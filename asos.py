import logging
import asyncio
import aiohttp
import motor.motor_asyncio
import os
import sys
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup 
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                           InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove)

# LOGLAR
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- SOZLAMALAR ---
API_TOKEN = '8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo'
ADMIN_ID = 7861165622 
SMM_API_KEY = '00c9d8e11e3935fe8861533a792fd2fe'
SMM_API_URL = 'https://smmapi.safobuilder.uz/shox_smmbot/api/v2'

# --- MONGODB ---
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?retryWrites=true&w=majority&appName=ZOirbek2003"
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client.smm_pro_database
users_col = db.users
services_col = db.services
orders_col = db.orders

# --- HOLATLAR (FSM) ---
class PaymentState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()

class SupportState(StatesGroup):
    waiting_for_message = State()

class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()

# --- KLAVIATURALAR ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish")],
    [KeyboardButton(text="👤 Mening hisobim"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

payment_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="✅ To'lov qildim")],
    [KeyboardButton(text="🏠 Orqaga")]
], resize_keyboard=True)

# --- START ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_deposited': 0}},
        upsert=True
    )
    await message.answer("SMM Botga xush kelibsiz!", reply_markup=main_menu)

# --- 💰 BALANS TO'LDIRISH TIZIMI ---
@dp.message(F.text == "💰 Balans to'ldirish")
async def pay_info(message: types.Message):
    text = (
        "💳 **To'lov tizimi:**\n\n"
        "🔸 **Karta:** `9860030125568440`\n"
        f"🔸 **ID:** `{message.from_user.id}`\n\n"
        "👆 Ushbu karta raqamga xohlagan ilova orqali o'zingiz xohlagancha pul tashlang va chekni yuborib kuting.\n\n"
        "⚠️ **Diqqat!** Kartaga pul tashlasangiz va necha pul tashlaganingizni yozishda xatoga yo'l qo'yib, "
        "summada 1 so'mga ham adashsangiz sizning to'lovingiz tasdiqlanmaydi va pullar qaytarilmaydi!❗️\n\n"
        "📞 To'lov tushishi kechiksa: +998883075131"
    )
    await message.answer(text, reply_markup=payment_kb, parse_mode="Markdown")

@dp.message(F.text == "✅ To'lov qildim")
async def pay_confirm(message: types.Message, state: FSMContext):
    await message.answer("💵 **To'lov miqdorini kiriting:**\n\nMinimal: 1000 so'm", reply_markup=ReplyKeyboardRemove())
    await state.set_state(PaymentState.waiting_for_amount)

@dp.message(PaymentState.waiting_for_amount)
async def pay_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1000:
        return await message.answer("❌ Minimal 1000 so'm kiriting!")
    
    await state.update_data(amount=message.text)
    await message.answer("🖼 **To'lov screenshotini (chekni) yuboring:**")
    await state.set_state(PaymentState.waiting_for_screenshot)

@dp.message(PaymentState.waiting_for_screenshot, F.photo)
async def pay_screenshot(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    user_id = message.from_user.id
    
    # Adminga yuborish
    caption = (
        "💰 **Yangi to'lov so'rovi!**\n\n"
        f"👤 Foydalanuvchi: {message.from_user.full_name}\n"
        f"🆔 ID: `{user_id}`\n"
        f"💵 Summa: {amount} so'm\n"
    )
    
    # Tasdiqlash tugmalari
    admin_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_yes_{user_id}_{amount}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_no_{user_id}")]
    ])
    
    await bot.send_photo(ADMIN_ID, photo=message.photo[-1].file_id, caption=caption, reply_markup=admin_kb, parse_mode="Markdown")
    await message.answer("✅ To'lovingiz adminga yuborildi. Tasdiqlanishini kuting!", reply_markup=main_menu)
    await state.clear()

# --- 👨‍💻 BOG'LANISH (SHIKOYAT) ---
@dp.message(F.text == "👨‍💻 Bog'lanish")
async def support_start(message: types.Message, state: FSMContext):
    await message.answer("✍️ Shikoyat yoki taklifingizni yozib qoldiring. Admin tez orada javob beradi:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(SupportState.waiting_for_message)

@dp.message(SupportState.waiting_for_message)
async def support_finish(message: types.Message, state: FSMContext):
    # Adminga shikoyatni yetkazish
    text = (
        "📩 **Yangi shikoyat/xabar:**\n\n"
        f"👤 Kimdan: {message.from_user.full_name}\n"
        f"🆔 ID: `{message.from_user.id}`\n"
        f"📝 Xabar: {message.text}"
    )
    await bot.send_message(ADMIN_ID, text, parse_mode="Markdown")
    await message.answer("✅ Xabaringiz yuborildi!", reply_markup=main_menu)
    await state.clear()

# --- ADMIN TO'LOVNI TASDIQLASHI ---
@dp.callback_query(F.data.startswith("pay_"))
async def admin_pay_process(callback: types.CallbackQuery):
    _, action, uid, amount = callback.data.split("_")
    uid = int(uid)
    
    if action == "yes":
        amount = float(amount)
        await users_col.update_one({'user_id': uid}, {'$inc': {'balance': amount, 'total_deposited': amount}})
        await bot.send_message(uid, f"✅ To'lovingiz tasdiqlandi! Hisobingizga {amount:,.0f} so'm qo'shildi.")
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ **TASDIQLANDI**")
    else:
        await bot.send_message(uid, "❌ Kechirasiz, to'lovingiz tasdiqlanmadi. Ma'lumotlarni tekshirib qayta yuboring.")
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ **RAD ETILDI**")
    
    await callback.answer()

# --- ORQAGA TUGMASI ---
@dp.message(F.text == "🏠 Orqaga")
async def back_to_main(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

# (Buyurtma berish, Admin panel kabi avvalgi funksiyalar kodning oxirida bo'lishi kerak)

async def main():
    port = int(os.environ.get("PORT", 10000))
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import motor.motor_asyncio
import os
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (ReplyKeyboardMarkup, KeyboardButton, 
                           InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove)

# --- KONFIGURATSIYA ---
API_TOKEN = '8473159649:AAHt9KnDd0aRDvthXrIE1sRWhP2u7DHpCnM'
ADMIN_ID = 7861165622
KARTA_RAQAMI = "9860 0301 2556 8441"
SMM_API_KEY = '00c9d8e11e3935fe8861533a792fd2fe'
SMM_API_URL = 'https://smmapi.safobuilder.uz/shox_smmbot/api/v2'

# --- MONGODB ---
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?retryWrites=true&w=majority&appName=ZOirbek2003"
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client.smm_pro_database
users_col = db.users
services_col = db.services
orders_col = db.orders

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- HOLATLAR (FSM) ---
class EditService(StatesGroup):
    waiting_for_new_value = State()

class ServiceState(StatesGroup):
    waiting_for_name = State()
    waiting_for_min = State()
    waiting_for_price = State()
    waiting_for_api_id = State()
    waiting_for_cat = State()

class OrderState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_link = State()

class PaymentState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_screenshot = State()

class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_manual_amount = State()

class HelpState(StatesGroup):
    waiting_for_msg = State()

# --- TUGMALAR ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish"), KeyboardButton(text="💰 Balans")],
    [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")],
    [KeyboardButton(text="🆘 Yordam")]
], resize_keyboard=True)

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="➕ Yangi xizmat qo'shish"), KeyboardButton(text="📝 Xizmatlarni tahrirlash")],
    [KeyboardButton(text="💸 Balans qo'shish (ID)"), KeyboardButton(text="🔄 API orqali yangilash")],
    [KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

pay_confirm_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="✅ To'lov qildim")],
    [KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_deposited': 0}},
        upsert=True
    )
    await message.answer(f"Xush kelibsiz, {message.from_user.first_name}!", reply_markup=main_menu)

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("👨‍💻 Admin Panel:", reply_markup=admin_menu)

@dp.message(F.text == "🏠 Asosiy menyu")
async def home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_menu)

# --- BALANS VA STATISTIKA ---

@dp.message(F.text == "💰 Balans")
async def show_balance(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    bal = user['balance'] if user else 0
    await message.answer(f"💰 Balansingiz: `{bal:,.0f}` so'm", parse_mode="Markdown")

@dp.message(F.text == "📊 Statistika")
async def stat(message: types.Message):
    u_count = await users_col.count_documents({})
    # Jami tushum
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_deposited"}}}]
    res = await users_col.aggregate(pipeline).to_list(length=1)
    total = res[0]['total'] if res else 0
    await message.answer(f"📊 **Statistika:**\n\n👤 Foydalanuvchilar: {u_count} ta\n💰 Jami tushum: {total:,.0f} so'm", parse_mode="Markdown")

# --- 💳 HISOBNI TO'LDIRISH (SIZ SO'RAGAN MANTIQ) ---

@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_start(message: types.Message):
    text = (
        f"💳 **To'lov tizimi:**\n\n"
        f"Karta: `{KARTA_RAQAMI}`\n"
        f"ID: `{message.from_user.id}`\n\n"
        "👆 Ushbu karta raqamga xohlagan ilova orqali o'zingiz xohlagancha pul tashlang va chekni yuborib kuting.\n\n"
        "**Diqqat!** Kartaga pul tashlasangiz va necha pul tashlaganingizni yozishda xatoga yo'l qo'yib, "
        "summada 1 so'mga ham adashsangiz sizning to'lovingiz tasdiqlanmaydi va pullar qaytarilmaydi! ❗️\n\n"
        "To'lov tushishi kechiksa bizga tel qiling yoki sms yozing: +998883075131"
    )
    await message.answer(text, reply_markup=pay_confirm_kb, parse_mode="Markdown")

@dp.message(F.text == "✅ To'lov qildim")
async def pay_confirm(message: types.Message, state: FSMContext):
    await message.answer("💵 To'lov miqdorini kiriting:\n\nMinimal: 1000 so'm", reply_markup=ReplyKeyboardRemove())
    await state.set_state(PaymentState.waiting_for_amount)

@dp.message(PaymentState.waiting_for_amount)
async def pay_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit() or int(message.text) < 1000:
        return await message.answer("❌ Minimal 1000 so'm kiriting!")
    await state.update_data(amount=float(message.text))
    await message.answer("🖼 Screenshot (chek) yuboring:")
    await state.set_state(PaymentState.waiting_for_screenshot)

@dp.message(PaymentState.waiting_for_screenshot, F.photo)
async def pay_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = data['amount']
    uid = message.from_user.id
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"p_ok_{uid}_{amount}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"p_no_{uid}")]
    ])
    
    await bot.send_photo(
        ADMIN_ID, 
        message.photo[-1].file_id, 
        caption=f"💰 **Yangi to'lov!**\nID: `{uid}`\nSumma: `{amount:,.0f}` so'm",
        reply_markup=kb,
        parse_mode="Markdown"
    )
    await message.answer("✅ Yuborildi. Admin tasdiqlashini kuting.", reply_markup=main_menu)
    await state.clear()

@dp.callback_query(F.data.startswith("p_"))
async def admin_verify_pay(call: types.CallbackQuery):
    parts = call.data.split("_")
    action, uid, amount = parts[1], int(parts[2]), float(parts[3]) if len(parts)>3 else 0
    
    if action == "ok":
        await users_col.update_one({'user_id': uid}, {'$inc': {'balance': amount, 'total_deposited': amount}})
        await bot.send_message(uid, f"✅ To'lovingiz tasdiqlandi! Hisobingizga {amount:,.0f} so'm qo'shildi.")
        await call.message.edit_caption(caption=call.message.caption + "\n\n✅ **TASDIQLANDI**")
    else:
        await bot.send_message(uid, "❌ To'lovingiz rad etildi. Ma'lumotlarni tekshirib qayta yuboring.")
        await call.message.edit_caption(caption=call.message.caption + "\n\n❌ **RAD ETILDI**")
    await call.answer()

# --- 🚀 BUYURTMA BERISH (API BILAN) ---

@dp.message(F.text == "🚀 Buyurtma berish")
async def order_start(message: types.Message):
    services = await services_col.find().to_list(length=50)
    if not services: return await message.answer("Xizmatlar yo'q.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s['name']} ({s['price']} so'm)", callback_data=f"ord_{s['id']}")] for s in services
    ])
    await message.answer("Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ord_"))
async def order_qty(call: types.CallbackQuery, state: FSMContext):
    srv_id = call.data.split("_")[1]
    srv = await services_col.find_one({'id': srv_id})
    await state.update_data(srv_id=srv['id'], srv_name=srv['name'], price=srv['price'], min_q=srv['min_amount'])
    await call.message.answer(f"🔢 Miqdorni kiriting (Min: {srv['min_amount']}):")
    await state.set_state(OrderState.waiting_for_amount)
    await call.answer()

@dp.message(OrderState.waiting_for_amount)
async def order_link(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam yozing!")
    qty = int(message.text)
    data = await state.get_data()
    if qty < data['min_q']: return await message.answer(f"❌ Minimal miqdor: {data['min_q']}")
    
    cost = (qty / 1000) * data['price']
    user = await users_col.find_one({'user_id': message.from_user.id})
    
    if user['balance'] < cost:
        return await message.answer(f"❌ Mablag' yetarli emas! Narxi: {cost:,.0f} so'm")
    
    await state.update_data(qty=qty, cost=cost)
    await message.answer(f"💰 Narxi: {cost:,.0f} so'm.\n🔗 Linkni yuboring:")
    await state.set_state(OrderState.waiting_for_link)

@dp.message(OrderState.waiting_for_link)
async def order_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    # API so'rovi (misol tariqasida)
    async with aiohttp.ClientSession() as session:
        payload = {'key': SMM_API_KEY, 'action': 'add', 'service': data['srv_id'], 'link': message.text, 'quantity': data['qty']}
        async with session.post(SMM_API_URL, data=payload) as resp:
            res = await resp.json()
            if 'order' in res:
                await users_col.update_one({'user_id': message.from_user.id}, {'$inc': {'balance': -data['cost']}})
                await message.answer(f"✅ Buyurtma qabul qilindi! ID: {res['order']}")
                await bot.send_message(ADMIN_ID, f"📦 **Yangi buyurtma!**\nUser: `{message.from_user.id}`\nXizmat: {data['srv_name']}\nLink: {message.text}")
            else:
                await message.answer(f"❌ API Xatosi: {res.get('error')}")
    await state.clear()

# --- 🆘 YORDAM (SHIKOYAT) ---

@dp.message(F.text == "🆘 Yordam")
async def help_s(message: types.Message, state: FSMContext):
    await message.answer("✍️ Shikoyat yoki taklifingizni yozing:", reply_markup=ReplyKeyboardRemove())
    await state.set_state(HelpState.waiting_for_msg)

@dp.message(HelpState.waiting_for_msg)
async def help_admin(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 **Yangi shikoyat!**\n\nKimdan: {message.from_user.full_name}\nID: `{message.from_user.id}`\n\nXabar: {message.text}")
    await message.answer("✅ Xabaringiz adminga yetkazildi.", reply_markup=main_menu)
    await state.clear()

# --- ADMIN: BALANS QO'SHISH (ID ORQALI) ---

@dp.message(F.text == "💸 Balans qo'shish (ID)", F.from_user.id == ADMIN_ID)
async def adm_bal_direct(message: types.Message, state: FSMContext):
    await message.answer("Foydalanuvchi ID:"); await state.set_state(AdminState.waiting_for_user_id)

@dp.message(AdminState.waiting_for_user_id)
async def adm_bal_direct_2(message: types.Message, state: FSMContext):
    await state.update_data(t_id=int(message.text))
    await message.answer("Summa:"); await state.set_state(AdminState.waiting_for_manual_amount)

@dp.message(AdminState.waiting_for_manual_amount)
async def adm_bal_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    amount = float(message.text)
    await users_col.update_one({'user_id': d['t_id']}, {'$inc': {'balance': amount, 'total_deposited': amount}}, upsert=True)
    await bot.send_message(d['t_id'], f"✅ Hisobingiz admin tomonidan {amount:,.0f} so'mga to'ldirildi!")
    await message.answer("✅ Tayyor!", reply_markup=admin_menu)
    await state.clear()

# --- RENDER PORT VA ISHGA TUSHIRISH ---

async def main():
    # Render uchun port
    port = int(os.environ.get("PORT", 10000))
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi")

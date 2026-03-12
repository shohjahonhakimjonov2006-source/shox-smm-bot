import logging
import asyncio
import aiohttp
import motor.motor_asyncio
import os
import sys
from datetime import datetime

# AIOGRAM importlari
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup 
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# LOGLARNI SOZLASH
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
class OrderState(StatesGroup):
    entering_link = State()
    entering_quantity = State()

class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
    m_name = State()
    m_price = State()
    m_id = State()
    m_cat = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- KLAVIATURALAR ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish")],
    [KeyboardButton(text="👤 Mening hisobim"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

# --- FOYDALANUVCHI QISMI ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_deposited': 0}},
        upsert=True
    )
    await message.answer("SMM Botga xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu)

# --- 📊 BUYURTMALARIM QISMI ---
@dp.message(F.text == "📊 Buyurtmalarim")
async def my_orders(message: types.Message):
    user_orders = await orders_col.find({'user_id': message.from_user.id}).sort('_id', -1).limit(10).to_list(length=10)
    
    if not user_orders:
        return await message.answer("⚠️ Sizda hali buyurtmalar mavjud emas.")
    
    text = "📦 **Oxirgi 10 ta buyurtmangiz:**\n\n"
    for o in user_orders:
        text += f"🆔 ID: `{o.get('order_id')}`\n🔹 Xizmat: {o.get('service_name')}\n💰 Narxi: {o.get('cost')} so'm\n📅 Sana: {o.get('date')}\n\n"
    
    await message.answer(text, parse_mode="Markdown")

# --- 💰 BALANS TO'LDIRISH ---
@dp.message(F.text == "💰 Balans to'ldirish")
async def top_up_balance(message: types.Message):
    text = (
        "💳 **Hisobni to'ldirish usullari:**\n\n"
        "1. Click/Payme orqali (Avtomatik emas)\n"
        "2. Admin bilan bog'lanish orqali\n\n"
        "To'lov qilish uchun adminga murojaat qiling va to'lov skrinshotini yuboring. "
        "Admin hisobingizni tasdiqlagach, balansingizga pul qo'shiladi."
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👨‍💻 Adminga yozish", url="https://t.me/shox_admin")] # O'zingizni linkizni qo'ying
    ])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

# --- 👨‍💻 BOG'LANISH ---
@dp.message(F.text == "👨‍💻 Bog'lanish")
async def contact_admin(message: types.Message):
    text = (
        "👨‍💻 **Texnik yordam bo'limi**\n\n"
        "Savollaringiz yoki muammolar bo'lsa, adminga murojaat qilishingiz mumkin:\n"
        "📍 Telegram: @shox_admin\n"
        "🕒 Ish vaqti: 09:00 - 22:00"
    )
    await message.answer(text)

# --- MENING HISOBIM ---
@dp.message(F.text == "👤 Mening hisobim")
async def my_acc(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    balance = user.get('balance', 0) if user else 0
    await message.answer(f"👤 **ID:** `{message.from_user.id}`\n💵 **Balans:** {balance:,.2f} so'm", parse_mode="Markdown")

# --- ADMIN PANEL VA BOSHQA FUNKSIYALAR ---
# (Avvalgi koddagi Buyurtma berish va Admin funksiyalari shu yerda davom etadi)

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Xizmatlarni yangilash"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="💰 Balans qo'shish"), KeyboardButton(text="➕ Yangi xizmat qo'shish")],
        [KeyboardButton(text="🏠 Asosiy menyu")]
    ], resize_keyboard=True)
    await message.answer("🛠 Admin paneli:", reply_markup=kb)

# ... (Xizmatlarni yangilash va boshqa admin funksiyalari o'z joyida qoladi)

async def main():
    port = int(os.environ.get("PORT", 10000))
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

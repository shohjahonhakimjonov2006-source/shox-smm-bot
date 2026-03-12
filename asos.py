import logging
import asyncio
import aiohttp
import motor.motor_asyncio
import os
import sys
from datetime import datetime

# AIOGRAM importlari - StatesGroup xatosini aynan shu qator tuzatadi
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

social_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Telegram"), KeyboardButton(text="Instagram")],
    [KeyboardButton(text="Tik tok"), KeyboardButton(text="YouTube")],
    [KeyboardButton(text="Facebook"), KeyboardButton(text="Twitter")],
    [KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

# --- FOYDALANUVCHI QISMI ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_deposited': 0}},
        upsert=True
    )
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu)

@dp.message(F.text == "🚀 Buyurtma berish")
async def show_socials(message: types.Message):
    await message.answer("📁 Ijtimoiy tarmoqni tanlang:", reply_markup=social_menu)

@dp.message(F.text.in_(["Telegram", "Instagram", "Tik tok", "YouTube", "Facebook", "Twitter"]))
async def list_services(message: types.Message):
    cat = message.text
    services = await services_col.find({"category": {"$regex": cat, "$options": "i"}}).to_list(length=30)
    
    if not services:
        return await message.answer(f"😔 {cat} bo'limida xizmatlar topilmadi.")
    
    kb_list = []
    for s in services:
        kb_list.append([InlineKeyboardButton(text=f"{s['name'][:30]} - {s['price']} so'm", callback_data=f"srv_{s['id']}")])
    
    await message.answer(f"📁 {cat} xizmatlari:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("srv_"))
async def service_select(callback: types.CallbackQuery, state: FSMContext):
    s_id = callback.data.split("_")[1]
    service = await services_col.find_one({'id': s_id})
    if not service: return await callback.answer("Xizmat topilmadi!")
    
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await callback.message.answer(f"📌 {service['name']}\n\n🔗 Havola (link) yuboring:")
    await state.set_state(OrderState.entering_link)

@dp.message(OrderState.entering_link)
async def process_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Miqdorni kiriting:")
    await state.set_state(OrderState.entering_quantity)

@dp.message(OrderState.entering_quantity)
async def process_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Raqam kiriting!")
    qty = int(message.text)
    data = await state.get_data()
    cost = (float(data['s_price']) / 1000) * qty
    
    user = await users_col.find_one({'user_id': message.from_user.id})
    if user.get('balance', 0) < cost:
        return await message.answer(f"⚠️ Balans yetarli emas! Narxi: {cost:,.0f} so'm")

    async with aiohttp.ClientSession() as session:
        payload = {'key': SMM_API_KEY, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}
        async with session.post(SMM_API_URL, data=payload) as resp:
            res = await resp.json()
            if 'order' in res:
                await users_col.update_one({'user_id': message.from_user.id}, {'$inc': {'balance': -cost}})
                await message.answer(f"✅ Buyurtma qabul qilindi! ID: {res['order']}", reply_markup=main_menu)
            else:
                await message.answer(f"❌ Xato: {res.get('error')}")
    await state.clear()

@dp.message(F.text == "👤 Mening hisobim")
async def my_acc(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    await message.answer(f"👤 ID: `{message.from_user.id}`\n💵 Balans: {user.get('balance', 0):,.2f} so'm", parse_mode="Markdown")

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Xizmatlarni yangilash"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="💰 Balans qo'shish"), KeyboardButton(text="➕ Yangi xizmat qo'shish")],
        [KeyboardButton(text="🏠 Asosiy menyu")]
    ], resize_keyboard=True)
    await message.answer("🛠 Admin paneli:", reply_markup=kb)

@dp.message(F.text == "📊 Statistika")
async def stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    u_count = await users_col.count_documents({})
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_deposited"}}}]
    res = await users_col.aggregate(pipeline).to_list(length=1)
    total_money = res[0]['total'] if res else 0
    await message.answer(f"👥 Foydalanuvchilar: {u_count}\n💰 Umumiy kiritilgan summa: {total_money:,.0f} so'm")

@dp.message(F.text == "🔄 Xizmatlarni yangilash")
async def update_srv(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    status = await message.answer("🔄 Yangilanmoqda...")
    async with aiohttp.ClientSession() as session:
        async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as r:
            data = await r.json()
            if isinstance(data, list):
                await services_col.delete_many({'manual': {'$ne': True}})
                for s in data:
                    await services_col.update_one(
                        {'id': str(s['service'])},
                        {'$set': {'id': str(s['service']), 'name': s['name'], 'price': float(s['rate']), 'category': s['category']}},
                        upsert=True
                    )
                await status.edit_text(f"✅ {len(data)} ta xizmat yangilandi!")

@dp.message(F.text == "💰 Balans qo'shish")
async def add_bal_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Foydalanuvchi ID raqamini yuboring:")
    await state.set_state(AdminState.waiting_for_user_id)

@dp.message(AdminState.waiting_for_user_id)
async def add_bal_uid(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("ID faqat raqam bo'ladi!")
    await state.update_data(uid=int(message.text))
    await message.answer("Summani kiriting:")
    await state.set_state(AdminState.waiting_for_amount)

@dp.message(AdminState.waiting_for_amount)
async def add_bal_final(message: types.Message, state: FSMContext):
    try:
        amount = float(message.text)
        data = await state.get_data()
        await users_col.update_one({'user_id': data['uid']}, {'$inc': {'balance': amount, 'total_deposited': amount}}, upsert=True)
        await message.answer(f"✅ {data['uid']} hisobiga {amount} so'm qo'shildi.")
        try: await bot.send_message(data['uid'], f"✅ Hisobingiz {amount} so'mga to'ldirildi!")
        except: pass
    except:
        await message.answer("❌ Xato! Summani to'g'ri kiriting.")
    await state.clear()

@dp.message(F.text == "➕ Yangi xizmat qo'shish")
async def manual_srv(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Xizmat nomi:")
    await state.set_state(AdminState.m_name)

@dp.message(AdminState.m_name)
async def m_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Narxi (1000 ta uchun):")
    await state.set_state(AdminState.m_price)

@dp.message(AdminState.m_price)
async def m_price(message: types.Message, state: FSMContext):
    await state.update_data(price=float(message.text))
    await message.answer("Service ID (API-dagi):")
    await state.set_state(AdminState.m_id)

@dp.message(AdminState.m_id)
async def m_id(message: types.Message, state: FSMContext):
    await state.update_data(sid=message.text)
    await message.answer("Kategoriya (Masalan: Telegram):")
    await state.set_state(AdminState.m_cat)

@dp.message(AdminState.m_cat)
async def m_final(message: types.Message, state: FSMContext):
    d = await state.get_data()
    await services_col.insert_one({'id': d['sid'], 'name': d['name'], 'price': d['price'], 'category': message.text, 'manual': True})
    await message.answer("✅ Xizmat qo'lda qo'shildi!")
    await state.clear()

@dp.message(F.text == "🏠 Asosiy menyu")
async def back_home(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

# --- RENDER PORT VA ISHGA TUSHIRISH ---
async def main():
    port = int(os.environ.get("PORT", 10000))
    # Render "No open ports detected" xatosini oldini olish
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

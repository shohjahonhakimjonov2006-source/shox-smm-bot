import logging
import asyncio
import aiohttp
import motor.motor_asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

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

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class OrderState(StatesGroup):
    entering_link = State()
    entering_quantity = State()

# --- MENYULAR ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish")],
    [KeyboardButton(text="👤 Mening hisobim"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

social_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Telegram"), KeyboardButton(text="Tik tok")],
    [KeyboardButton(text="Stars va Premium"), KeyboardButton(text="Facebook")],
    [KeyboardButton(text="Instagram"), KeyboardButton(text="YouTube")],
    [KeyboardButton(text="WhatsApp"), KeyboardButton(text="Twitter")],
    [KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_spent': 0}},
        upsert=True
    )
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu)

@dp.message(F.text == "🚀 Buyurtma berish")
async def show_socials(message: types.Message):
    await message.answer("📁 Quyidagi ijtimoiy tarmoqlardan birini tanlang:", reply_markup=social_menu)

@dp.message(F.text.in_(["Telegram", "Tik tok", "Instagram", "YouTube", "Facebook", "Twitter", "WhatsApp", "Stars va Premium"]))
async def show_services(message: types.Message):
    category_name = message.text
    # Bazadan qidirishda ID ni string va int shaklida tekshirish uchun xatolikni oldini olamiz
    services = await services_col.find({"name": {"$regex": category_name, "$options": "i"}}).limit(15).to_list(length=15)
    
    if not services:
        services = await services_col.find().limit(15).to_list(length=15)

    if not services:
        return await message.answer("Xizmatlar topilmadi. Admin /admin orqali yangilashi kerak.")
    
    kb_list = []
    for s in services:
        kb_list.append([InlineKeyboardButton(text=f"{s['name'][:30]} - {s['price']} so'm", callback_data=f"srv_{s['id']}")])
    
    await message.answer(f"📁 {category_name} bo'limi. Xizmatni tanlang:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list))

@dp.callback_query(F.data.startswith("srv_"))
async def srv_click(callback: types.CallbackQuery, state: FSMContext):
    s_id = callback.data.split("_")[1]
    # MUHIM: Bazadan ham string, ham int shaklida qidirib ko'ramiz
    service = await services_col.find_one({'$or': [{'id': s_id}, {'id': int(s_id) if s_id.isdigit() else s_id}]})
    
    if not service:
        logging.error(f"Xizmat topilmadi: ID={s_id}")
        return await callback.message.answer("❌ Xatolik: Xizmat bazadan topilmadi! Iltimos, /admin orqali yangilang.")
        
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await callback.message.answer(f"📌 {service['name']}\n\n🔗 Havolani yuboring:")
    await state.set_state(OrderState.entering_link)

@dp.message(OrderState.entering_link)
async def process_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Miqdorni kiriting:")
    await state.set_state(OrderState.entering_quantity)

@dp.message(OrderState.entering_quantity)
async def process_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam kiriting!")
    qty = int(message.text)
    data = await state.get_data()
    cost = (float(data['s_price']) / 1000) * qty
    
    user = await users_col.find_one({'user_id': message.from_user.id})
    if not user or user.get('balance', 0) < cost:
        return await message.answer(f"⚠️ Mablag' yetarli emas! Narxi: {cost:,.2f} so'm")

    async with aiohttp.ClientSession() as session:
        payload = {'key': SMM_API_KEY, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}
        async with session.post(SMM_API_URL, data=payload) as resp:
            res = await resp.json()
            if 'order' in res:
                await users_col.update_one({'user_id': message.from_user.id}, {'$inc': {'balance': -cost}})
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await orders_col.insert_one({
                    'order_id': res['order'], 'user_id': message.from_user.id,
                    'service_name': data['s_name'], 'cost': cost, 'link': data['link'],
                    'quantity': qty, 'date': now, 'status': 'Pending'
                })
                await message.answer(f"✅ Buyurtma qabul qilindi!\nID: {res['order']}", reply_markup=main_menu)
            else:
                await message.answer(f"❌ API xatosi: {res.get('error', 'Nomalum xato')}")
    await state.clear()

@dp.message(F.text == "👤 Mening hisobim")
async def my_account(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    order_count = await orders_col.count_documents({'user_id': message.from_user.id})
    balance = user.get('balance', 0) if user else 0
    text = (f"👤 Sizning ID raqamingiz: `{message.from_user.id}`\n\n"
            f"💵 Balansingiz: {balance:,.2f} so'm\n"
            f"📊 Buyurtmalaringiz: {order_count} ta")
    await message.answer(text, parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔄 Xizmatlarni yangilash")], [KeyboardButton(text="🏠 Asosiy menyu")]], resize_keyboard=True)
        await message.answer("Admin paneli:", reply_markup=kb)

@dp.message(F.text == "🔄 Xizmatlarni yangilash")
async def update_srv(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiohttp.ClientSession() as session:
        async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as r:
            data = await r.json()
            if isinstance(data, list):
                await services_col.delete_many({})
                for s in data:
                    # ID-ni har doim string sifatida saqlaymiz
                    await services_col.insert_one({'id': str(s['service']), 'name': s['name'], 'price': float(s['rate'])})
                await message.answer(f"✅ {len(data)} ta xizmat yangilandi!")

@dp.message(F.text == "🏠 Asosiy menyu")
async def back_main(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

# --- RENDER PORT BINDING ---
async def start_web_server():
    port = int(os.environ.get("PORT", 10000))
    server = await asyncio.start_server(lambda r, w: None, '0.0.0.0', port)
    async with server:
        await server.serve_forever()

async def main():
    # Bir vaqtning o'zida ham botni, ham portni ishga tushiramiz
    await asyncio.gather(
        dp.start_polling(bot),
        start_web_server()
    )

if __name__ == "__main__":
    asyncio.run(main())

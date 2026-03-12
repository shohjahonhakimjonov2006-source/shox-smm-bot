import logging
import asyncio
import aiohttp
import motor.motor_asyncio
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
KARTA_RAQAM = "9860030125568441"

# --- MONGODB ULANISH ---
# Siz bergan ulanish kodi muvaffaqiyatli qo'shildi
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?retryWrites=true&w=majority&appName=ZOirbek2003"
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client.smm_pro_database

users_col = db.users
services_col = db.services
orders_col = db.orders

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- HOLATLAR ---
class PaymentState(StatesGroup):
    entering_amount = State()
    sending_screenshot = State()

class AdminState(StatesGroup):
    add_bal_id = State()
    add_bal_amount = State()

class OrderState(StatesGroup):
    entering_link = State()
    entering_quantity = State()

class SupportState(StatesGroup):
    waiting_message = State()

# --- KLAVIATURALAR ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish"), KeyboardButton(text="👤 Profil")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

admin_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Xizmatlarni yangilash"), KeyboardButton(text="💸 Balans qo'shish")],
    [KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

payment_kb = InlineKeyboardMarkup(inline_keyboard=[
    [InlineKeyboardButton(text="✅ To'lov qildim", callback_data="pay_done")],
    [InlineKeyboardButton(text="⬅️ Ortga", callback_data="back_home")]
])

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panelga xush kelibsiz!", reply_markup=admin_menu)

@dp.message(F.text == "🔄 Xizmatlarni yangilash")
async def sync_services(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("Xizmatlar yangilanmoqda...")
    async with aiohttp.ClientSession() as session:
        async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as response:
            services = await response.json()
            if isinstance(services, list):
                await services_col.delete_many({}) 
                for s in services:
                    await services_col.insert_one({
                        'id': s['service'],
                        'name': s['name'],
                        'price': float(s['rate']),
                        'min': int(s['min']),
                        'max': int(s['max'])
                    })
                await message.answer(f"✅ {len(services)} ta xizmat MongoDB-ga yuklandi!")

# --- BOG'LANISH ---
@dp.message(F.text == "👨‍💻 Bog'lanish")
async def support_start(message: types.Message, state: FSMContext):
    await message.answer("📑 Murojaat matnini yozib yuboring.")
    await state.set_state(SupportState.waiting_message)

@dp.message(SupportState.waiting_message)
async def support_finish(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 Yangi murojaat!\n👤 Ism: {message.from_user.full_name}\nID: `{message.from_user.id}`\n\n📝 Matn: {message.text}")
    await message.answer("✅ Murojaatingiz yuborildi. Tez orada javob beramiz.")
    await state.clear()

# --- BUYURTMALARIM ---
@dp.message(F.text == "📊 Buyurtmalarim")
async def my_orders(message: types.Message):
    cursor = orders_col.find({'user_id': message.from_user.id}).sort('_id', -1).limit(10)
    rows = await cursor.to_list(length=10)
    if not rows:
        return await message.answer("Sizda hali buyurtmalar mavjud emas.")
    
    msg = "📊 **Oxirgi 10 ta buyurtmangiz:**\n\n"
    for r in rows:
        msg += f"🆔 ID: `{r['order_id']}`\n🔹 {r['service_name']}\n💰 {r['cost']} so'm\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    await message.answer(msg, parse_mode="Markdown")

# --- PROFIL ---
@dp.message(F.text == "👤 Profil")
async def user_profile(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    balance = user.get('balance', 0) if user else 0
    await message.answer(f"👤 Profilingiz:\n🆔 ID: `{message.from_user.id}`\n💰 Balans: {balance} so'm")

# --- BUYURTMA BERISH ---
@dp.message(F.text == "🚀 Buyurtma berish")
async def order_start(message: types.Message):
    services = await services_col.find().limit(25).to_list(length=25)
    if not services: return await message.answer("Xizmatlar topilmadi. Admin /admin menyusidan yangilashi kerak.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name'][:25]} | {s['price']} so'm", callback_data=f"order_{s['id']}")] for s in services])
    await message.answer("Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("order_"))
async def order_select(callback: types.CallbackQuery, state: FSMContext):
    s_id = callback.data.split("_")[1]
    service = await services_col.find_one({'id': s_id})
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'], min_q=service['min'])
    await callback.message.answer(f"📌 {service['name']}\n\n🔗 Havolani yuboring:")
    await state.set_state(OrderState.entering_link)

@dp.message(OrderState.entering_link)
async def order_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    data = await state.get_data()
    await message.answer(f"🔢 Miqdorni kiriting (Min: {data['min_q']}):")
    await state.set_state(OrderState.entering_quantity)

@dp.message(OrderState.entering_quantity)
async def order_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Iltimos, faqat raqam kiriting!")
    qty = int(message.text)
    data = await state.get_data()
    total_cost = (data['s_price'] / 1000) * qty
    
    user = await users_col.find_one({'user_id': message.from_user.id})
    current_balance = user.get('balance', 0) if user else 0
    
    if current_balance < total_cost:
        return await message.answer(f"⚠️ Mablag' yetarli emas!\nKerak: {total_cost} so'm\nSizda: {current_balance} so'm")

    async with aiohttp.ClientSession() as session:
        params = {'key': SMM_API_KEY, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}
        async with session.post(SMM_API_URL, data=params) as resp:
            res = await resp.json()
            if 'order' in res:
                await users_col.update_one({'user_id': message.from_user.id}, {'$inc': {'balance': -total_cost}})
                await orders_col.insert_one({
                    'order_id': res['order'], 
                    'user_id': message.from_user.id, 
                    'service_name': data['s_name'], 
                    'cost': total_cost
                })
                await message.answer(f"✅ Buyurtma qabul qilindi!\n🆔 ID: {res['order']}")
            else:
                await message.answer("❌ API xatosi yuz berdi. Keyinroq urinib ko'ring.")
    await state.clear()

# --- BALANS QO'SHISH (ADMIN) ---
@dp.message(F.text == "💸 Balans qo'shish")
async def add_bal_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("User ID sini kiriting:")
    await state.set_state(AdminState.add_bal_id)

@dp.message(AdminState.add_bal_id)
async def add_bal_id_proc(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("ID faqat raqam bo'lishi kerak!")
    await state.update_data(target_id=int(message.text))
    await message.answer("Qancha qo'shmoqchisiz (summa):")
    await state.set_state(AdminState.add_bal_amount)

@dp.message(AdminState.add_bal_amount)
async def add_bal_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = float(message.text)
    await users_col.update_one(
        {'user_id': data['target_id']},
        {'$inc': {'balance': amount}},
        upsert=True
    )
    await message.answer(f"✅ ID {data['target_id']} hisobiga {amount} so'm qo'shildi!")
    try:
        await bot.send_message(data['target_id'], f"💰 Balansingiz {amount} so'mga to'ldirildi!")
    except: pass
    await state.clear()

@dp.message(F.text == "💰 Balans to'ldirish")
async def fill_bal(message: types.Message):
    text = (
        f"💳 Karta raqam: `{KARTA_RAQAM}`\n"
        f"👤 ID: `{message.from_user.id}`\n\n"
        "To'lov qilganingizdan so'ng, chekni (screenshot) adminga yuboring."
    )
    await message.answer(text, reply_markup=payment_kb)

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0}},
        upsert=True
    )
    await message.answer("Xush kelibsiz! Botdan foydalanish uchun menyuni tanlang.", reply_markup=main_menu)

@dp.message(F.text == "🏠 Asosiy menyu")
async def back_home(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

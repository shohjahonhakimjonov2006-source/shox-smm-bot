import asyncio
import logging
from motor.motor_asyncio import AsyncIOMotorClient
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# --- KONFIGURATSIYA ---
API_TOKEN = '8473159649:AAHt9KnDd0aRDvthXrIE1sRWhP2u7DHpCnM'
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"
KARTA_RAQAMI = "9860 0301 2556 8441"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- MONGODB BAZASI ---
client = AsyncIOMotorClient(MONGO_URL)
db = client['smm_database']
users_col = db['users']
services_col = db['services']

# --- HOLATLAR (FSM) ---
class EditService(StatesGroup):
    waiting_for_new_value = State()

class ServiceState(StatesGroup):
    waiting_for_name = State()
    waiting_for_min = State()
    waiting_for_price = State()

class OrderState(StatesGroup):
    waiting_for_amount = State()
    waiting_for_link = State()

class PaymentState(StatesGroup):
    waiting_for_screenshot = State()
    waiting_for_admin_val = State()

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
    [KeyboardButton(text="💸 Balans qo'shish (ID)"), KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

# --- ASOSIY HANDLERLAR ---

@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    user = await users_col.find_one({"id": message.from_user.id})
    if not user:
        await users_col.insert_one({"id": message.from_user.id, "balance": 0})
    
    await message.answer(f"👋 Salom, {message.from_user.first_name}! SMM PRO botiga xush kelibsiz.", 
                         reply_markup=main_menu)

@dp.message(F.text == "💰 Balans")
async def show_balance(message: types.Message):
    user = await users_col.find_one({"id": message.from_user.id})
    bal = user['balance'] if user else 0
    await message.answer(f"💰 Balansingiz: `{bal:,.0f}` so'm", parse_mode="Markdown")

@dp.message(F.text == "📊 Statistika")
async def stat(message: types.Message):
    count = await users_col.count_documents({})
    await message.answer(f"📊 Jami foydalanuvchilar: {count} ta")

# --- XIZMATLARNI BOSHQARISH (ADMIN) ---

@dp.message(F.text == "📝 Xizmatlarni tahrirlash", F.from_user.id == ADMIN_ID)
async def list_services_edit(message: types.Message):
    services = await services_col.find().to_list(length=100)
    if not services:
        return await message.answer("Xizmatlar yo'q.")
    
    for s in services:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Nom", callback_data=f"edit_name_{s['_id']}"),
             InlineKeyboardButton(text="Min", callback_data=f"edit_min_{s['_id']}"),
             InlineKeyboardButton(text="Narx", callback_data=f"edit_price_{s['_id']}")],
            [InlineKeyboardButton(text="❌ O'chirish", callback_data=f"del_srv_{s['_id']}")]
        ])
        await message.answer(f"🛠 **{s['name']}**\n📦 Min: {s['min_amount']} | 💰 Narx: {s['price']} so'm", 
                             reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("edit_"))
async def edit_service_choice(call: types.CallbackQuery, state: FSMContext):
    _, field, srv_id = call.data.split("_")
    await state.update_data(srv_id=srv_id, field=field)
    await call.message.answer(f"Yangi {field} qiymatini kiriting:")
    await state.set_state(EditService.waiting_for_new_value)
    await call.answer()

@dp.message(EditService.waiting_for_new_value, F.from_user.id == ADMIN_ID)
async def save_edited_value(message: types.Message, state: FSMContext):
    data = await state.get_data()
    from bson.objectid import ObjectId
    
    val = message.text
    if data['field'] == "min": val = int(val)
    if data['field'] == "price": val = float(val)
    
    await services_col.update_one({"_id": ObjectId(data['srv_id'])}, {"$set": {data['field']: val}})
    await message.answer("✅ Yangilandi!", reply_markup=admin_menu)
    await state.clear()

# --- BUYURTMA BERISH ---

@dp.message(F.text == "🚀 Buyurtma berish")
async def order_list(message: types.Message):
    services = await services_col.find().to_list(length=100)
    if not services: return await message.answer("Xizmatlar yo'q.")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s['name']} ({s['price']} so'm)", callback_data=f"ord_{s['_id']}")] for s in services
    ])
    await message.answer("Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ord_"))
async def order_amount(call: types.CallbackQuery, state: FSMContext):
    from bson.objectid import ObjectId
    srv_id = call.data.split("_")[1]
    srv = await services_col.find_one({"_id": ObjectId(srv_id)})
    await state.update_data(srv_name=srv['name'], price=srv['price'], min_q=srv['min_amount'])
    await call.message.answer(f"🔢 Miqdorni kiriting (Min: {srv['min_amount']}):")
    await state.set_state(OrderState.waiting_for_amount)
    await call.answer()

@dp.message(OrderState.waiting_for_amount)
async def order_link(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam!")
    amount = int(message.text)
    data = await state.get_data()
    
    if amount < data['min_q']: return await message.answer(f"Min miqdor: {data['min_q']}")
    total_price = (amount / 1000) * data['price']
    
    user = await users_col.find_one({"id": message.from_user.id})
    if user['balance'] < total_price:
        return await message.answer(f"❌ Mablag' yetarli emas. Narxi: {total_price:,.0f}")
    
    await state.update_data(amount=amount, total_price=total_price)
    await message.answer(f"💰 Narxi: {total_price:,.0f} so'm. Link yuboring:")
    await state.set_state(OrderState.waiting_for_link)

@dp.message(OrderState.waiting_for_link)
async def order_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await users_col.update_one({"id": message.from_user.id}, {"$inc": {"balance": -data['total_price']}})
    await bot.send_message(ADMIN_ID, f"📦 **Buyurtma!**\nID: {message.from_user.id}\nXizmat: {data['srv_name']}\nLink: {message.text}")
    await message.answer(f"✅ Qabul qilindi!"); await state.clear()

# --- ADMIN PANEL & TO'LOV ---

@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("Admin Panel:", reply_markup=admin_menu)

@dp.message(F.text == "➕ Yangi xizmat qo'shish", F.from_user.id == ADMIN_ID)
async def add_srv_1(message: types.Message, state: FSMContext):
    await message.answer("Nomi:"); await state.set_state(ServiceState.waiting_for_name)

@dp.message(ServiceState.waiting_for_name)
async def add_srv_2(message: types.Message, state: FSMContext):
    await state.update_data(n=message.text); await message.answer("Min:"); await state.set_state(ServiceState.waiting_for_min)

@dp.message(ServiceState.waiting_for_min)
async def add_srv_3(message: types.Message, state: FSMContext):
    await state.update_data(m=int(message.text)); await message.answer("Narx (1k):"); await state.set_state(ServiceState.waiting_for_price)

@dp.message(ServiceState.waiting_for_price)
async def add_srv_4(message: types.Message, state: FSMContext):
    d = await state.get_data()
    await services_col.insert_one({"name": d['n'], "min_amount": d['m'], "price": float(message.text)})
    await message.answer("✅ Qo'shildi!"); await state.clear()

@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay(message: types.Message, state: FSMContext):
    await message.answer(f"💳 Karta: `{KARTA_RAQAMI}`\nChek yuboring."); await state.set_state(PaymentState.waiting_for_screenshot)

@dp.message(PaymentState.waiting_for_screenshot, F.photo)
async def check_h(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Tasdiqlash", callback_data=f"payadm_{message.from_user.id}")]])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"To'lov ID: {message.from_user.id}", reply_markup=kb)
    await message.answer("Yuborildi.")

@dp.callback_query(F.data.startswith("payadm_"))
async def adm_p(call: types.CallbackQuery, state: FSMContext):
    uid = int(call.data.split("_")[1]); await state.update_data(t_id=uid)
    await bot.send_message(ADMIN_ID, f"ID {uid} uchun summa:"); await state.set_state(AdminState.waiting_for_manual_amount); await call.answer()

@dp.message(AdminState.waiting_for_manual_amount)
async def adm_f(message: types.Message, state: FSMContext):
    d = await state.get_data()
    await users_col.update_one({"id": d['t_id']}, {"$inc": {"balance": float(message.text)}})
    await bot.send_message(d['t_id'], f"✅ +{message.text} so'm!"); await message.answer("Tayyor!"); await state.clear()

@dp.message(F.text == "🏠 Asosiy menyu")
async def home_back(message: types.Message):
    await message.answer("Menyu:", reply_markup=main_menu)

@dp.message(F.text == "🆘 Yordam")
async def help_s(message: types.Message, state: FSMContext):
    await message.answer("Xabar yozing:"); await state.set_state(HelpState.waiting_for_msg)

@dp.message(HelpState.waiting_for_msg)
async def help_admin(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 Xabar: {message.text}\nID: {message.from_user.id}"); await message.answer("Yuborildi."); await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())

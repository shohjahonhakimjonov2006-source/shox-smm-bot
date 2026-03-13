import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- KONFIGURATSIYA ---
TOKEN = "8473159649:AAHt9KnDd0aRDvthXrIE1sRWhP2u7DHpCnM"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- MONGODB ---
client = AsyncIOMotorClient(MONGO_URL)
db = client['bot_database']
users_col, services_col, categories_col = db['users'], db['services'], db['categories']
orders_col, settings_col = db['orders'], db['settings']

# --- HOLATLAR ---
class AdminState(StatesGroup):
    changing_card = State()
    add_category = State()
    add_service_name = State()
    add_service_price = State()

class UserOrder(StatesGroup):
    entering_details = State()

class PaymentState(StatesGroup):
    sending_receipt = State()
    entering_amount = State()

# --- KLAVIATURALAR ---
def main_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Buyurtma berish"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")]
    ], resize_keyboard=True)

def admin_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📁 Bo'limlar/Xizmatlar"), KeyboardButton(text="📈 Admin Statistika")],
        [KeyboardButton(text="📢 Yangilik yuborish"), KeyboardButton(text="💳 Kartani o'zgartirish")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- /ADMIN BUYRUG'I (XAR QANDAY HOLATDA ISHLAYDI) ---
@dp.message(Command("admin"))
async def admin_panel_force(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear() # Barcha bloklangan holatlarni yuvib tashlaydi
        await message.answer("🛠 **Admin Panelga majburiy kirish**\nBarcha holatlar tozalandi.", reply_markup=admin_menu_kb())

@dp.message(F.text == "🏠 Bosh menyu")
@dp.message(F.text == "⬅️ Ortga qaytish")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panelga qaytdingiz:", reply_markup=admin_menu_kb())
    else:
        await message.answer("Asosiy menyuga qaytdingiz:", reply_markup=main_menu())

@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    now = datetime.now()
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"last_seen": now.strftime("%Y-%m-%d"), "month": now.strftime("%Y-%m")},
         "$setOnInsert": {"balance": 0, "join_date": now.strftime("%Y-%m-%d")}},
        upsert=True
    )
    if u_id == ADMIN_ID:
        await message.answer("🛠 Admin panel:", reply_markup=admin_menu_kb())
    else:
        await message.answer("Xush kelibsiz!", reply_markup=main_menu())

# --- KARTANI O'ZGARTIRISH ---
@dp.message(F.text == "💳 Kartani o'zgartirish", F.from_user.id == ADMIN_ID)
async def card_start(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Yangi karta raqamini yozing:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga qaytish")]], resize_keyboard=True))
    await state.set_state(AdminState.changing_card)

@dp.message(AdminState.changing_card)
async def card_save(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Ortga qaytish": return await universal_back(message, state)
    await settings_col.update_one({"type": "card_info"}, {"$set": {"card": message.text}}, upsert=True)
    await message.answer(f"✅ Karta yangilandi: {message.text}", reply_markup=admin_menu_kb())
    await state.clear()

# --- ADMIN STATISTIKA ---
@dp.message(F.text == "📈 Admin Statistika", F.from_user.id == ADMIN_ID)
async def full_stats(message: types.Message):
    total = await users_col.count_documents({})
    today = await users_col.count_documents({"last_seen": datetime.now().strftime("%Y-%m-%d")})
    s = await settings_col.find_one({"type": "stats"})
    inflow = s.get("total_inflow", 0) if s else 0
    await message.answer(f"📊 **Statistika**\n\n👤 Jami: {total}\n🆕 Bugun faol: {today}\n💰 Jami tushum: {inflow:,} so'm")

# --- XIZMAT QO'SHISH (ESKILARI QOLADI) ---
@dp.message(F.text == "📁 Bo'limlar/Xizmatlar", F.from_user.id == ADMIN_ID)
async def cats_view(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bo'lim qo'shish", callback_data="add_c")],
        [InlineKeyboardButton(text="➕ Xizmat qo'shish", callback_data="add_s")]
    ])
    cats = await categories_col.find().to_list(100)
    res = "\n".join([f"• {c['name']}" for c in cats]) if cats else "Hali bo'lim yo'q"
    await message.answer(f"📂 **Bo'limlar:**\n{res}", reply_markup=kb)

@dp.callback_query(F.data == "add_s")
async def s_add_1(call: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(100)
    if not cats: return await call.answer("Avval bo'lim oching!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"scat_{c['name']}")] for c in cats])
    await call.message.answer("Qaysi bo'limga?", reply_markup=kb)

@dp.callback_query(F.data.startswith("scat_"))
async def s_add_2(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat=call.data.split("_")[1])
    await call.message.answer("Yangi xizmat nomi?")
    await state.set_state(AdminState.add_service_name)

@dp.message(AdminState.add_service_name)
async def s_add_3(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Narxi (raqamda)?")
    await state.set_state(AdminState.add_service_price)

@dp.message(AdminState.add_service_price)
async def s_add_4(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Raqam yozing!")
    d = await state.get_data()
    await services_col.insert_one({"category": d['cat'], "name": d['name'], "price": int(message.text)})
    await message.answer("✅ Yangi xizmat qo'shildi!", reply_markup=admin_menu_kb())
    await state.clear()

# --- TO'LOV TASDIQLASH (FIXED) ---
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_init(message: types.Message, state: FSMContext):
    c = await settings_col.find_one({"type": "card_info"})
    card = c['card'] if c else "8600..."
    await message.answer(f"Karta: `{card}`\nChek yuboring:", parse_mode="Markdown")
    await state.set_state(PaymentState.sending_receipt)

@dp.message(PaymentState.sending_receipt, F.photo)
async def pay_photo(message: types.Message, state: FSMContext):
    await state.update_data(p_id=message.photo[-1].file_id)
    await message.answer("Summa?")
    await state.set_state(PaymentState.entering_amount)

@dp.message(PaymentState.entering_amount)
async def pay_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Raqam yozing!")
    d = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiq", callback_data=f"ap_y_{message.from_user.id}_{message.text}")],
        [InlineKeyboardButton(text="❌ Rad", callback_data=f"ap_n_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, d['p_id'], caption=f"To'lov: {message.text}\nID: {message.from_user.id}", reply_markup=kb)
    await message.answer("Yuborildi!", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data.startswith("ap_"))
async def admin_decision(call: types.CallbackQuery):
    p = call.data.split("_")
    u_id = int(p[3])
    if p[2] == "y":
        amt = int(p[4])
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amt}})
        await settings_col.update_one({"type": "stats"}, {"$inc": {"total_inflow": amt}}, upsert=True)
        await bot.send_message(u_id, f"✅ Hisobingiz {amt} so'mga to'ldirildi!")
    else:
        await bot.send_message(u_id, "❌ To'lov rad etildi.")
    await call.message.edit_reply_markup(reply_markup=None)

# --- RUN ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

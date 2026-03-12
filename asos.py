import logging
import asyncio
import sqlite3
import aiohttp
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

logging.basicConfig(level=logging.INFO)

# --- MA'LUMOTLAR BAZASI ---
db = sqlite3.connect("smm_pro.db")
cursor = db.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, balance REAL DEFAULT 0)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS services (id INTEGER PRIMARY KEY, name TEXT, price REAL, min_qty INTEGER, max_qty INTEGER)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS orders (order_id TEXT, user_id INTEGER, service_name TEXT, quantity INTEGER, cost REAL)''')
db.commit()

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
    async with aiohttp.ClientSession() as session:
        async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as response:
            services = await response.json()
            if isinstance(services, list):
                cursor.execute("DELETE FROM services")
                for s in services:
                    cursor.execute("INSERT INTO services VALUES (?, ?, ?, ?, ?)", (s['service'], s['name'], float(s['rate']), int(s['min']), int(s['max'])))
                db.commit()
                await message.answer(f"✅ Xizmatlar yangilandi!")

# --- BOG'LANISH BO'LIMI ---
@dp.message(F.text == "👨‍💻 Bog'lanish")
async def support_start(message: types.Message, state: FSMContext):
    await message.answer("📑 Murojaat matnini yozib yuboring.")
    await state.set_state(SupportState.waiting_message)

@dp.message(SupportState.waiting_message)
async def support_finish(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 **Yangi murojaat!**\n\n👤 Kimdan: {message.from_user.full_name}\n🆔 ID: `{message.from_user.id}`\n\n📝 Matn: {message.text}")
    await message.answer("✅ Murojaatingiz yuborildi. Tez orada javob beramiz.")
    await state.clear()

# --- BUYURTMALARIM BO'LIMI ---
@dp.message(F.text == "📊 Buyurtmalarim")
async def my_orders(message: types.Message):
    cursor.execute("SELECT order_id, service_name, quantity, cost FROM orders WHERE user_id = ? ORDER BY rowid DESC LIMIT 10", (message.from_user.id,))
    rows = cursor.fetchall()
    if not rows:
        return await message.answer("Sizda hali buyurtmalar mavjud emas.")
    
    msg = "📊 **Oxirgi 10 ta buyurtmangiz:**\n\n"
    for r in rows:
        msg += f"🆔 ID: `{r[0]}`\n🔹 Xizmat: {r[1]}\n🔢 Miqdor: {r[2]}\n💰 Narx: {r[3]} so'm\n"
        msg += "⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
    await message.answer(msg, parse_mode="Markdown")

# --- BUYURTMA BERISH ---
@dp.message(F.text == "🚀 Buyurtma berish")
async def order_begin(message: types.Message):
    cursor.execute("SELECT id, name, price FROM services LIMIT 25")
    rows = cursor.fetchall()
    if not rows: return await message.answer("Xizmatlar topilmadi.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{r[1][:30]} | {r[2]} so'm", callback_data=f"order_{r[0]}")] for r in rows])
    await message.answer("Kerakli xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("order_"))
async def order_step1(callback: types.CallbackQuery, state: FSMContext):
    s_id = callback.data.split("_")[1]
    cursor.execute("SELECT name, price, min_qty, max_qty FROM services WHERE id = ?", (s_id,))
    s = cursor.fetchone()
    await state.update_data(s_id=s_id, s_name=s[0], s_price=s[1], min_q=s[2], max_q=s[3])
    await callback.message.answer(f"📌 {s[0]}\n💸 1000 tasi: {s[1]} so'm\n\n🔗 Havolani yuboring:")
    await state.set_state(OrderState.entering_link)

@dp.message(OrderState.entering_link)
async def order_step2(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    data = await state.get_data()
    await message.answer(f"🔢 Miqdorni kiriting (Min: {data['min_q']} | Max: {data['max_q']}):")
    await state.set_state(OrderState.entering_quantity)

@dp.message(OrderState.entering_quantity)
async def order_step3(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Raqam kiriting!")
    qty = int(message.text)
    data = await state.get_data()
    total = (data['s_price'] / 1000) * qty
    
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    balance = cursor.fetchone()[0]
    
    if balance < total: return await message.answer("Hisobingizda mablag' yetarli emas!")

    async with aiohttp.ClientSession() as session:
        params = {'key': SMM_API_KEY, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}
        async with session.post(SMM_API_URL, data=params) as resp:
            res = await resp.json()
            if 'order' in res:
                cursor.execute("UPDATE users SET balance = balance - ? WHERE user_id = ?", (total, message.from_user.id))
                cursor.execute("INSERT INTO orders VALUES (?, ?, ?, ?, ?)", (res['order'], message.from_user.id, data['s_name'], qty, total))
                db.commit()
                await message.answer(f"✅ Buyurtma qabul qilindi!\n🆔 ID: {res['order']}")
            else:
                await message.answer("❌ Xatolik yuz berdi. Keyinroq urinib ko'ring.")
    await state.clear()

# --- BALANS TO'LDIRISH VA BOSHQA FUNKSIYALAR ---
@dp.message(F.text == "💰 Balans to'ldirish")
async def bal_start(message: types.Message):
    msg = f"To'lov tizimi: 🔹 Payme\n\nKarta: `{KARTA_RAQAM}`\nID: `{message.from_user.id}`\n\nChekni yuboring va kuting."
    await message.answer(msg, reply_markup=payment_kb, parse_mode="Markdown")

@dp.callback_query(F.data == "pay_done")
async def pay_confirm(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("💵 To'lov miqdorini kiriting:")
    await state.set_state(PaymentState.entering_amount)

@dp.message(PaymentState.entering_amount)
async def pay_amt(message: types.Message, state: FSMContext):
    await state.update_data(amt=message.text)
    await message.answer("📸 Screenshot yuboring:")
    await state.set_state(PaymentState.sending_screenshot)

@dp.message(PaymentState.sending_screenshot, F.photo)
async def pay_photo(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, caption=f"💰 To'lov!\nID: `{message.from_user.id}`\nSumma: {data['amt']}")
    await message.answer("✅ Yuborildi. Admin tasdiqlashini kuting.")
    await state.clear()

@dp.message(F.text == "💸 Balans qo'shish")
async def adm_add_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await message.answer("User ID:")
        await state.set_state(AdminState.add_bal_id)

@dp.message(AdminState.add_bal_id)
async def adm_add_id(message: types.Message, state: FSMContext):
    await state.update_data(uid=message.text)
    await message.answer("Summa:")
    await state.set_state(AdminState.add_bal_amount)

@dp.message(AdminState.add_bal_amount)
async def adm_add_fin(message: types.Message, state: FSMContext):
    data = await state.get_data()
    cursor.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (float(message.text), data['uid']))
    db.commit()
    await message.answer("✅ Tayyor.")
    await state.clear()

@dp.message(F.text == "👤 Profil")
async def user_prof(message: types.Message):
    cursor.execute("SELECT balance FROM users WHERE user_id = ?", (message.from_user.id,))
    res = cursor.fetchone()
    await message.answer(f"🆔 ID: `{message.from_user.id}`\n💰 Balans: {res[0]} so'm")

@dp.message(F.text == "🏠 Asosiy menyu")
async def home_back(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

@dp.message(Command("start"))
async def start_handler(message: types.Message):
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
    db.commit()
    await message.answer("Xush kelibsiz!", reply_markup=main_menu)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
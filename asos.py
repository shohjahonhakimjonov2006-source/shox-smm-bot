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

# --- MONGODB ULANISHI ---
client = AsyncIOMotorClient(MONGO_URL)
db = client['bot_database']
users_col = db['users']
services_col = db['services']
categories_col = db['categories']
orders_col = db['orders']
settings_col = db['settings']

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
    kb = [
        [KeyboardButton(text="🛒 Buyurtma berish"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu_kb():
    kb = [
        [KeyboardButton(text="📁 Bo'limlar/Xizmatlar"), KeyboardButton(text="📈 Admin Statistika")],
        [KeyboardButton(text="📢 Yangilik yuborish"), KeyboardButton(text="💳 Kartani o'zgartirish")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# --- START ---
@dp.message(Command("start"))
@dp.message(F.text == "⬅️ Ortga qaytish")
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    now = datetime.now()
    
    # Userni bazaga qo'shish yoki yangilash
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"last_seen": now.strftime("%Y-%m-%d"), "month": now.strftime("%Y-%m")},
         "$setOnInsert": {"balance": 0, "join_date": now.strftime("%Y-%m-%d"), "total_spent": 0}},
        upsert=True
    )
    
    if u_id == ADMIN_ID and message.text != "⬅️ Ortga qaytish":
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_menu_kb())
    else:
        await message.answer("Xizmat ko'rsatish botiga xush kelibsiz!", reply_markup=main_menu())

# --- FOYDALANUVCHI STATISTIKASI (YANGILANDI) ---
@dp.message(F.text == "📊 Statistika")
async def user_stats(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")
    
    # Bugun botdan foydalanganlar
    today_count = await users_col.count_documents({"last_seen": today})
    # Shu oy foydalanganlar
    month_count = await users_col.count_documents({"month": this_month})
    
    # Jami kiritilgan summa (Admin tasdiqlagan barcha to'lovlar yig'indisi)
    settings = await settings_col.find_one({"type": "stats"})
    total_inflow = settings.get("total_inflow", 0) if settings else 0

    text = (
        "📊 **Bot Statistikasi**\n\n"
        f"👤 Bugun botdan foydalandi: {today_count} kishi\n"
        f"📅 Shu oyda faol bo'lganlar: {month_count} kishi\n"
        f"💰 Botga jami kiritilgan mablag': {total_inflow:,} so'm\n\n"
        "Sizga sifatli xizmat ko'rsatishdan mamnunmiz!"
    )
    await message.answer(text)

# --- HISOBNI TO'LDIRISH (TASDIQLASH TUZATILDI) ---
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_start(message: types.Message, state: FSMContext):
    card_data = await settings_col.find_one({"type": "card_info"})
    card = card_data['card'] if card_data else "8600 0000 0000 0000"
    await message.answer(f"💳 To'lov uchun karta: `{card}`\n\nTo'lov qilgach, chekni (rasm) va summani yuboring.", 
                         parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga qaytish")]], resize_keyboard=True))
    await state.set_state(PaymentState.sending_receipt)

@dp.message(PaymentState.sending_receipt, F.photo)
async def pay_receipt(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("To'lov summasini kiriting (faqat raqam):")
    await state.set_state(PaymentState.entering_amount)

@dp.message(PaymentState.entering_amount)
async def pay_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Iltimos, faqat raqam kiriting!")
    
    data = await state.get_data()
    u_id = message.from_user.id
    amount = message.text
    
    # Callback_data uzunligi chegaralangan, shuning uchun "pay|y|user_id|amount" formatidan foydalanamiz
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay:y:{u_id}:{amount}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay:n:{u_id}:0")]
    ])
    
    await bot.send_photo(ADMIN_ID, data['photo_id'], 
                         caption=f"💰 To'lov so'rovi\nID: {u_id}\nSumma: {amount} so'm", 
                         reply_markup=kb)
    await message.answer("✅ Chek adminga yuborildi, tasdiqlashni kuting.", reply_markup=main_menu())
    await state.clear()

# --- ADMIN: TO'LOVNI TASDIQLASH HANDLERI (TUZATILDI) ---
@dp.callback_query(F.data.startswith("pay:"))
async def admin_pay_approve(callback: types.CallbackQuery):
    # Callbackni ajratib olish
    _, res, u_id, amt = callback.data.split(":")
    u_id = int(u_id)
    amt = int(amt)

    if res == "y":
        # Foydalanuvchi balansini oshirish
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amt}})
        # Umumiy tushumni (stats) oshirish
        await settings_col.update_one({"type": "stats"}, {"$inc": {"total_inflow": amt}}, upsert=True)
        
        try:
            await bot.send_message(u_id, f"✅ To'lovingiz tasdiqlandi! Hisobingizga {amt:,} so'm qo'shildi.")
            await callback.answer("To'lov tasdiqlandi", show_alert=True)
        except:
            pass
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n✅ TASDIQLANDI")
    else:
        try:
            await bot.send_message(u_id, "❌ To'lovingiz rad etildi. Chek noto'g'ri yoki summa mos emas.")
            await callback.answer("To'lov rad etildi", show_alert=True)
        except:
            pass
        await callback.message.edit_caption(caption=callback.message.caption + "\n\n❌ RAD ETILDI")
    
    # Tugmalarni olib tashlash
    await callback.message.edit_reply_markup(reply_markup=None)

# --- QOLGAN FUNKSIYALAR ---
@dp.message(F.text == "🏠 Bosh menyu")
async def go_home(message: types.Message):
    await message.answer("Asosiy menyu:", reply_markup=main_menu())

# --- RUN ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

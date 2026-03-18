import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiohttp import web

# --- KONFIGURATSIYA ---
TOKEN = "8678413684:AAGlG1FRn8l960oCDKRrnKigcuUxi0nwEhM"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- DATABASE ---
client = AsyncIOMotorClient(MONGO_URL)
db = client["smm_bot_v2"]
users_col = db["users"]
services_col = db["services"]
categories_col = db["categories"]
orders_col = db["orders"]
settings_col = db["settings"]
payments_col = db["payments"]

# --- STATES ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    add_card_num = State()
    edit_user_id = State()
    edit_user_amount = State()
    broadcast_msg = State()

class UserState(StatesGroup):
    order_link = State()
    order_quantity = State()
    fill_balance_amount = State()
    upload_receipt = State()

# --- KEYBOARDS ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📦 Buyurtmalarim")],
        [KeyboardButton(text="🆘 Yordam")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📂 Bo'lim/Xizmatlar"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="👤 Balans tahrirlash"), KeyboardButton(text="📢 Xabar yuborish")],
            [KeyboardButton(text="🏠 Bosh menyu")]
        ], resize_keyboard=True
    )

# --- START ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"full_name": message.from_user.full_name},
         "$setOnInsert": {"balance": 0, "total_in": 0}},
        upsert=True
    )
    await message.answer(f"Assalomu alaykum, {message.from_user.full_name}!\nSMM xizmatlar botiga xush kelibsiz.", 
                         reply_markup=main_kb(u_id))

# --- USER: SERVICES & ORDERING ---
@dp.message(F.text == "🛒 Xizmatlar")
async def show_categories(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats:
        return await message.answer("Hozircha bo'limlar yo'q.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c['name'], callback_data=f"user_cat_{c['_id']}")] for c in cats
    ])
    await message.answer("📁 Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("user_cat_"))
async def show_services_user(call: types.CallbackQuery):
    cat_id = call.data.split("_")[2]
    servs = await services_col.find({"cat_id": cat_id}).to_list(None)
    if not servs:
        return await call.answer("Bu bo'limda xizmatlar yo'q.", show_alert=True)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"buy_serv_{s['_id']}")] for s in servs
    ])
    await call.message.edit_text("✨ Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_serv_"))
async def process_buy(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[2]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    await state.update_data(s_id=s_id, s_price=service['price'], s_name=service['name'])
    await call.message.answer(f"💠 Xizmat: {service['name']}\n💵 Narxi: {service['price']} so'm (1000 ta uchun)\n\n🔗 Havolani (link) yuboring:")
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link)
async def process_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Qancha buyurtma qilmoqchisiz? (Masalan: 500)")
    await state.set_state(UserState.order_quantity)

@dp.message(UserState.order_quantity)
async def process_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Faqat raqam kiriting!")
    
    qty = int(message.text)
    data = await state.get_data()
    total_price = (data['s_price'] / 1000) * qty
    
    user = await users_col.find_one({"user_id": message.from_user.id})
    if user['balance'] < total_price:
        return await message.answer(f"❌ Mablag' yetarli emas!\nKerak: {total_price:,} so'm\nBalansingiz: {user['balance']:,} so'm")

    # Buyurtmani saqlash
    order = {
        "user_id": message.from_user.id,
        "service": data['s_name'],
        "link": data['link'],
        "qty": qty,
        "price": total_price,
        "status": "Jarayonda",
        "date": datetime.now().strftime("%Y-%m-%d %H:%M")
    }
    await orders_col.insert_one(order)
    await users_col.update_one({"user_id": message.from_user.id}, {"$inc": {"balance": -total_price}})
    
    await message.answer(f"✅ Buyurtma qabul qilindi!\n💰 Narxi: {total_price:,} so'm\nBalansdan chegirildi.")
    await bot.send_message(ADMIN_ID, f"🔔 Yangi buyurtma!\nUser: {message.from_user.id}\nXizmat: {data['s_name']}\nLink: {data['link']}")
    await state.clear()

# --- USER: BALANCE ---
@dp.message(F.text == "💰 Balans")
async def show_balance(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"👤 Foydalanuvchi: {message.from_user.full_name}\n💰 Balans: {user['balance']:,} so'm")

@dp.message(F.text == "💳 Hisobni to'ldirish")
async def fill_bal_start(message: types.Message, state: FSMContext):
    await message.answer("To'lov miqdorini kiriting (so'mda):")
    await state.set_state(UserState.fill_balance_amount)

@dp.message(UserState.fill_balance_amount)
async def fill_bal_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Raqam kiriting!")
    await state.update_data(amount=int(message.text))
    await message.answer("💳 To'lovni amalga oshiring:\n`8600123456789012` (Zoirbek)\n\nTo'lovdan so'ng chekni (rasm) yuboring:", parse_mode="Markdown")
    await state.set_state(UserState.upload_receipt)

@dp.message(UserState.upload_receipt, F.photo)
async def fill_bal_done(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await message.answer("✅ Chek qabul qilindi! Admin tasdiqlashini kuting.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_yes_{message.from_user.id}_{data['amount']}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_no_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, message.photo[-1].file_id, 
                         caption=f"💰 To'lov!\nID: {message.from_user.id}\nSumma: {data['amount']:,} so'm", reply_markup=kb)
    await state.clear()

# --- ADMIN: PAYMENT CONFIRM ---
@dp.callback_query(F.data.startswith("pay_"))
async def admin_pay_confirm(call: types.CallbackQuery):
    parts = call.data.split("_")
    action, u_id, amount = parts[1], int(parts[2]), int(parts[3]) if len(parts)>3 else 0
    
    if action == "yes":
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amount, "total_in": amount}})
        await bot.send_message(u_id, f"✅ To'lovingiz tasdiqlandi! Balansingizga {amount:,} so'm qo'shildi.")
        await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI")
    else:
        await bot.send_message(u_id, "❌ To'lovingiz bekor qilindi. Ma'lumotni tekshiring.")
        await call.message.edit_caption(caption=call.message.caption + "\n\n❌ BEKOR QILINDI")

# --- ADMIN: NAVIGATION ---
@dp.message(F.text == "🛠 Admin Panel", F.from_user.id == ADMIN_ID)
async def admin_main(message: types.Message):
    await message.answer("Boshqaruv paneli:", reply_markup=admin_kb())

@dp.message(F.text == "🏠 Bosh menyu")
async def back_main(message: types.Message):
    await message.answer("Bosh menyu", reply_markup=main_kb(message.from_user.id))

# --- SERVER RUN ---
async def handle(request): return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

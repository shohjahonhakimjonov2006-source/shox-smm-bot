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

# --- MONGODB ---
client = AsyncIOMotorClient(MONGO_URL)
db = client["smm_bot"]
users_col = db["users"]
services_col = db["services"]
categories_col = db["categories"]
orders_col = db["orders"]
settings_col = db["settings"]
promo_col = db["promo_codes"]
payments_col = db["payments"]

# --- STATES ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    add_card_num = State()
    edit_user_id = State()
    edit_user_balance = State()
    broadcast_msg = State()
    set_daily_bonus = State()

class UserState(StatesGroup):
    order_link = State()
    pay_photo = State()
    pay_sum = State()
    help_msg = State()
    enter_promo = State()

# --- KEYBOARDS ---
def main_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
            [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🎁 Bonuslar"), KeyboardButton(text="🆘 Yordam")]
        ], resize_keyboard=True
    )

def admin_kb():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📂 Bo'lim/Xizmatlar"), KeyboardButton(text="📊 Admin Statistika")],
            [KeyboardButton(text="💳 Karta sozlamalari"), KeyboardButton(text="👤 Balans tahrirlash")],
            [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🎟 Bonus sozlamalari")],
            [KeyboardButton(text="🏠 Bosh menyu")]
        ], resize_keyboard=True
    )

# --- START & ADMIN COMMANDS ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"full_name": message.from_user.full_name, "last_seen": today},
         "$setOnInsert": {"balance": 0, "total_in": 0, "last_daily": None}},
        upsert=True
    )
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}!", reply_markup=main_kb())

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_kb())

@dp.message(F.text == "🏠 Bosh menyu")
async def back_to_main(message: types.Message):
    await message.answer("Bosh menyu tanlandi", reply_markup=main_kb())

# --- ADMIN: BO'LIM VA XIZMATLAR (TO'G'RILANDI) ---
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def admin_services_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Bo‘lim", callback_data="add_cat")],
        [InlineKeyboardButton(text="➕ Yangi Xizmat", callback_data="add_service")]
    ])
    await message.answer("📂 Bo'limlar va Xizmatlar boshqaruvi:", reply_markup=kb)

@dp.callback_query(F.data == "add_cat")
async def add_cat_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🆕 Yangi bo‘lim nomini kiriting:")
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat)
async def add_cat_save(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ Bo'lim qo'shildi: {message.text}")
    await state.clear()

@dp.callback_query(F.data == "add_service")
async def add_serv_start(call: types.CallbackQuery):
    cats = await categories_col.find().to_list(None)
    if not cats:
        return await call.message.answer("❌ Avval bo'lim qo'shishingiz kerak!")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=c['name'], callback_data=f"selcat_{c['_id']}")] for c in cats
    ])
    await call.message.answer("Xizmat qaysi bo'limga qo'shilsin?", reply_markup=kb)

@dp.callback_query(F.data.startswith("selcat_"))
async def add_serv_name(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split("_")[1]
    await state.update_data(cat_id=cat_id)
    await call.message.answer("🛠 Xizmat nomini kiriting:")
    await state.set_state(AdminState.add_serv_name)

@dp.message(AdminState.add_serv_name)
async def add_serv_price(message: types.Message, state: FSMContext):
    await state.update_data(s_name=message.text)
    await message.answer("💰 Xizmat narxini kiriting (faqat raqam):")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price)
async def add_serv_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Narx faqat raqam bo'lishi kerak!")
    data = await state.get_data()
    await services_col.insert_one({
        "cat_id": data['cat_id'],
        "name": data['s_name'],
        "price": int(message.text)
    })
    await message.answer(f"✅ Xizmat qo'shildi: {data['s_name']}")
    await state.clear()

# --- ADMIN: KARTA SOZLAMALARI (TO'G'RILANDI) ---
@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def card_settings(message: types.Message):
    cards = await settings_col.find({"type": "card"}).to_list(None)
    text = "💳 **Hozirgi kartalar:**\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="add_card")]])
    for c in cards:
        text += f"🔹 `{c['number']}`\n"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"🗑 O'chirish: {c['number'][:4]}...", callback_data=f"del_card_{c['_id']}")])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("del_card_"))
async def delete_card(call: types.CallbackQuery):
    card_id = call.data.split("_")[2]
    await settings_col.delete_one({"_id": ObjectId(card_id)})
    await call.answer("✅ Karta o'chirildi")
    await card_settings(call.message)

# --- ADMIN: BONUS SOZLAMALARI (TO'G'RILANDI) ---
@dp.message(F.text == "🎟 Bonus sozlamalari", F.from_user.id == ADMIN_ID)
async def bonus_settings(message: types.Message):
    bonus = await settings_col.find_one({"type": "daily_bonus"})
    val = bonus['sum'] if bonus else 0
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="💰 Bonusni o'zgartirish", callback_data="edit_bonus")]])
    await message.answer(f"🎁 Hozirgi kunlik bonus: **{val} so'm**", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "edit_bonus")
async def edit_bonus_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bonus miqdorini yuboring (raqam):")
    await state.set_state(AdminState.set_daily_bonus)

@dp.message(AdminState.set_daily_bonus)
async def edit_bonus_save(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("❌ Faqat raqam kiriting!")
    await settings_col.update_one({"type": "daily_bonus"}, {"$set": {"sum": int(message.text)}}, upsert=True)
    await message.answer(f"✅ Kunlik bonus {message.text} so'mga o'rnatildi.")
    await state.clear()

# --- ADMIN: STATISTIKA (TO'G'RILANDI) ---
@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_full_stats(message: types.Message):
    total_u = await users_col.count_documents({})
    all_in = await users_col.aggregate([{"$group": {"_id": None, "s": {"$sum": "$total_in"}}}]).to_list(1)
    all_bal = await users_col.aggregate([{"$group": {"_id": None, "s": {"$sum": "$balance"}}}]).to_list(1)
    
    text = (
        f"📊 **Botning Umumiy Statistikasi:**\n\n"
        f"👥 Jami foydalanuvchilar: {total_u}\n"
        f"💰 Jami tushum: {all_in[0]['s'] if all_in else 0:,} so'm\n"
        f"💳 Jami qolgan balans: {all_bal[0]['s'] if all_bal else 0:,} so'm"
    )
    await message.answer(text, parse_mode="Markdown")

# --- FOYDALANUVCHI QISMI (XIZMATLAR VA BALANS) ---
@dp.message(F.text == "🛒 Xizmatlar")
async def services_view(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats:
        return await message.answer("😔 Hozircha xizmatlar mavjud emas.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c["name"], callback_data=f"cat_{c['_id']}")] for c in cats])
    await message.answer("📁 Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    services = await services_col.find({"cat_id": cat_id}).to_list(None)
    if not services:
        return await call.message.answer("Bu bo‘limda xizmatlar yo'q")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']:,} so'm", callback_data=f"buy_{s['_id']}")] for s in services])
    await call.message.answer("✨ Xizmatni tanlang:", reply_markup=kb)

@dp.message(F.text == "💰 Balans")
async def balance(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"💰 **Balansingiz:** {user.get('balance', 0):,} so'm\n📥 **Jami to'lovlar:** {user.get('total_in', 0):,} so'm", parse_mode="Markdown")

# --- QOLGAN FUNKSIYALAR (HISOB TO'LDIRISH, YORDAM VA HOKAZO...) ---
# (Siz yuborgan koddagi refill_start, help_user kabi funksiyalar bu yerda davom etishi mumkin)

# --- SERVER VA START ---
async def handle(request): return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

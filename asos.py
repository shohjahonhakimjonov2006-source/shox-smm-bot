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
TOKEN = "8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo"
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
    add_serv_name = State()
    add_serv_price = State()
    broadcast_msg = State()

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
            [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🏠 Bosh menyu")]
        ], resize_keyboard=True
    )

# --- HANDLERS ---

@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")

    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"full_name": message.from_user.full_name, "last_seen": today},
         "$setOnInsert": {"balance": 0, "total_in": 0, "last_daily": None, "used_promos": [], "orders_today": 0}},
        upsert=True
    )
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}!", reply_markup=main_kb())
    if u_id == ADMIN_ID:
        await message.answer("🛠 Admin panelga kirish: /admin", reply_markup=admin_kb())

@dp.message(F.text == "🏠 Bosh menyu")
async def back_to_main(message: types.Message):
    await message.answer("Bosh menyu", reply_markup=main_kb())

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_kb())

@dp.message(F.text == "💰 Balans")
async def balance(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    today = datetime.now().strftime("%Y-%m-%d")
    today_orders = await orders_col.count_documents({"user_id": message.from_user.id, "date": today})

    text = (
        f"💰 Sizning balansingiz:\n"
        f"Hisob: {user.get('balance', 0):,} so'm\n"
        f"Botga kiritgan jami summa: {user.get('total_in', 0):,} so'm\n"
        f"Bugun bergan buyurtmalaringiz: {today_orders} ta"
    )
    await message.answer(text)

@dp.message(F.text == "🛒 Xizmatlar")
async def services(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats:
        await message.answer("Hozircha bo'limlar yo'q")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for c in cats:
        kb.inline_keyboard.append([InlineKeyboardButton(text=c["name"], callback_data=f"cat_{c['_id']}")])
    await message.answer("Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    services = await services_col.find({"cat_id": cat_id}).to_list(None)

    if not services:
        await call.answer("Bu bo‘limda xizmatlar mavjud emas", show_alert=True)
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for s in services:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{s['name']} - {s['price']:,} so'm", callback_data=f"buy_{s['_id']}")])
    
    await call.message.edit_text("Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_service(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})

    if user["balance"] < service["price"]:
        await call.answer("❌ Balans yetarli emas!", show_alert=True)
        return

    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await call.message.answer(f"🔗 {service['name']} uchun havola yoki xabar yuboring:")
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link)
async def order_link(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = await users_col.find_one({"user_id": message.from_user.id})
    
    # Balansni tekshirish (yana bir bor)
    if user['balance'] < data['s_price']:
        await message.answer("Xatolik: Balans yetarli emas.")
        return await state.clear()

    await users_col.update_one({"user_id": message.from_user.id}, {"$inc": {"balance": -data['s_price']}})
    today = datetime.now().strftime("%Y-%m-%d")

    order = await orders_col.insert_one({
        "user_id": message.from_user.id,
        "user_name": message.from_user.full_name,
        "service_name": data['s_name'],
        "link": message.text,
        "price": data['s_price'],
        "status": "pending",
        "date": today
    })

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"ord_ok_{order.inserted_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"ord_no_{order.inserted_id}")
    ]])

    await bot.send_message(ADMIN_ID,
                           f"📦 Yangi buyurtma!\n\n👤 Foydalanuvchi: {message.from_user.full_name}\n🆔 ID: {message.from_user.id}\n"
                           f"🛠 Xizmat: {data['s_name']}\n🔗 Havola: {message.text}\n💰 Summa: {data['s_price']:,} so'm",
                           reply_markup=kb)
    await message.answer("✅ Buyurtmangiz qabul qilindi!", reply_markup=main_kb())
    await state.clear()

# --- ADMIN PROCESS ORDERS ---
@dp.callback_query(F.data.startswith("ord_ok_"))
async def admin_confirm(call: types.CallbackQuery):
    order_id = call.data.split("_")[2]
    order = await orders_col.find_one({"_id": ObjectId(order_id)})
    if order and order['status'] == "pending":
        await orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "completed"}})
        await bot.send_message(order['user_id'], f"✅ Sizning '{order['service_name']}' buyurtmangiz bajarildi!")
        await call.message.edit_text(call.message.text + "\n\n✅ TASDIQLANDI")
    else:
        await call.answer("Buyurtma allaqachon bajarilgan yoki topilmadi")

# --- ADMIN PANEL LOGIC ---
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def admin_services_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("➕ Yangi Bo‘lim", callback_data="add_cat")],
        [InlineKeyboardButton("➕ Yangi Xizmat", callback_data="add_service")]
    ])
    await message.answer("Boshqaruv:", reply_markup=kb)

@dp.callback_query(F.data == "add_cat")
async def add_category(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo‘lim nomini kiriting:")
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat)
async def save_category(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ Bo‘lim qo‘shildi: {message.text}", reply_markup=admin_kb())
    await state.clear()

@dp.callback_query(F.data == "add_service")
async def add_service_start(call: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(None)
    if not cats:
        return await call.message.answer("Avval bo'lim oching!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(c['name'], callback_data=f"asel_{c['_id']}")] for c in cats])
    await call.message.answer("Qaysi bo'limga xizmat qo'shamiz?", reply_markup=kb)

@dp.callback_query(F.data.startswith("asel_"))
async def select_cat_admin(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split("_")[1]
    await state.update_data(cat_id=cat_id)
    await call.message.answer("Xizmat nomini kiriting:")
    await state.set_state(AdminState.add_serv_name)

@dp.message(AdminState.add_serv_name)
async def save_serv_name(message: types.Message, state: FSMContext):
    await state.update_data(s_name=message.text)
    await message.answer("Narxini kiriting (faqat raqam):")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price)
async def save_serv_price(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Faqat raqam kiriting!")
    data = await state.get_data()
    await services_col.insert_one({"cat_id": data['cat_id'], "name": data['s_name'], "price": int(message.text)})
    await message.answer("✅ Xizmat saqlandi!", reply_markup=admin_kb())
    await state.clear()

# --- WEB SERVER (for Render/Heroku) ---
async def handle(request): 
    return web.Response(text="Bot is Running")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

async def main():
    asyncio.create_task(start_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")

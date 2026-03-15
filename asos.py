import asyncio
import logging
import os
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiohttp import web

# --- KONFIGURATSIYA ---
TOKEN = "8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
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
promo_col = db['promo_codes']

# --- HOLATLAR (States) ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    add_card_name = State()
    add_card_num = State()
    edit_user_id = State()
    edit_user_balance = State()
    broadcast_msg = State()
    add_promo_code = State()
    add_promo_sum = State()
    add_promo_limit = State()
    set_daily_amount = State()

class UserState(StatesGroup):
    order_link = State()
    pay_photo = State()
    pay_sum = State()
    help_msg = State()
    enter_promo = State()

# --- KLAVIATURALAR ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🎁 Bonuslar"), KeyboardButton(text="🆘 Yordam")]
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim/Xizmatlar"), KeyboardButton(text="📊 Admin Statistika")],
        [KeyboardButton(text="💳 Karta sozlamalari"), KeyboardButton(text="👤 Balans tahrirlash")],
        [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🎟 Bonus sozlamalari")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- START ---
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

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 **Admin paneliga xush kelibsiz!**", reply_markup=admin_kb())

# --- ADMIN: XIZMATLAR BOSHQARUVI ---
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def admin_serv_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Bo'lim", callback_data="add_cat_start")],
        [InlineKeyboardButton(text="➕ Yangi Xizmat", callback_data="add_serv_start")]
    ])
    await message.answer("Xizmatlar va bo'limlarni boshqarish:", reply_markup=kb)

@dp.callback_query(F.data == "add_cat_start")
async def add_cat_step1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomini yozing:")
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat)
async def add_cat_step2(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ Bo'lim qo'shildi: {message.text}")
    await state.clear()

# --- FOYDALANUVCHI: BUYURTMA BERISH ---
@dp.callback_query(F.data.startswith("ubuy_"))
async def user_buy_step1(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})
    if user['balance'] < service['price']:
        return await call.answer("❌ Mablag' yetarli emas!", show_alert=True)
    await state.update_data(s_id=s_id, s_price=service['price'], s_name=service['name'])
    await call.message.answer(f"🔗 {service['name']} uchun havola (link) yoki xabar yuboring:")
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link)
async def user_buy_step2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    u_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['s_price']}})
    order_id = await orders_col.insert_one({
        "user_id": u_id, "user_name": message.from_user.full_name, "service_name": data['s_name'],
        "link": message.text, "price": data['s_price'], "status": "pending", "date": today
    })
    
    today_count = await orders_col.count_documents({"date": today})
    user_upd = await users_col.find_one({"user_id": u_id})
    admin_text = (
        f"📦 **Yangi Buyurtma!**\n\n🔢 Bugungi jami: {today_count}\n👤 Foydalanuvchi: {message.from_user.full_name}\n"
        f"🆔 ID: `{u_id}`\n🛠 Xizmat: {data['s_name']}\n🔗 Havola: {message.text}\n💰 Summa: {data['s_price']:,} so'm\n💳 Qolgan balans: {user_upd['balance']:,} so'm"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ord_ok_{order_id.inserted_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"ord_no_{order_id.inserted_id}")]
    ])
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb)
    await message.answer("✅ Buyurtmangiz qabul qilindi va adminga yuborildi.", reply_markup=main_kb())
    await state.clear()

# --- ADMIN: BUYURTMANI TASDIQLASH ---
@dp.callback_query(F.data.startswith("ord_ok_"))
async def admin_confirm_order(call: types.CallbackQuery):
    o_id = call.data.split("_")[2]
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if order['status'] != "pending": return await call.answer("Ko'rib bo'lingan.")
    await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "completed"}})
    await bot.send_message(order['user_id'], f"✅ Sizning '{order['service_name']}' buyurtmangiz bajarildi!")
    await call.message.edit_text(call.message.text + "\n\n✅ **BAJARILDI**")

# --- FOYDALANUVCHI: STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def user_full_stats(message: types.Message):
    u_id = message.from_user.id
    user = await users_col.find_one({"user_id": u_id})
    today = datetime.now().strftime("%Y-%m-%d")
    this_month = datetime.now().strftime("%Y-%m")
    
    u_today_orders = await orders_col.count_documents({"user_id": u_id, "date": today})
    total_users_today = await users_col.count_documents({"last_seen": today})
    total_users_month = await users_col.count_documents({"last_seen": {"$regex": f"^{this_month}"}})
    bot_today_orders = await orders_col.count_documents({"date": today, "status": "completed"})
    
    text = (
        f"📊 **Bot Statistikasi**\n\n"
        f"👥 Bugun foydalanganlar: {total_users_today}\n"
        f"📅 Shu oyda foydalanganlar: {total_users_month}\n"
        f"✅ Bugun bajarilgan buyurtmalar: {bot_today_orders}\n\n"
        f"👤 **Sizning hisobingiz:**\n"
        f"💰 Hozirgi balans: {user['balance']:,} so'm\n"
        f"📥 Jami kiritilgan summa: {user['total_in']:,} so'm\n"
        f"📦 Bugungi buyurtmalaringiz: {u_today_orders} ta"
    )
    await message.answer(text)

# --- ADMIN: KARTANI BOSHQARISH ---
@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def admin_card_manage(message: types.Message):
    cards = await settings_col.find({"type": "card"}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    text = "💳 **To'lov kartalari:**\n\n"
    if not cards: text += "Kartalar yo'q."
    for c in cards:
        text += f"🔹 {c['name']}: `{c['number']}`\n"
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"❌ {c['name']}ni o'chirish", callback_data=f"delcard_{c['_id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="addcard_start")])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "addcard_start")
async def addcard_1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Karta egasi va nomi (Masalan: Uzcard - Ali):")
    await state.set_state(AdminState.add_card_name)

@dp.message(AdminState.add_card_name)
async def addcard_2(message: types.Message, state: FSMContext):
    await state.update_data(cname=message.text)
    await message.answer("Karta raqamini yozing:")
    await state.set_state(AdminState.add_card_num)

@dp.message(AdminState.add_card_num)
async def addcard_3(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await settings_col.insert_one({"type": "card", "name": data['cname'], "number": message.text})
    await message.answer("✅ Karta muvaffaqiyatli qo'shildi.")
    await state.clear()

# --- ADMIN: STATISTIKA VA TOZALASH ---
@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_full_stat_panel(message: types.Message):
    total_u = await users_col.count_documents({})
    pipeline = [{"$sort": {"total_in": -1}}, {"$limit": 10}]
    top_10 = await users_col.aggregate(pipeline).to_list(10)
    
    all_in = await users_col.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$total_in"}}}]).to_list(1)
    all_bal = await users_col.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$balance"}}}]).to_list(1)
    
    t_in = all_in[0]['sum'] if all_in else 0
    t_bal = all_bal[0]['sum'] if all_bal else 0
    
    stat_text = f"📊 **Umumiy Statistika**\n👥 Jami userlar: {total_u}\n💰 Jami tushum: {t_in:,} so'm\n💳 Ishlatilmagan pullar: {t_bal:,} so'm\n\n🏆 **Top 10 To'lovchilar:**\n"
    for i, u in enumerate(top_10, 1):
        stat_text += f"{i}. {u['full_name']} - {u['total_in']:,} so'm\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Statistikani tozalash", callback_data="clear_stats")]])
    await message.answer(stat_text, reply_markup=kb)

# --- ADMIN: BONUS VA PROMOKOD ---
@dp.message(F.text == "🎟 Bonus sozlamalari", F.from_user.id == ADMIN_ID)
async def admin_bonus_settings(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Kunlik bonusni belgilash", callback_data="set_daily_bonus")],
        [InlineKeyboardButton(text="🎟 Yangi Promokod qo'shish", callback_data="add_promo")]
    ])
    await message.answer("Bonus va Promokod bo'limi:", reply_markup=kb)

@dp.callback_query(F.data == "add_promo")
async def add_promo_1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi promokod yozing (Masalan: BONUS2026):")
    await state.set_state(AdminState.add_promo_code)

@dp.message(AdminState.add_promo_code)
async def add_promo_2(message: types.Message, state: FSMContext):
    await state.update_data(p_code=message.text.upper())
    await message.answer("Promokod summasini yozing:")
    await state.set_state(AdminState.add_promo_sum)

@dp.message(AdminState.add_promo_sum)
async def add_promo_3(message: types.Message, state: FSMContext):
    await state.update_data(p_sum=int(message.text))
    await message.answer("Necha kishi foydalana olsin (soni):")
    await state.set_state(AdminState.add_promo_limit)

@dp.message(AdminState.add_promo_limit)
async def add_promo_4(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_code = data['p_code']
    p_sum = data['p_sum']
    limit = int(message.text)
    await promo_col.insert_one({"code": p_code, "sum": p_sum, "limit": limit, "used_by": []})
    
    # Barchaga bildirishnoma
    users = await users_col.find().to_list(None)
    for u in users:
        try:
            await bot.send_message(u['user_id'], f"🎟 **Yangi Promokod!**\nKodi: `{p_code}`\nSummasi: {p_sum:,} so'm\nFaqat birinchi {limit} kishi uchun! 🎁")
        except: continue
    await message.answer("✅ Promokod qo'shildi va barchaga e'lon qilindi.")
    await state.clear()

# --- WEB SERVER (Render xatoliklarini oldini olish uchun) ---
async def handle(request): return web.Response(text="Bot is Running")
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

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
    add_card_num = State()
    edit_user_id = State()
    edit_user_balance = State()
    broadcast_msg = State()
    add_promo_code = State()
    add_promo_sum = State()
    add_promo_limit = State()
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

# --- START HANDLER ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"full_name": message.from_user.full_name, "last_seen": today},
         "$setOnInsert": {"balance": 0, "total_in": 0, "last_daily": None, "used_promos": [], "orders_today_count": 0}},
        upsert=True
    )
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}!", reply_markup=main_kb())

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_kb())

@dp.message(F.text == "🏠 Bosh menyu")
async def back_to_main(message: types.Message):
    await message.answer("Bosh menyu", reply_markup=main_kb())

# --- FOYDALANUVCHI FUNKSIYALARI ---

@dp.message(F.text == "💰 Balans")
async def balance(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    text = (
        f"💰 **Sizning hisobingiz:**\n\n"
        f"💵 Balans: {user.get('balance', 0):,} so'm\n"
        f"📥 Jami kiritilgan: {user.get('total_in', 0):,} so'm"
    )
    await message.answer(text, parse_mode="Markdown")

@dp.message(F.text == "📊 Statistika")
async def user_stats(message: types.Message):
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
        f"👤 **Sizning ko'rsatkichlaringiz:**\n"
        f"💰 Balans: {user.get('balance', 0):,} so‘m\n"
        f"📥 Jami kiritilgan: {user.get('total_in', 0):,} so‘m\n"
        f"📦 Bugungi buyurtmalaringiz: {u_today_orders} ta"
    )
    await message.answer(text, parse_mode="Markdown")

# --- BUYURTMA BERISH ---

@dp.message(F.text == "🛒 Xizmatlar")
async def services_view(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats:
        await message.answer("😔 Hozircha xizmatlar mavjud emas.")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c["name"], callback_data=f"cat_{c['_id']}")] for c in cats])
    await message.answer("Kategoriyani tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    services = await services_col.find({"cat_id": cat_id}).to_list(None)
    if not services:
        await call.message.answer("Bu bo‘limda xizmatlar yo'q")
        return
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']:,} so'm", callback_data=f"buy_{s['_id']}")] for s in services])
    await call.message.answer("Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def buy_process(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})

    if user["balance"] < service["price"]:
        await call.answer("❌ Balans yetarli emas!", show_alert=True)
        return

    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await call.message.answer(f"🚀 {service['name']} tanlandi.\nNarxi: {service['price']:,} so'm.\n\nIltimos, havola (link) yoki xabar yuboring:")
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link)
async def order_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    user = await users_col.find_one({"user_id": message.from_user.id})
    
    await users_col.update_one({"user_id": message.from_user.id}, {"$inc": {"balance": -data['s_price']}})
    order = await orders_col.insert_one({
        "user_id": message.from_user.id,
        "details": message.text,
        "service": data['s_name'],
        "price": data['s_price'],
        "status": "pending",
        "date": datetime.now().strftime("%Y-%m-%d")
    })

    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Bajarildi", callback_data=f"ord_ok_{order.inserted_id}"),
        InlineKeyboardButton("❌ Rad etish", callback_data=f"ord_no_{order.inserted_id}")
    ]])

    await bot.send_message(ADMIN_ID, f"📦 **Yangi Buyurtma!**\n\n👤 Foydalanuvchi: {message.from_user.full_name}\n🆔 ID: {message.from_user.id}\n🛠 Xizmat: {data['s_name']}\n🔗 Havola: {message.text}\n💰 Narxi: {data['s_price']:,} so'm\n💳 Qolgan balans: {user['balance'] - data['s_price']:,} so'm", reply_markup=kb)
    await message.answer("✅ Buyurtma qabul qilindi, adminga yuborildi.", reply_markup=main_kb())
    await state.clear()

# --- TO'LOV TIZIMI ---

@dp.message(F.text == "💳 Hisobni to'ldirish")
async def refill_start(message: types.Message, state: FSMContext):
    cards = await settings_col.find({"type": "card"}).to_list(None)
    if not cards:
        await message.answer("To'lov vaqtincha to'xtatilgan.")
        return
    text = "💳 **To'lov qilish uchun kartalar:**\n\n"
    for c in cards: text += f"📍 {c['number']}\n"
    await message.answer(text + "\nTo'lov qilib, chek (rasm) yuboring:", parse_mode="Markdown")
    await state.set_state(UserState.pay_photo)

@dp.message(UserState.pay_photo, F.photo)
async def refill_sum(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("💰 To'lov summasini kiriting (faqat raqam):")
    await state.set_state(UserState.pay_sum)

@dp.message(UserState.pay_sum)
async def refill_admin(message: types.Message, state: FSMContext):
    if not message.text.isdigit():
        return await message.answer("Faqat raqam kiriting!")
    data = await state.get_data()
    pay = await payments_col.insert_one({"u_id": message.from_user.id, "sum": int(message.text), "status": "pending"})
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton("✅ Tasdiqlash", callback_data=f"pay_ok_{pay.inserted_id}"),
        InlineKeyboardButton("❌ Bekor qilish", callback_data=f"pay_no_{pay.inserted_id}")
    ]])
    
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"💳 **Yangi to'lov cheki!**\n\n👤: {message.from_user.full_name}\n🆔: {message.from_user.id}\n💰 Summa: {message.text} so'm", reply_markup=kb)
    await message.answer("✅ Chek yuborildi. Admin tasdiqlashi bilan pul tushadi.")
    await state.clear()

@dp.callback_query(F.data.startswith("pay_ok_"))
async def pay_confirm(call: types.CallbackQuery):
    pay_id = call.data.split("_")[2]
    pay = await payments_col.find_one({"_id": ObjectId(pay_id)})
    if pay['status'] != "pending": return
    
    await users_col.update_one({"user_id": pay['u_id']}, {"$inc": {"balance": pay['sum'], "total_in": pay['sum']}})
    await payments_col.update_one({"_id": ObjectId(pay_id)}, {"$set": {"status": "ok"}})
    await bot.send_message(pay['u_id'], f"✅ To'lovingiz tasdiqlandi! {pay['sum']:,} so'm hisobingizga qo'shildi.")
    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ TASDIQLANDI")

# --- BONUS VA PROMO ---

@dp.callback_query(F.data == "daily_bonus")
async def get_daily(call: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    user = await users_col.find_one({"user_id": call.from_user.id})
    bonus_set = await settings_col.find_one({"type": "daily_bonus"})
    
    if not bonus_set: return await call.answer("Bonus o'chirilgan")
    if user.get("last_daily") == today: return await call.answer("Bugun olgansiz!", show_alert=True)
    
    await users_col.update_one({"user_id": call.from_user.id}, {"$inc": {"balance": bonus_set['sum']}, "$set": {"last_daily": today}})
    await call.answer(f"Tabriklaymiz! {bonus_set['sum']} so'm qo'shildi.", show_alert=True)

# --- ADMIN FUNKSIYALARI ---

@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_full_stats(message: types.Message):
    total_u = await users_col.count_documents({})
    all_in = await users_col.aggregate([{"$group": {"_id": None, "s": {"$sum": "$total_in"}}}]).to_list(1)
    all_bal = await users_col.aggregate([{"$group": {"_id": None, "s": {"$sum": "$balance"}}}]).to_list(1)
    top10 = await users_col.find().sort("total_in", -1).limit(10).to_list(None)

    text = f"📊 **Umumiy Statistika:**\n\n👥 Jami foydalanuvchi: {total_u}\n💰 Jami tushum: {all_in[0]['s'] if all_in else 0:,} so'm\n💳 Ishlatilmagan balanslar: {all_bal[0]['s'] if all_bal else 0:,} so'm\n\n🏆 **Top 10 To'lovchilar:**\n"
    for i, u in enumerate(top10, 1):
        text += f"{i}. {u['full_name']} - {u.get('total_in',0):,} so'm\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("🗑 Statistikani tozalash", callback_data="clear_stats")]])
    await message.answer(text, reply_markup=kb)

@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def card_settings(message: types.Message):
    cards = await settings_col.find({"type": "card"}).to_list(None)
    text = "💳 **Hozirgi kartalar:**\n"
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("➕ Karta qo'shish", callback_data="add_card")]])
    for c in cards:
        text += f"🔹 {c['number']}\n"
        kb.inline_keyboard.append([InlineKeyboardButton(f"❌ {c['number']} o'chirish", callback_data=f"del_card_{c['_id']}")])
    await message.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "add_card")
async def add_card_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Karta raqamini yuboring:")
    await state.set_state(AdminState.add_card_num)

@dp.message(AdminState.add_card_num)
async def add_card_save(message: types.Message, state: FSMContext):
    await settings_col.insert_one({"type": "card", "number": message.text})
    await message.answer("✅ Karta qo'shildi.")
    await state.clear()

@dp.message(F.text == "👤 Balans tahrirlash", F.from_user.id == ADMIN_ID)
async def edit_bal_start(message: types.Message, state: FSMContext):
    await message.answer("Foydalanuvchi ID raqamini yuboring:")
    await state.set_state(AdminState.edit_user_id)

@dp.message(AdminState.edit_user_id)
async def edit_bal_id(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("ID raqam bo'lishi kerak")
    await state.update_data(u_id=int(message.text))
    await message.answer("Yangi balans summasini yuboring (Masalan: 5000 yoki -2000):")
    await state.set_state(AdminState.edit_user_balance)

@dp.message(AdminState.edit_user_balance)
async def edit_bal_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await users_col.update_one({"user_id": data['u_id']}, {"$inc": {"balance": int(message.text)}})
    await message.answer("✅ Balans o'zgartirildi.")
    await state.clear()

@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_start(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni yozing:")
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg)
async def broadcast_send(message: types.Message, state: FSMContext):
    users = await users_col.find().to_list(None)
    count = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.text)
            count += 1
        except: continue
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yuborildi.")
    await state.clear()

@dp.message(F.text == "🆘 Yordam")
async def help_user(message: types.Message, state: FSMContext):
    await message.answer("Muammoingizni yozing, admin tez orada javob beradi:")
    await state.set_state(UserState.help_msg)

@dp.message(UserState.help_msg)
async def help_forward(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 **Yordam so'rovi!**\n\n👤 {message.from_user.full_name}\n🆔 {message.from_user.id}\n💬 Xabar: {message.text}")
    await message.answer("✅ Xabaringiz yuborildi.")
    await state.clear()

# --- SERVER ISHLATISH ---
async def handle(request): return web.Response(text="SMM Bot Online")

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

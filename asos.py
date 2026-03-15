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

# --- TOKEN VA MONGO URL ---
TOKEN = "8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"

# --- LOGGING ---
logging.basicConfig(level=logging.INFO)

# --- BOT VA DISPATCHER ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- MONGODB ULANISH ---
client = AsyncIOMotorClient(MONGO_URL)
db = client["smm_bot"]
users_col = db["users"]
services_col = db["services"]
categories_col = db["categories"]
orders_col = db["orders"]
settings_col = db["settings"]
promo_col = db["promo_codes"]
payments_col = db["payments"]
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
    set_daily_bonus = State()


class UserState(StatesGroup):
    order_link = State()
    pay_photo = State()
    pay_sum = State()
    help_msg = State()
    enter_promo = State()
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
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_kb())
@dp.message(F.text == "💰 Balans")
async def balance(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    today_orders = await orders_col.count_documents({"user_id": message.from_user.id, "date": datetime.now().strftime("%Y-%m-%d")})

    text = (
        f"💰 Sizning balansingiz:\n"
        f"Hisob: {user['balance']:,} so'm\n"
        f"Botga kiritgan jami summa: {user['total_in']:,} so'm\n"
        f"Bugun bergan buyurtmalaringiz: {today_orders} ta"
    )
    await message.answer(text)
@dp.message(F.text == "🛒 Xizmatlar")
async def services(message: types.Message):
    cats = await categories_col.find().to_list(None)

    if not cats:
        await message.answer("Hozircha xizmatlar yo'q")
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
        await call.message.answer("Bu bo‘limda xizmatlar mavjud emas")
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for s in services:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{s['name']} - {s['price']:,} so'm", callback_data=f"buy_{s['_id']}")])

    await call.message.answer("Xizmatni tanlang:", reply_markup=kb)


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
                           f"🛠 Xizmat: {data['s_name']}\n🔗 Havola: {message.text}\n💰 Summa: {data['s_price']:,} so'm\n"
                           f"💳 Qolgan balans: {user['balance']:,} so'm",
                           reply_markup=kb)
    await message.answer("✅ Buyurtmangiz yuborildi va adminga keladi", reply_markup=main_kb())
    await state.clear()
@dp.callback_query(F.data.startswith("ord_ok_"))
async def admin_confirm(call: types.CallbackQuery):
    order_id = call.data.split("_")[2]
    order = await orders_col.find_one({"_id": ObjectId(order_id)})
    if order['status'] != "pending":
        return await call.answer("Bu buyurtma allaqachon ko‘rib chiqilgan.")

    await orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "completed"}})
    await bot.send_message(order['user_id'], f"✅ Sizning '{order['service_name']}' buyurtmangiz bajarildi!")
    await call.message.edit_text(call.message.text + "\n\n✅ BAJARILDI")


@dp.callback_query(F.data.startswith("ord_no_"))
async def admin_decline(call: types.CallbackQuery):
    order_id = call.data.split("_")[2]
    order = await orders_col.find_one({"_id": ObjectId(order_id)})
    if order['status'] != "pending":
        return await call.answer("Bu buyurtma allaqachon ko‘rib chiqilgan.")

    await orders_col.update_one({"_id": ObjectId(order_id)}, {"$set": {"status": "declined"}})
    await bot.send_message(order['user_id'], f"❌ Sizning '{order['service_name']}' buyurtmangiz rad etildi!")
    await call.message.edit_text(call.message.text + "\n\n❌ RAD ETILDI")
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def add_balance(message: types.Message, state: FSMContext):
    cards = await settings_col.find({"type": "card"}).to_list(None)
    if not cards:
        await message.answer("Admin hali karta qo‘shmagan")
        return

    text = "💳 To‘lov uchun kartalar:\n"
    for c in cards:
        text += f"🔹 {c['name']}: {c['number']}\n"

    await message.answer(text + "\nTo‘lov qilganingizdan so‘ng chek yoki skrinshot yuboring:")
    await state.set_state(UserState.pay_photo)


@dp.message(UserState.pay_photo)
async def add_balance_photo(message: types.Message, state: FSMContext):
    if not message.photo:
        return await message.answer("❌ Iltimos, to‘lov skrinshotini yuboring")
    await state.update_data(pay_photo=True)
    await message.answer("✅ To‘lov summasini kiriting:")
    await state.set_state(UserState.pay_sum)


@dp.message(UserState.pay_sum)
async def add_balance_sum(message: types.Message, state: FSMContext):
    try:
        sum_ = int(message.text)
    except:
        return await message.answer("❌ Raqam kiriting")
    data = await state.get_data()
    await payments_col.insert_one({
        "user_id": message.from_user.id,
        "sum": sum_,
        "photo": True,
        "status": "pending"
    })
    await message.answer("✅ To‘lov admin tasdiqlashini kuting")
    await state.clear()
    await bot.send_message(ADMIN_ID, f"💳 {message.from_user.full_name} to‘lovi {sum_} so‘m. Tasdiqlash uchun tekshiring.")
@dp.message(F.text == "🎁 Bonuslar")
async def bonus_section(message: types.Message, state: FSMContext):
    today = datetime.now().strftime("%Y-%m-%d")
    user = await users_col.find_one({"user_id": message.from_user.id})
    settings = await settings_col.find_one({"type": "daily_bonus"})
    kb = InlineKeyboardMarkup(inline_keyboard=[])

    text = "🎁 Bonuslar bo‘limi:\n\n"

    # Kunlik bonus
    if settings:
        if user.get("last_daily") != today:
            kb.inline_keyboard.append([InlineKeyboardButton(text=f"🎁 Kunlik bonus: {settings['sum']} so‘m", callback_data="daily_bonus")])
        else:
            text += f"✅ Siz bugun kunlik bonus olgansiz ({settings['sum']} so‘m)\n"

    # Promokod
    kb.inline_keyboard.append([InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="enter_promo")])
    await message.answer(text, reply_markup=kb)


@dp.callback_query(F.data == "daily_bonus")
async def get_daily_bonus(call: types.CallbackQuery):
    today = datetime.now().strftime("%Y-%m-%d")
    user = await users_col.find_one({"user_id": call.from_user.id})
    settings = await settings_col.find_one({"type": "daily_bonus"})
    if not settings:
        return await call.answer("Admin bonusni belgilamagan", show_alert=True)

    if user.get("last_daily") == today:
        return await call.answer("Siz bugun bonus olgansiz", show_alert=True)

    await users_col.update_one({"user_id": call.from_user.id},
                               {"$inc": {"balance": settings['sum']}, "$set": {"last_daily": today}})
    await call.answer(f"✅ {settings['sum']} so‘m bonus olindi!", show_alert=True)


@dp.callback_query(F.data == "enter_promo")
async def enter_promo(call: types.CallbackQuery):
    await call.message.answer("Promokodni kiriting:")
    await UserState.enter_promo.set()


@dp.message(UserState.enter_promo)
async def promo_apply(message: types.Message, state: FSMContext):
    code = message.text.upper()
    promo = await promo_col.find_one({"code": code})
    if not promo:
        return await message.answer("❌ Bunday promokod yo‘q")

    if message.from_user.id in promo.get("used_by", []):
        return await message.answer("❌ Siz bu promokodni allaqachon ishlatgansiz")

    # Cheklangan promokodlar
    limit = promo.get("limit")
    used_count = len(promo.get("used_by", []))
    if limit and used_count >= limit:
        return await message.answer("❌ Promokod muddati tugagan")

    await users_col.update_one({"user_id": message.from_user.id}, {"$inc": {"balance": promo['sum']}})
    await promo_col.update_one({"_id": promo['_id']}, {"$push": {"used_by": message.from_user.id}})
    await message.answer(f"✅ Siz {promo['sum']} so‘m olidingiz!")
    await state.clear()
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
        f"👤 Sizning hisobingiz:\n"
        f"💰 Balans: {user['balance']:,} so‘m\n"
        f"📥 Jami kiritilgan summa: {user['total_in']:,} so‘m\n"
        f"📦 Bugungi buyurtmalar: {u_today_orders} ta"
    )
    await message.answer(text)
@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_stats(message: types.Message):
    total_users = await users_col.count_documents({})
    pipeline = [{"$sort": {"total_in": -1}}, {"$limit": 10}]
    top10 = await users_col.aggregate(pipeline).to_list(10)
    total_in_sum = await users_col.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$total_in"}}}]).to_list(1)
    total_balance = await users_col.aggregate([{"$group": {"_id": None, "sum": {"$sum": "$balance"}}}]).to_list(1)

    text = f"📊 **Umumiy Statistika**\n"
    text += f"👥 Jami foydalanuvchilar: {total_users}\n"
    text += f"💰 Botga kiritilgan jami: {total_in_sum[0]['sum'] if total_in_sum else 0:,} so‘m\n"
    text += f"💳 Qolgan pullar: {total_balance[0]['sum'] if total_balance else 0:,} so‘m\n\n"
    text += "🏆 Top 10 foydalanuvchi:\n"
    for i, u in enumerate(top10, 1):
        text += f"{i}. {u['full_name']} - {u['total_in']:,} so‘m\n"

    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton("🗑 Statistikani tozalash", callback_data="clear_stats")]])
    await message.answer(text, reply_markup=kb)
@dp.message(F.text == "🆘 Yordam")
async def help_msg(message: types.Message):
    await UserState.help_msg.set()
    await message.answer("Yordam xabaringizni yuboring, adminga yetkaziladi:")


@dp.message(UserState.help_msg)
async def forward_help(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 Yordam xabari:\n\n{message.text}\n\n👤 {message.from_user.full_name}\n🆔 {message.from_user.id}")
    await message.answer("✅ Xabaringiz adminga yetkazildi")
    await state.clear()
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def admin_services_panel(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("➕ Yangi Bo‘lim", callback_data="add_cat")],
        [InlineKeyboardButton("➕ Yangi Xizmat", callback_data="add_service")]
    ])
    await message.answer("Xizmatlar bo‘limi:", reply_markup=kb)


@dp.callback_query(F.data == "add_cat")
async def add_category(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo‘lim nomini kiriting:")
    await AdminState.add_cat.set()


@dp.message(AdminState.add_cat)
async def save_category(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ Bo‘lim qo‘shildi: {message.text}")
    await state.clear()


@dp.callback_query(F.data == "add_service")
async def add_service_start(call: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(None)
    if not cats:
        return await call.message.answer("❌ Bo‘lim yo‘q, avval bo‘lim qo‘shing")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(c['name'], callback_data=f"cat_sel_{c['_id']}")] for c in cats])
    await call.message.answer("Xizmat uchun bo‘limni tanlang:", reply_markup=kb)


@dp.callback_query(F.data.startswith("cat_sel_"))
async def select_category_for_service(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split("_")[2]
    await state.update_data(cat_id=cat_id)
    await call.message.answer("Xizmat nomini kiriting:")
    await AdminState.add_serv_name.set()


@dp.message(AdminState.add_serv_name)
async def save_service_name(message: types.Message, state: FSMContext):
    await state.update_data(serv_name=message.text)
    await message.answer("Xizmat narxini kiriting:")
    await AdminState.add_serv_price.set()


@dp.message(AdminState.add_serv_price)
async def save_service_price(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await services_col.insert_one({"cat_id": data['cat_id'], "name": data['serv_name'], "price": int(message.text)})
    await message.answer(f"✅ Xizmat qo‘shildi: {data['serv_name']} - {message.text} so‘m")
    await state.clear()
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

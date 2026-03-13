import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiohttp import web  # Web server uchun

# --- KONFIGURATSIYA ---
TOKEN = "8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo"
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

# --- KEEP-ALIVE WEB SERVER ---
async def handle(request):
    return web.Response(text="Bot is running 24/7!")

async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    # Render avtomatik PORT o'zgaruvchisini beradi, bo'lmasa 8080 ishlatiladi
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    logging.info(f"Web server {port}-portda ishga tushdi.")

# --- HOLATLAR ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    edit_card = State()
    add_channel = State()
    send_news = State()

class UserState(StatesGroup):
    order_data = State()
    pay_photo = State()
    pay_sum = State()
    help_msg = State()

# --- KLAVIATURALAR ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🆘 Yordam")]
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim/Xizmatlar"), KeyboardButton(text="📊 Admin Statistika")],
        [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="💳 Karta sozlamalari")],
        [KeyboardButton(text="📢 Majburiy obuna"), KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- MAJBURIY OBUNA TEKSHIRUVI ---
async def is_subscribed(user_id):
    channels = await settings_col.find({"type": "channel"}).to_list(None)
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch['chat_id'], user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: continue
    return True

# --- START VA OBUNA ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    now = datetime.now()
    
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"last_seen": now.strftime("%Y-%m-%d"), "month": now.strftime("%Y-%m")},
         "$setOnInsert": {"balance": 0, "total_in": 0, "join_date": now.strftime("%Y-%m-%d")}},
        upsert=True
    )

    if not await is_subscribed(u_id):
        channels = await settings_col.find({"type": "channel"}).to_list(None)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], url=c['link'])] for c in channels])
        kb.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        return await message.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=kb)
    
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_kb())

@dp.callback_query(F.data == "check_sub")
async def check_callback(call: types.CallbackQuery, state: FSMContext):
    if await is_subscribed(call.from_user.id):
        await call.message.delete()
        await call.message.answer("Obuna tasdiqlandi!", reply_markup=main_kb())
    else:
        await call.answer("Hali hamma kanallarga obuna bo'lmadingiz!", show_alert=True)

# --- FOYDALANUVCHI: BALANS ---
@dp.message(F.text == "💰 Balans")
async def bal_cmd(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"💰 Sizning balansingiz: **{user['balance']:,} so'm**", parse_mode="Markdown")

# --- FOYDALANUVCHI: XIZMAT VA BUYURTMA ---
@dp.message(F.text == "🛒 Xizmatlar")
async def user_cats(message: types.Message):
    cats = await categories_col.find().to_list(100)
    if not cats: return await message.answer("Hozircha bo'limlar yo'q.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"ucat_{c['name']}")] for c in cats])
    await message.answer("Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ucat_"))
async def user_servs(call: types.CallbackQuery):
    cat = call.data.split("_")[1]
    servs = await services_col.find({"category": cat}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"ubuy_{s['_id']}")] for s in servs])
    await call.message.edit_text(f"{cat} bo'limi xizmatlari:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ubuy_"))
async def buy_step1(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    serv = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})
    
    if user['balance'] < serv['price']:
        return await call.answer("❌ Balansda mablag' yetarli emas!", show_alert=True)
    
    await state.update_data(s_id=s_id, price=serv['price'], name=serv['name'])
    await call.message.answer(f"📦 {serv['name']} uchun ma'lumotlarni (Link/ID/Tavsif) yuboring:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(UserState.order_data)

@dp.message(UserState.order_data)
async def buy_step2(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await start_handler(message, state)
    data = await state.get_data()
    u_id = message.from_user.id
    
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['price']}})
    order = await orders_col.insert_one({"u_id": u_id, "name": data['name'], "price": data['price'], "info": message.text, "status": "pending"})
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"adm_o_y_{order.inserted_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_o_n_{order.inserted_id}")]
    ])
    await bot.send_message(ADMIN_ID, f"🆕 **YANGI BUYURTMA**\nID: `{u_id}`\nXizmat: {data['name']}\nSumma: {data['price']}\nMa'lumot: {message.text}", reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ Buyurtma berildi, balansdan pul yechildi. Admin tasdiqlashini kiting.", reply_markup=main_kb())
    await state.clear()

@dp.callback_query(F.data.startswith("adm_o_"))
async def admin_order_res(call: types.CallbackQuery):
    _, _, res, o_id = call.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if res == "y":
        await bot.send_message(order['u_id'], f"✅ Buyurtmangiz ({order['name']}) muvaffaqiyatli bajarildi!")
    else:
        await users_col.update_one({"user_id": order['u_id']}, {"$inc": {"balance": order['price']}})
        await bot.send_message(order['u_id'], f"❌ Buyurtmangiz ({order['name']}) rad etildi. Pullar hisobingizga qaytarildi.")
    await call.message.delete()

# --- FOYDALANUVCHI: HISOB TO'LDIRISH ---
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_init(message: types.Message, state: FSMContext):
    cards = await settings_col.find({"type": "card"}).to_list(None)
    card_text = "\n".join([f"💳 {c['name']}: `{c['number']}`" for c in cards])
    await message.answer(f"Hisobni to'ldirish uchun to'lov qiling:\n\n{card_text}\n\nTo'lovdan so'ng **screenshot** yuboring:", parse_mode="Markdown")
    await state.set_state(UserState.pay_photo)

@dp.message(UserState.pay_photo, F.photo)
async def pay_p(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("To'lov summasini kiriting (faqat raqam):")
    await state.set_state(UserState.pay_sum)

@dp.message(UserState.pay_sum)
async def pay_s(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam kiriting!")
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiq", callback_data=f"adm_p_y_{message.from_user.id}_{message.text}"),
         InlineKeyboardButton(text="❌ Rad", callback_data=f"adm_p_n_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"💰 To'lov so'rovi\nID: {message.from_user.id}\nSumma: {message.text}", reply_markup=kb)
    await message.answer("✅ To'lov ma'lumotlari yuborildi.", reply_markup=main_kb())
    await state.clear()

@dp.callback_query(F.data.startswith("adm_p_"))
async def admin_pay_res(call: types.CallbackQuery):
    p = call.data.split("_")
    res, u_id = p[2], int(p[3])
    if res == "y":
        amt = int(p[4])
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amt, "total_in": amt}})
        await bot.send_message(u_id, f"✅ To'lovingiz tasdiqlandi! Hisobingizga {amt:,} so'm qo'shildi.")
    else:
        await bot.send_message(u_id, "❌ To'lovingiz rad etildi.")
    await call.message.delete()

# --- ADMIN: XABAR YUBORISH ---
@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def news_start(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabar matnini kiriting:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(AdminState.send_news)

@dp.message(AdminState.send_news, F.from_user.id == ADMIN_ID)
async def news_send(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await start_handler(message, state)
    users = await users_col.find().to_list(None)
    for u in users:
        try: await bot.send_message(u['user_id'], message.text)
        except: continue
    await message.answer("✅ Xabar hamma foydalanuvchilarga yuborildi.", reply_markup=admin_kb())
    await state.clear()

# --- ADMIN: /ADMIN ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("🛠 Admin panel:", reply_markup=admin_kb())

# --- ADMIN: BO'LIM QO'SHISH ---
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def manage_init(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bo'lim qo'shish", callback_data="a_add_cat")],
        [InlineKeyboardButton(text="➕ Xizmat qo'shish", callback_data="a_add_serv")]
    ])
    await message.answer("Tanlang:", reply_markup=kb)

@dp.callback_query(F.data == "a_add_cat")
async def a_cat1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomi:")
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat)
async def a_cat2(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer("✅ Bo'lim qo'shildi.", reply_markup=admin_kb())
    await state.clear()

@dp.callback_query(F.data == "a_add_serv")
async def a_serv1(call: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"as_cat_{c['name']}")] for c in cats])
    await call.message.answer("Qaysi bo'limga?", reply_markup=kb)

@dp.callback_query(F.data.startswith("as_cat_"))
async def a_serv2(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat=call.data.split("_")[2])
    await call.message.answer("Xizmat nomi:")
    await state.set_state(AdminState.add_serv_name)

@dp.message(AdminState.add_serv_name)
async def a_serv3(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Narxi:")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price)
async def a_serv4(message: types.Message, state: FSMContext):
    d = await state.get_data()
    price = int(message.text)
    await services_col.insert_one({"category": d['cat'], "name": d['name'], "price": price})
    
    users = await users_col.find().to_list(None)
    for u in users:
        try: await bot.send_message(u['user_id'], f"📣 **YANGI XIZMAT!**\n\n📂 Bo'lim: {d['cat']}\n📦 Nom: {d['name']}\n💰 Narx: {price} so'm")
        except: continue
    
    await message.answer("✅ Xizmat qo'shildi va e'lon qilindi.", reply_markup=admin_kb())
    await state.clear()

# --- ADMIN: SOZLAMALAR ---
@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def card_set(message: types.Message, state: FSMContext):
    await message.answer("Karta: `Nomi:Raqami` (Humo:9860...)")
    await state.set_state(AdminState.edit_card)

@dp.message(AdminState.edit_card)
async def card_save(message: types.Message, state: FSMContext):
    name, num = message.text.split(":")
    await settings_col.update_one({"type": "card", "name": name}, {"$set": {"number": num}}, upsert=True)
    await message.answer("✅ Karta saqlandi.", reply_markup=admin_kb())
    await state.clear()

@dp.message(F.text == "📢 Majburiy obuna", F.from_user.id == ADMIN_ID)
async def sub_set(message: types.Message, state: FSMContext):
    await message.answer("Kanal: `Nomi|ChatID|Link` (Kanal1|-100...|t.me/...)")
    await state.set_state(AdminState.add_channel)

@dp.message(AdminState.add_channel)
async def sub_save(message: types.Message, state: FSMContext):
    name, cid, link = message.text.split("|")
    await settings_col.insert_one({"type": "channel", "name": name, "chat_id": int(cid), "link": link})
    await message.answer("✅ Kanal qo'shildi.", reply_markup=admin_kb())
    await state.clear()

# --- STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def user_stat(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    t_count = await users_col.count_documents({"last_seen": today})
    m_count = await users_col.count_documents({"month": month})
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"📊 **Statistika**\n\n👤 Bugun faol: {t_count}\n📅 Shu oyda faol: {m_count}\n💰 Siz kiritgan summa: {user['total_in']} so'm")

@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_stat(message: types.Message):
    total = await users_col.count_documents({})
    cursor = users_col.aggregate([{"$group": {"_id": None, "unused": {"$sum": "$balance"}, "total": {"$sum": "$total_in"}}}])
    res = await cursor.to_list(1)
    unused = res[0]['unused'] if res else 0
    total_in = res[0]['total'] if res else 0
    await message.answer(f"📊 **Admin Stats**\n\n👥 Jami foydalanuvchi: {total}\n💰 Jami kiritilgan: {total_in}\n💳 Ishlatilmagan qoldiq: {unused}")

# --- YORDAM ---
@dp.message(F.text == "🆘 Yordam")
async def help_init(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing:")
    await state.set_state(UserState.help_msg)

@dp.message(UserState.help_msg)
async def help_done(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 **YORDAM**\nID: `{message.from_user.id}`\nXabar: {message.text}")
    await message.answer("✅ Xabar adminga yuborildi.", reply_markup=main_kb())
    await state.clear()

@dp.message(F.text == "🏠 Bosh menyu")
async def back_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyu:", reply_markup=main_kb())

# --- ASOSIY MAIN FUNKSIYA ---
async def main():
    # 1. Web serverni ishga tushirish (Render uchun)
    asyncio.create_task(start_web_server())
    
    # 2. Eskirgan update'larni tozalash (bot o'chiqligida kelgan xabarlar botni qotirmasligi uchun)
    await bot.delete_webhook(drop_pending_updates=True)
    
    # 3. Pollingni boshlash
    logging.info("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")

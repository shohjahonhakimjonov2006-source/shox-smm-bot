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
from aiohttp import web

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
    edit_cat_new_name = State()
    edit_serv_new_price = State()
    edit_user_balance = State()

class UserState(StatesGroup):
    order_data = State()
    confirm_order = State() # Buyurtmani tasdiqlash uchun
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
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_kb())

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
    await call.message.answer(f"📦 {serv['name']} uchun havolani (link) yuboring:", 
                            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(UserState.order_data)

# --- HAVOLA QABUL QILISH VA TASDIQLASH ---
@dp.message(UserState.order_data)
async def buy_step2(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await start_handler(message, state)
    
    user_link = message.text or message.caption # Havola matn yoki caption bo'lishi mumkin
    if not user_link:
        return await message.answer("❌ Iltimos, havola yuboring!")

    await state.update_data(user_link=user_link)
    data = await state.get_data()

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order_yes"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_order_no")]
    ])
    
    await message.answer(f"📊 **Buyurtmani tasdiqlang:**\n\n"
                         f"📦 Xizmat: {data['name']}\n"
                         f"💰 Narxi: {data['price']:,} so'm\n"
                         f"🔗 Havola: `{user_link}`", 
                         reply_markup=kb, parse_mode="Markdown")
    await state.set_state(UserState.confirm_order)

@dp.callback_query(UserState.confirm_order, F.data.startswith("confirm_order_"))
async def buy_step3(call: types.CallbackQuery, state: FSMContext):
    res = call.data.split("_")[2]
    if res == "no":
        await call.message.edit_text("❌ Buyurtma bekor qilindi.")
        await state.clear()
        return

    data = await state.get_data()
    u_id = call.from_user.id
    u_name = call.from_user.full_name
    
    # Bugungi tartib raqami
    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_count = await orders_col.count_documents({"date_only": today_str}) + 1

    # Buyurtmani bazaga yozish
    order = await orders_col.insert_one({
        "u_id": u_id, "u_name": u_name, "name": data['name'], "price": data['price'], 
        "info": data['user_link'], "status": "pending", "date_only": today_str, "order_num": daily_count
    })
    
    # Balansdan ayirish
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['price']}})

    # ADMINGA YUBORISH
    admin_kb_order = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"adm_o_y_{order.inserted_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_o_n_{order.inserted_id}")]
    ])
    
    admin_msg = (f"🔔 **YANGI BUYURTMA #{daily_count}**\n\n"
                 f"👤 Mijoz: {u_name}\n"
                 f"🆔 ID: `{u_id}`\n"
                 f"📦 Xizmat: {data['name']}\n"
                 f"💰 Summa: {data['price']:,} so'm\n"
                 f"🔗 **HAVOLA:** `{data['user_link']}`\n"
                 f"📅 Sana: {today_str}")
    
    await bot.send_message(ADMIN_ID, admin_msg, reply_markup=admin_kb_order, parse_mode="Markdown", disable_web_page_preview=True)
    await call.message.edit_text(f"✅ Buyurtmangiz qabul qilindi! Bugungi tartib raqamingiz: #{daily_count}")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_o_"))
async def admin_order_res(call: types.CallbackQuery):
    _, _, res, o_id = call.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if not order: return await call.answer("Buyurtma topilmadi.")

    if res == "y":
        await bot.send_message(order['u_id'], f"✅ Buyurtmangiz ({order['name']}) muvaffaqiyatli bajarildi!")
        await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "completed"}})
    else:
        await users_col.update_one({"user_id": order['u_id']}, {"$inc": {"balance": order['price']}})
        await bot.send_message(order['u_id'], f"❌ Buyurtmangiz ({order['name']}) rad etildi. Pullar qaytarildi.")
        await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "rejected"}})
    
    await call.message.edit_text(call.message.text + "\n\n✅ JARAYON YAKUNLANDI.")
    await call.answer("Bajarildi")

# --- QOLGAN FUNKSIYALAR (Balans, Statistika, Admin) ---
@dp.message(F.text == "💰 Balans")
async def bal_cmd(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"💰 Sizning balansingiz: **{user['balance']:,} so'm**", parse_mode="Markdown")

@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("🛠 Admin paneliga xush kelibsiz!", reply_markup=admin_kb())

# --- ASOSIY MAIN ---
async def main():
    asyncio.create_task(start_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi.")

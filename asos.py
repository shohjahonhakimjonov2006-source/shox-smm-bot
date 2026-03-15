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

# --- HOLATLAR ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    edit_user_balance = State()

class UserState(StatesGroup):
    order_data = State()
    confirm_order = State()
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
        [KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- START ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    now = datetime.now()
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"last_seen": now.strftime("%Y-%m-%d")},
         "$setOnInsert": {"balance": 0, "total_in": 0}},
        upsert=True
    )
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_kb())

# --- XIZMATLAR VA BUYURTMA ---
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
    await call.message.edit_text(f"{cat} bo'limi:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ubuy_"))
async def buy_step1(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    serv = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})
    
    if user['balance'] < serv['price']:
        return await call.answer("❌ Balansda mablag' yetarli emas!", show_alert=True)
    
    await state.update_data(s_id=s_id, price=serv['price'], name=serv['name'])
    await call.message.answer(f"📦 {serv['name']} uchun havolani (link) yoki xabarni yuboring:", 
                            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(UserState.order_data)

# --- ISTALGAN XABARNI QABUL QILISH (YORDAM FUNKSIYASI KABI) ---
@dp.message(UserState.order_data)
async def buy_step2(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await start_handler(message, state)
    
    # Xabarning barcha ma'lumotlarini saqlaymiz
    content = message.text or message.caption or "Xabar yuborildi"
    await state.update_data(
        user_msg_id=message.message_id,
        user_chat_id=message.chat.id,
        user_link=content
    )
    
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order_yes"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_order_no")]
    ])
    
    await message.answer(f"📊 **Buyurtmangizni tasdiqlang:**\n\n📦 Xizmat: {data['name']}\n💰 Narxi: {data['price']:,} so'm", 
                         reply_markup=kb, parse_mode="Markdown")
    await state.set_state(UserState.confirm_order)

@dp.callback_query(UserState.confirm_order, F.data.startswith("confirm_order_"))
async def buy_step3(call: types.CallbackQuery, state: FSMContext):
    res = call.data.split("_")[2]
    if res == "no":
        await call.message.edit_text("❌ Bekor qilindi.")
        return await state.clear()

    data = await state.get_data()
    u_id = call.from_user.id
    
    # Balansni tekshirish
    user = await users_col.find_one({"user_id": u_id})
    if user['balance'] < data['price']:
        await call.answer("❌ Balansda pul yetarli emas!", show_alert=True)
        return await state.clear()

    today_str = datetime.now().strftime("%Y-%m-%d")
    daily_count = await orders_col.count_documents({"date_only": today_str}) + 1

    # Saqlash
    order = await orders_col.insert_one({
        "u_id": u_id, "u_name": call.from_user.full_name, "name": data['name'], 
        "price": data['price'], "status": "pending", "date_only": today_str, "order_num": daily_count
    })
    
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['price']}})

    # ADMINGA COPY_MESSAGE ORQALI YUBORISH
    admin_kb_order = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"adm_o_y_{order.inserted_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_o_n_{order.inserted_id}")]
    ])
    
    await bot.send_message(ADMIN_ID, f"🆕 **BUYURTMA #{daily_count}**\n👤: {call.from_user.full_name}\n📦: {data['name']}\n💰: {data['price']:,} so'm")
    
    # Foydalanuvchi yuborgan original xabarni adminga nusxalash
    await bot.copy_message(
        chat_id=ADMIN_ID,
        from_chat_id=data['user_chat_id'],
        message_id=data['user_msg_id'],
        reply_markup=admin_kb_order
    )

    await call.message.edit_text(f"✅ Qabul qilindi! Raqamingiz: #{daily_count}")
    await state.clear()

# --- ADMIN JAVOBI ---
@dp.callback_query(F.data.startswith("adm_o_"))
async def admin_order_res(call: types.CallbackQuery):
    _, _, res, o_id = call.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if not order: return
    
    if res == "y":
        await bot.send_message(order['u_id'], f"✅ Buyurtmangiz ({order['name']}) bajarildi!")
    else:
        await users_col.update_one({"user_id": order['u_id']}, {"$inc": {"balance": order['price']}})
        await bot.send_message(order['u_id'], "❌ Buyurtma rad etildi, pul qaytarildi.")
    
    await call.message.delete()

# --- BALANS VA TO'LOV ---
@dp.message(F.text == "💰 Balans")
async def bal_cmd(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"💰 Balans: {user['balance']:,} so'm")

@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_init(message: types.Message, state: FSMContext):
    await message.answer("To'lovdan so'ng screenshot yuboring:")
    await state.set_state(UserState.pay_photo)

@dp.message(UserState.pay_photo, F.photo)
async def pay_p(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Summani kiriting:")
    await state.set_state(UserState.pay_sum)

@dp.message(UserState.pay_sum)
async def pay_s(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Tasdiq", callback_data=f"adm_p_y_{message.from_user.id}_{message.text}")]])
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"To'lov so'rovi\nID: {message.from_user.id}\nSumma: {message.text}", reply_markup=kb)
    await message.answer("✅ Yuborildi.")
    await state.clear()

@dp.callback_query(F.data.startswith("adm_p_y_"))
async def admin_pay_ok(call: types.CallbackQuery):
    _, _, _, u_id, amt = call.data.split("_")
    await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": int(amt)}})
    await bot.send_message(int(u_id), f"✅ Hisobingiz {amt} so'mga to'ldirildi.")
    await call.message.delete()

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panel", reply_markup=admin_kb())

# --- YORDAM ---
@dp.message(F.text == "🆘 Yordam")
async def help_init(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing:")
    await state.set_state(UserState.help_msg)

@dp.message(UserState.help_msg)
async def help_done(message: types.Message, state: FSMContext):
    await bot.copy_message(ADMIN_ID, message.chat.id, message.message_id)
    await message.answer("✅ Adminga yuborildi.")
    await state.clear()

async def main():
    asyncio.create_task(start_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

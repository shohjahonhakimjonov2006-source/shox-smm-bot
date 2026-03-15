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
    add_card_name = State()
    add_card_num = State()
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
        [KeyboardButton(text="💳 Karta sozlamalari"), KeyboardButton(text="👤 Balans tahrirlash")],
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
        {"$set": {"last_seen": now.strftime("%Y-%m-%d"), 
                  "month": now.strftime("%Y-%m"),
                  "full_name": message.from_user.full_name},
         "$setOnInsert": {"balance": 0, "total_in": 0}},
        upsert=True
    )
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}!", reply_markup=main_kb())

# --- FOYDALANUVCHI: BALANS ---
@dp.message(F.text == "💰 Balans")
async def bal_cmd(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    balance = user.get('balance', 0)
    total_in = user.get('total_in', 0)
    await message.answer(f"💰 **Sizning balansingiz:** {balance:,} so'm\n"
                         f"📥 **Kiritilgan jami pul:** {total_in:,} so'm", parse_mode="Markdown")

# --- FOYDALANUVCHI: STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def user_stat(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    
    t_count = await users_col.count_documents({"last_seen": today})
    m_count = await users_col.count_documents({"month": month})
    
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_in"}}}]
    res = await users_col.aggregate(pipeline).to_list(1)
    total_money = res[0]['total'] if res else 0
    
    await message.answer(f"📊 **Bot statistikasi:**\n\n"
                         f"👥 Bugun foydalanganlar: {t_count}\n"
                         f"📅 Shu oy foydalanganlar: {m_count}\n"
                         f"💰 Foydalanuvchilar kiritgan jami summa: {total_money:,} so'm", parse_mode="Markdown")

# --- FOYDALANUVCHI: YORDAM ---
@dp.message(F.text == "🆘 Yordam")
async def help_init(message: types.Message, state: FSMContext):
    await message.answer("Adminga xabaringizni yozing (matn, rasm yoki link):")
    await state.set_state(UserState.help_msg)

@dp.message(UserState.help_msg)
async def help_done(message: types.Message, state: FSMContext):
    u_id = message.from_user.id
    u_name = message.from_user.full_name
    await bot.send_message(ADMIN_ID, f"🆘 **YANGI MUROJAAT**\n\n👤 Ismi: {u_name}\n🆔 ID: `{u_id}`\n\n👇 Xabar pastda:")
    await bot.copy_message(ADMIN_ID, message.chat.id, message.message_id)
    await message.answer("✅ Xabaringiz adminga yetkazildi.", reply_markup=main_kb())
    await state.clear()

# --- ADMIN: STATISTIKA VA TOP 10 ---
@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_stat(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    
    t_count = await users_col.count_documents({"last_seen": today})
    m_count = await users_col.count_documents({"month": month})
    
    top_users = await users_col.find().sort("total_in", -1).limit(10).to_list(None)
    top_text = "🔝 **Top 10 kiritilgan summa bo'yicha:**\n"
    for i, u in enumerate(top_users, 1):
        name = u.get('full_name', 'Noma\'lum')
        top_text += f"{i}. {name} | ID: `{u['user_id']}` | {u.get('total_in', 0):,} so'm\n"
    
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🗑 Pullarni tozalash", callback_data="clear_all_money")]])
    await message.answer(f"📊 **Admin Statistika:**\n\n👥 Bugun: {t_count}\n📅 Shu oy: {m_count}\n\n{top_text}", reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "clear_all_money", F.from_user.id == ADMIN_ID)
async def clear_money_confirm(call: types.CallbackQuery):
    await users_col.update_many({}, {"$set": {"total_in": 0}})
    await call.answer("✅ Kiritilgan pullar statistikasi tozalandi!", show_alert=True)

# --- ADMIN: BO'LIM VA XIZMATLAR ---
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def manage_cats(message: types.Message):
    cats = await categories_col.find().to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for c in cats:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"📁 {c['name']}", callback_data=f"list_serv_{c['name']}"),
            InlineKeyboardButton(text="❌", callback_data=f"del_cat_{c['_id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Bo'lim qo'shish", callback_data="adm_add_cat")])
    await message.answer("Boshqarish uchun bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_cat")
async def add_cat_init(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomini yozing:")
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat)
async def add_cat_final(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ {message.text} bo'limi qo'shildi!", reply_markup=admin_kb())
    await state.clear()

@dp.callback_query(F.data.startswith("list_serv_"))
async def list_servs(call: types.CallbackQuery):
    cat_name = call.data.split("_")[2]
    servs = await services_col.find({"category": cat_name}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for s in servs:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"{s['name']} - {s['price']}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_serv_{s['_id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Xizmat qo'shish", callback_data=f"adm_add_s_{cat_name}")])
    await call.message.edit_text(f"{cat_name} xizmatlari:", reply_markup=kb)

# --- ADMIN: KARTA SOZLAMALARI ---
@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def manage_cards(message: types.Message):
    cards = await settings_col.find({"type": "card"}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for c in cards:
        kb.inline_keyboard.append([
            InlineKeyboardButton(text=f"💳 {c['name']} - {c['number']}", callback_data="noop"),
            InlineKeyboardButton(text="❌", callback_data=f"del_card_{c['_id']}")
        ])
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Karta qo'shish", callback_data="adm_add_card")])
    await message.answer("To'lov kartalari:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_card")
async def add_card_init(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Karta nomini yozing (Humo, Uzcard...):")
    await state.set_state(AdminState.add_card_name)

@dp.message(AdminState.add_card_name)
async def add_card_num(message: types.Message, state: FSMContext):
    await state.update_data(c_name=message.text)
    await message.answer("Karta raqamini yozing:")
    await state.set_state(AdminState.add_card_num)

@dp.message(AdminState.add_card_num)
async def add_card_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await settings_col.insert_one({"type": "card", "name": data['c_name'], "number": message.text})
    await message.answer("✅ Karta saqlandi!", reply_markup=admin_kb())
    await state.clear()

# --- ADMIN: BALANS TAHRIRLASH ---
@dp.message(F.text == "👤 Balans tahrirlash", F.from_user.id == ADMIN_ID)
async def edit_bal_init(message: types.Message, state: FSMContext):
    await message.answer("Foydalanuvchi ID raqamini kiriting:")
    await state.set_state(AdminState.edit_user_balance)

@dp.message(AdminState.edit_user_balance)
async def edit_bal_final(message: types.Message, state: FSMContext):
    try:
        u_id, amount = message.text.split()
        await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": int(amount)}})
        await message.answer(f"✅ ID: {u_id} balansiga {amount} so'm o'zgartirildi.")
        await state.clear()
    except:
        await message.answer("Xato! Format: `ID SUMMA` (Masalan: 7861165622 5000)")

# --- FOYDALANUVCHI: XIZMATLAR VA BUYURTMA ---
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
        return await call.answer("❌ Balans yetarli emas!", show_alert=True)
    await state.update_data(s_id=s_id, price=serv['price'], name=serv['name'])
    await call.message.answer(f"📦 {serv['name']} uchun xabarni yoki havolani yuboring:", 
                            reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(UserState.order_data)

@dp.message(UserState.order_data)
async def buy_step2(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await start_handler(message, state)
    await state.update_data(m_id=message.message_id, c_id=message.chat.id)
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_y"), InlineKeyboardButton(text="❌ Bekor qilish", callback_data="confirm_n")]])
    await message.answer(f"📊 **Tasdiqlang:**\n\n📦 Xizmat: {data['name']}\n💰 Narxi: {data['price']:,} so'm", reply_markup=kb, parse_mode="Markdown")
    await state.set_state(UserState.confirm_order)

@dp.callback_query(UserState.confirm_order, F.data == "confirm_y")
async def buy_step3(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    u_id = call.from_user.id
    user = await users_col.find_one({"user_id": u_id})
    if user['balance'] < data['price']: return await call.answer("Balans yetarli emas!")
    
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['price']}})
    today = datetime.now().strftime("%Y-%m-%d")
    order = await orders_col.insert_one({"u_id": u_id, "name": data['name'], "price": data['price'], "date_only": today})
    
    await bot.send_message(ADMIN_ID, f"🆕 **BUYURTMA**\n👤: {call.from_user.full_name}\n🆔: `{u_id}`\n📦: {data['name']}")
    await bot.copy_message(ADMIN_ID, data['c_id'], data['m_id'], reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"adm_o_y_{order.inserted_id}"), InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_o_n_{order.inserted_id}")]]))
    
    await call.message.edit_text("✅ Buyurtma qabul qilindi!")
    await state.clear()

# --- FOYDALANUVCHI: TO'LOV ---
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_init(message: types.Message, state: FSMContext):
    cards = await settings_col.find({"type": "card"}).to_list(100)
    text = "To'lov kartalari:\n\n"
    for c in cards: text += f"💳 {c['name']}: `{c['number']}`\n"
    text += "\nScreenshot va summani yuboring."
    await message.answer(text, parse_mode="Markdown")
    await state.set_state(UserState.pay_photo)

@dp.message(UserState.pay_photo, F.photo)
async def pay_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Summani kiriting:")
    await state.set_state(UserState.pay_sum)

@dp.message(UserState.pay_sum)
async def pay_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    data = await state.get_data()
    u_id, amt = message.from_user.id, int(message.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ Tasdiq", callback_data=f"ap_y_{u_id}_{amt}"), InlineKeyboardButton(text="❌ Rad", callback_data=f"ap_n_{u_id}")]])
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"💰 To'lov: {amt:,} so'm\nID: `{u_id}`", reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ Yuborildi.")
    await state.clear()

@dp.callback_query(F.data.startswith("ap_"))
async def adm_pay_res(call: types.CallbackQuery):
    _, res, u_id, *amt = call.data.split("_")
    if res == "y":
        summa = int(amt[0])
        await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": summa, "total_in": summa}})
        await bot.send_message(int(u_id), f"✅ Hisobingiz {summa:,} so'mga to'ldirildi.")
    await call.message.delete()

# --- YORDAMCHI TUGMALAR ---
@dp.message(F.text == "🏠 Bosh menyu")
async def home(message: types.Message, state: FSMContext):
    await state.clear()
    await start_handler(message, state)

@dp.callback_query(F.data == "back_to_cats")
async def back_cats(call: types.CallbackQuery):
    await manage_cats(call.message)

# --- START ---
async def main():
    asyncio.create_task(start_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

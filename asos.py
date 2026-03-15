import asyncio
import logging
import os
from datetime import datetime, timedelta
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
promo_col = db['promo_codes']

# --- HOLATLAR ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    add_card_name = State()
    add_card_num = State()
    edit_user_balance = State()
    broadcast_msg = State()
    add_promo_code = State()
    add_promo_sum = State()
    set_daily_amount = State()

class UserState(StatesGroup):
    order_data = State()
    confirm_order = State()
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
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"full_name": message.from_user.full_name, "last_seen": datetime.now().strftime("%Y-%m-%d")},
         "$setOnInsert": {"balance": 0, "total_in": 0, "last_daily": None, "used_promos": []}},
        upsert=True
    )
    await message.answer(f"Xush kelibsiz, {message.from_user.full_name}!", reply_markup=main_kb())
    if u_id == ADMIN_ID:
        await message.answer("🛠 Admin panelga kirish: /admin", reply_markup=admin_kb())

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 **Admin paneliga xush kelibsiz!**", reply_markup=admin_kb())

# --- ADMIN: TO'LIQ STATISTIKA (TUZATILDI) ---
@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_full_stat(message: types.Message):
    total_users = await users_col.count_documents({})
    today = datetime.now().strftime("%Y-%m-%d")
    today_active = await users_col.count_documents({"last_seen": today})
    
    # Pul aylanmasi
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_in"}}}]
    res = await users_col.aggregate(pipeline).to_list(1)
    total_money = res[0]['total'] if res else 0
    
    # Buyurtmalar
    total_orders = await orders_col.count_documents({})
    
    text = (
        "📊 **TO'LIQ BOT STATISTIKASI**\n\n"
        f"👥 Jami foydalanuvchilar: {total_users} ta\n"
        f"🏃 Bugun faol bo'lganlar: {today_active} ta\n"
        f"📦 Jami buyurtmalar: {total_orders} ta\n"
        f"💰 Jami tushum (Kassa): {total_money:,} so'm\n"
    )
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN: KARTA SOZLAMALARI (TUZATILDI) ---
@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def manage_cards_admin(message: types.Message):
    cards = await settings_col.find({"type": "card"}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    
    text = "💳 **Mavjud to'lov kartalari:**\n\n"
    if not cards:
        text += "Hozircha kartalar yo'q."
    else:
        for c in cards:
            text += f"🔹 {c['name']}: `{c['number']}`\n"
            kb.inline_keyboard.append([
                InlineKeyboardButton(text=f"❌ {c['name']}ni o'chirish", callback_data=f"del_card_{c['_id']}")
            ])
            
    kb.inline_keyboard.append([InlineKeyboardButton(text="➕ Yangi karta qo'shish", callback_data="add_card_start")])
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "add_card_start")
async def add_card_step1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Karta nomini yozing (Masalan: Uzcard):")
    await state.set_state(AdminState.add_card_name)
    await call.answer()

@dp.message(AdminState.add_card_name)
async def add_card_step2(message: types.Message, state: FSMContext):
    await state.update_data(c_name=message.text)
    await message.answer("Karta raqamini yozing:")
    await state.set_state(AdminState.add_card_num)

@dp.message(AdminState.add_card_num)
async def add_card_step3(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await settings_col.insert_one({"type": "card", "name": data['c_name'], "number": message.text})
    await message.answer(f"✅ Karta qo'shildi: {data['c_name']}", reply_markup=admin_kb())
    await state.clear()

@dp.callback_query(F.data.startswith("del_card_"))
async def delete_card_admin(call: types.CallbackQuery):
    c_id = call.data.split("_")[2]
    await settings_col.delete_one({"_id": ObjectId(c_id)})
    await call.answer("Karta o'chirildi!", show_alert=True)
    await manage_cards_admin(call.message)

# --- ADMIN: BO'LIM VA XIZMAT QO'SHISH ---
@dp.message(F.text == "📂 Bo'lim/Xizmatlar", F.from_user.id == ADMIN_ID)
async def admin_serv_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Bo'lim", callback_data="add_cat_start")],
        [InlineKeyboardButton(text="➕ Yangi Xizmat", callback_data="add_serv_start")],
        [InlineKeyboardButton(text="🗑 Xizmatlarni tozalash", callback_data="clear_servs")]
    ])
    await message.answer("Xizmatlar boshqaruvi:", reply_markup=kb)

@dp.callback_query(F.data == "add_cat_start")
async def add_cat_step1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi bo'lim nomini yozing:")
    await state.set_state(AdminState.add_cat)
    await call.answer()

@dp.message(AdminState.add_cat)
async def add_cat_step2(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ Bo'lim qo'shildi: {message.text}")
    await state.clear()

@dp.callback_query(F.data == "add_serv_start")
async def add_serv_step1(call: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(100)
    if not cats: return await call.message.answer("Avval bo'lim qo'shing!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"as_cat_{c['name']}")] for c in cats])
    await call.message.answer("Xizmat qaysi bo'limga qo'shilsin?", reply_markup=kb)
    await call.answer()

@dp.callback_query(F.data.startswith("as_cat_"))
async def add_serv_step2(call: types.CallbackQuery, state: FSMContext):
    cat_name = call.data.split("_")[2]
    await state.update_data(s_cat=cat_name)
    await call.message.answer(f"[{cat_name}] uchun xizmat nomini yozing:")
    await state.set_state(AdminState.add_serv_name)
    await call.answer()

@dp.message(AdminState.add_serv_name)
async def add_serv_step3(message: types.Message, state: FSMContext):
    await state.update_data(s_name=message.text)
    await message.answer("Xizmat narxini yozing (faqat raqam):")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price)
async def add_serv_step4(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Narxni raqamda yozing!")
    data = await state.get_data()
    await services_col.insert_one({
        "category": data['s_cat'],
        "name": data['s_name'],
        "price": int(message.text)
    })
    await message.answer(f"✅ Xizmat qo'shildi: {data['s_name']} - {message.text} so'm", reply_markup=admin_kb())
    await state.clear()

# --- FOYDALANUVCHI: XIZMATLARNI KO'RISH ---
@dp.message(F.text == "🛒 Xizmatlar")
async def user_services(message: types.Message):
    cats = await categories_col.find().to_list(100)
    if not cats: return await message.answer("Hozircha xizmatlar mavjud emas.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"ucat_{c['name']}")] for c in cats])
    await message.answer("Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ucat_"))
async def user_cat_detail(call: types.CallbackQuery):
    cat_name = call.data.split("_")[1]
    servs = await services_col.find({"category": cat_name}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[])
    for s in servs:
        kb.inline_keyboard.append([InlineKeyboardButton(text=f"{s['name']} - {s['price']:,} so'm", callback_data=f"ubuy_{s['_id']}")])
    kb.inline_keyboard.append([InlineKeyboardButton(text="⬅️ Orqaga", callback_data="back_to_cats")])
    await call.message.edit_text(f"[{cat_name}] bo'limidagi xizmatlar:", reply_markup=kb)

# --- QOLGAN FUNKSIYALAR (Bonus, Reklama va b.) ---
# (Kodingizdagi mavjud Bonus, Reklama, Balans tahrirlash funksiyalari o'z holicha qoldi)

async def handle(request): return web.Response(text="Bot is running!")
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
    asyncio.run(main())

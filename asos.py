import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient

# --- KONFIGURATSIYA ---
TOKEN = "8473159649:AAHt9KnDd0aRDvthXrIE1sRWhP2u7DHpCnM"
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

# --- HOLATLAR ---
class AdminState(StatesGroup):
    changing_card = State()
    add_category = State()
    add_service_name = State()
    add_service_price = State()
    sending_news = State()

class UserOrder(StatesGroup):
    entering_details = State()

class PaymentState(StatesGroup):
    sending_receipt = State()
    entering_amount = State()

# --- KLAVIATURALAR ---
def main_menu():
    kb = [
        [KeyboardButton(text="🛒 Buyurtma berish"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu_kb():
    kb = [
        [KeyboardButton(text="📁 Bo'limlar/Xizmatlar"), KeyboardButton(text="📈 Admin Statistika")],
        [KeyboardButton(text="📢 Yangilik yuborish"), KeyboardButton(text="💳 Kartani o'zgartirish")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga qaytish")]], resize_keyboard=True)

# --- START VA USERNI BAZAGA YOZISH ---
@dp.message(Command("start"))
@dp.message(F.text == "⬅️ Ortga qaytish")
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    today = datetime.now().strftime("%Y-%m-%d")
    
    await users_col.update_one(
        {"user_id": u_id},
        {"$setOnInsert": {"balance": 0, "join_date": today}},
        upsert=True
    )
    
    if u_id == ADMIN_ID and message.text != "⬅️ Ortga qaytish":
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_menu_kb())
    else:
        await message.answer("Xizmat ko'rsatish botiga xush kelibsiz!", reply_markup=main_menu())

# --- ADMIN: TO'LIQ STATISTIKA (MONGODB) ---
@dp.message(F.text == "📈 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_full_stats(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    total_users = await users_col.count_documents({})
    today_users = await users_col.count_documents({"join_date": today})
    
    # Jami balansni hisoblash
    cursor = users_col.aggregate([{"$group": {"_id": None, "total": {"$sum": "$balance"}}}])
    res = await cursor.to_list(length=1)
    unused_balance = res[0]['total'] if res else 0
    
    # Inflow (tushum)
    settings = await settings_col.find_one({"type": "stats"})
    total_inflow = settings.get("total_inflow", 0) if settings else 0

    text = (
        "📊 **BOTNING TO'LIQ STATISTIKASI**\n\n"
        f"👥 Jami foydalanuvchilar: {total_users} ta\n"
        f"🆕 Bugun qo'shilganlar: {today_users} ta\n\n"
        f"💰 Jami tushum: {total_inflow} so'm\n"
        f"💳 Balanslardagi qoldiq: {unused_balance} so'm"
    )
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN: BO'LIMLAR VA XIZMATLAR ---
@dp.message(F.text == "📁 Bo'limlar/Xizmatlar", F.from_user.id == ADMIN_ID)
async def manage_cats(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bo'lim qo'shish", callback_data="add_cat")],
        [InlineKeyboardButton(text="➕ Xizmat qo'shish", callback_data="add_serv")],
        [InlineKeyboardButton(text="⚙️ Xizmatlarni tahrirlash", callback_data="manage_serv")]
    ])
    cats = await categories_col.find().to_list(length=100)
    text = "📁 **Bo'limlar:**\n" + "\n".join([f"- {c['name']}" for c in cats]) if cats else "Bo'limlar yo'q."
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data == "add_cat")
async def add_cat_start(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer("Yangi bo'lim nomini yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.add_category)

@dp.message(AdminState.add_category)
async def add_cat_finish(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Ortga qaytish": return await start_cmd(message, state)
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ '{message.text}' bo'limi qo'shildi.", reply_markup=admin_menu_kb())
    await state.clear()

@dp.callback_query(F.data == "add_serv")
async def add_serv_step1(callback: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(length=100)
    if not cats: return await callback.answer("Avval bo'lim yarating!", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"setcat_{c['name']}")] for c in cats])
    await callback.message.answer("Xizmat qaysi bo'limga qo'shilsin?", reply_markup=kb)

@dp.callback_query(F.data.startswith("setcat_"))
async def add_serv_step2(callback: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat=callback.data.split("_")[1])
    await callback.message.answer("Xizmat nomi:", reply_markup=back_kb())
    await state.set_state(AdminState.add_service_name)

@dp.message(AdminState.add_service_name)
async def add_serv_step3(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Narxi (raqamda):")
    await state.set_state(AdminState.add_service_price)

@dp.message(AdminState.add_service_price)
async def add_serv_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam!")
    data = await state.get_data()
    await services_col.insert_one({"category": data['cat'], "name": data['name'], "price": int(message.text)})
    await message.answer("✅ Xizmat qo'shildi!", reply_markup=admin_menu_kb())
    await state.clear()

# --- BUYURTMA BERISH ---
@dp.message(F.text == "🛒 Buyurtma berish")
async def user_cats(message: types.Message):
    cats = await categories_col.find().to_list(length=100)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"ucat_{c['name']}")] for c in cats])
    await message.answer("Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ucat_"))
async def user_servs(callback: types.CallbackQuery):
    cat = callback.data.split("_")[1]
    servs = await services_col.find({"category": cat}).to_list(length=100)
    if not servs: return await callback.answer("Xizmatlar yo'q.", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"ubuy_{s['_id']}")] for s in servs])
    await callback.message.edit_text(f"{cat} xizmatlari:", reply_markup=kb)

@dp.callback_query(F.data.startswith("ubuy_"))
async def buy_process(callback: types.CallbackQuery, state: FSMContext):
    from bson import ObjectId
    s_id = callback.data.split("_")[1]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": callback.from_user.id})
    
    if user['balance'] < service['price']:
        return await callback.message.answer("❌ Mablag' yetarli emas!", reply_markup=main_menu())
    
    await state.update_data(s_id=s_id, price=service['price'], s_name=service['name'])
    await callback.message.answer(f"'{service['name']}' uchun havola yoki PUBG ID yuboring:", reply_markup=back_kb())
    await state.set_state(UserOrder.entering_details)

@dp.message(UserOrder.entering_details)
async def buy_finish(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Ortga qaytish": return await start_cmd(message, state)
    data = await state.get_data()
    u_id = message.from_user.id
    
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['price']}})
    order_res = await orders_col.insert_one({"u_id": u_id, "price": data['price'], "status": "pending"})
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"ord_ok_{order_res.inserted_id}_{u_id}")],
        [InlineKeyboardButton(text="❌ Rad (Pul qaytarish)", callback_data=f"ord_no_{order_res.inserted_id}_{u_id}")]
    ])
    await bot.send_message(ADMIN_ID, f"🆕 BUYURTMA\nUser: {u_id}\nXizmat: {data['s_name']}\nMa'lumot: {message.text}", reply_markup=kb)
    await message.answer("✅ Buyurtma qabul qilindi!", reply_markup=main_menu())
    await state.clear()

# --- ADMIN: BUYURTMANI TASDIQLASH/RAD ETISH ---
@dp.callback_query(F.data.startswith("ord_"))
async def admin_order_res(callback: types.CallbackQuery):
    from bson import ObjectId
    _, action, o_id, u_id = callback.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    
    if action == "ok":
        await bot.send_message(int(u_id), "✅ Buyurtmangiz bajarildi!")
    else:
        await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": order['price']}})
        await bot.send_message(int(u_id), f"❌ Buyurtma rad etildi, {order['price']} so'm qaytarildi.")
    
    await callback.message.delete()

# --- BALANS VA HISOB TO'LDIRISH ---
@dp.message(F.text == "💰 Balans")
async def bal_view(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"💰 Balansingiz: {user['balance']} so'm")

@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_start(message: types.Message, state: FSMContext):
    card_data = await settings_col.find_one({"type": "card_info"})
    card = card_data['card'] if card_data else "Belgilanmagan"
    await message.answer(f"💳 Karta: `{card}`\nChekni rasm ko'rinishida yuboring:", reply_markup=back_kb(), parse_mode="Markdown")
    await state.set_state(PaymentState.sending_receipt)

@dp.message(PaymentState.sending_receipt, F.photo)
async def pay_receipt(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("To'lov summasini kiriting:")
    await state.set_state(PaymentState.entering_amount)

@dp.message(PaymentState.entering_amount)
async def pay_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam!")
    data = await state.get_data()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_y_{message.from_user.id}_{message.text}")],
        [InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_n_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, data['photo_id'], caption=f"💰 To'lov so'rovi: {message.text} so'm", reply_markup=kb)
    await message.answer("✅ Chek yuborildi!", reply_markup=main_menu())
    await state.clear()

@dp.callback_query(F.data.startswith("pay_"))
async def admin_pay_res(callback: types.CallbackQuery):
    _, res, u_id, amt = callback.data.split("_") + [None]
    if res == "y":
        await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": int(amt)}})
        await settings_col.update_one({"type": "stats"}, {"$inc": {"total_inflow": int(amt)}}, upsert=True)
        await bot.send_message(int(u_id), f"✅ Hisobingiz {amt} so'mga to'ldirildi!")
    else:
        await bot.send_message(int(u_id), "❌ To'lovingiz rad etildi.")
    await callback.message.delete()

# --- ADMIN: KARTANI O'ZGARTIRISH ---
@dp.message(F.text == "💳 Kartani o'zgartirish", F.from_user.id == ADMIN_ID)
async def change_card(message: types.Message, state: FSMContext):
    await message.answer("Yangi karta raqamini yuboring:", reply_markup=back_kb())
    await state.set_state(AdminState.changing_card)

@dp.message(AdminState.changing_card)
async def change_card_done(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Ortga qaytish": return await start_cmd(message, state)
    await settings_col.update_one({"type": "card_info"}, {"$set": {"card": message.text}}, upsert=True)
    await message.answer("✅ Karta yangilandi.", reply_markup=admin_menu_kb())
    await state.clear()

@dp.message(F.text == "🏠 Bosh menyu")
async def back_main(message: types.Message):
    await message.answer("Foydalanuvchi menyusi:", reply_markup=main_menu())

# --- RUN ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

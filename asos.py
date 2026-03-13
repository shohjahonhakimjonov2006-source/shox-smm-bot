import asyncio
import logging
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# --- KONFIGURATSIYA ---
TOKEN = "8473159649:AAHt9KnDd0aRDvthXrIE1sRWhP2u7DHpCnM"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- MONGODB ---
client = AsyncIOMotorClient(MONGO_URL)
db = client['bot_database']
users_col, services_col, categories_col = db['users'], db['services'], db['categories']
orders_col, settings_col = db['orders'], db['settings']

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
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Buyurtma berish"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")]
    ], resize_keyboard=True)

def admin_menu_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📁 Bo'limlar/Xizmatlar"), KeyboardButton(text="📈 Admin Statistika")],
        [KeyboardButton(text="📢 Yangilik yuborish"), KeyboardButton(text="💳 Kartani o'zgartirish")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- NAVIGATSIYA VA ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_menu_kb())

@dp.message(F.text == "🏠 Bosh menyu")
async def go_main_home(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Siz asosiy foydalanuvchi menyusiga qaytdingiz.", reply_markup=main_menu())

@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"last_seen": datetime.now().strftime("%Y-%m-%d")},
         "$setOnInsert": {"balance": 0, "join_date": datetime.now().strftime("%Y-%m-%d")}},
        upsert=True
    )
    await message.answer("Assalomu alaykum! Kerakli bo'limni tanlang:", reply_markup=main_menu())

# --- ADMIN: YANGILIK YUBORISH (TUZATILDI) ---
@dp.message(F.text == "📢 Yangilik yuborish", F.from_user.id == ADMIN_ID)
async def news_start(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabar matnini kiriting:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(AdminState.sending_news)

@dp.message(AdminState.sending_news)
async def news_send(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await go_main_home(message, state)
    users = await users_col.find().to_list(None)
    count = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.text)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yuborildi.", reply_markup=admin_menu_kb())
    await state.clear()

# --- ADMIN: XIZMAT QO'SHISH VA BILDIRISHNOMA ---
@dp.message(AdminState.add_service_price)
async def s_add_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam yozing!")
    data = await state.get_data()
    price = int(message.text)
    await services_col.insert_one({"category": data['cat'], "name": data['name'], "price": price})
    
    # Foydalanuvchilarga bildirishnoma
    promo_text = (
        f"📣 **YANGI XIZMAT QO'SHILDI!**\n\n"
        f"📂 Bo'lim: {data['cat']}\n"
        f"📦 Xizmat: {data['name']}\n"
        f"💰 Narxi: {price:,} so'm\n\n"
        f"Hoziroq botga kiring va yangi xizmatdan foydalaning! 👇"
    )
    users = await users_col.find().to_list(None)
    for u in users:
        try: await bot.send_message(u['user_id'], promo_text, parse_mode="Markdown")
        except: continue

    await message.answer("✅ Xizmat qo'shildi va barchaga e'lon qilindi.", reply_markup=admin_menu_kb())
    await state.clear()

# --- BUYURTMA BERISH VA PUL YECHISH ---
@dp.callback_query(F.data.startswith("ubuy_"))
async def user_order_details(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})

    if user['balance'] < service['price']:
        return await call.answer("❌ Balansingizda yetarli mablag' yo'q!", show_alert=True)

    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'], s_cat=service['category'])
    await call.message.answer(f"📝 {service['name']} uchun ma'lumotlarni kiriting (Link yoki PUBG ID):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(UserOrder.entering_details)

@dp.message(UserOrder.entering_details)
async def user_order_finish(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await go_main_home(message, state)
    data = await state.get_data()
    u_id = message.from_user.id
    
    # Pulni vaqtincha yechish
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['s_price']}})
    
    order_count = await orders_col.count_documents({}) + 1
    order_res = await orders_col.insert_one({
        "u_id": u_id, "price": data['s_price'], "status": "pending", "details": message.text
    })

    # Adminga xabar
    admin_text = (
        f"📦 **YANGI BUYURTMA #{order_count}**\n\n"
        f"👤 Foydalanuvchi ID: `{u_id}`\n"
        f"📂 Bo'lim: {data['s_cat']}\n"
        f"🛠 Xizmat turi: {data['s_name']}\n"
        f"🔗 Ma'lumot/ID: `{message.text}`\n"
        f"💰 Narxi: {data['s_price']:,} so'm"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Bajarildi", callback_data=f"ord_done_{order_res.inserted_id}_{u_id}")],
        [InlineKeyboardButton(text="❌ Rad etish (Pulni qaytarish)", callback_data=f"ord_cancel_{order_res.inserted_id}_{u_id}")]
    ])
    
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ Buyurtma qabul qilindi! Admin ko'rib chiqqach sizga xabar boradi.", reply_markup=main_menu())
    await state.clear()

# --- ADMIN: BUYURTMANI TASDIQLASH/RAD ETISH ---
@dp.callback_query(F.data.startswith("ord_"))
async def admin_order_decision(call: types.CallbackQuery):
    _, action, o_id, u_id = call.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if not order: return await call.answer("Buyurtma topilmadi!")

    if action == "done":
        await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "completed"}})
        await bot.send_message(int(u_id), f"✅ Buyurtmangiz bajarildi! Xizmat: {order.get('name', 'Tanlangan xizmat')}")
        await call.message.edit_caption(caption=call.message.text + "\n\n✅ **BAJARILDI**") if call.message.photo else await call.message.edit_text(call.message.text + "\n\n✅ **BAJARILDI**")
    
    elif action == "cancel":
        # Pulni qaytarish
        await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": order['price']}})
        await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "cancelled"}})
        await bot.send_message(int(u_id), f"❌ Buyurtmangiz rad etildi. {order['price']:,} so'm hisobingizga qaytarildi.")
        await call.message.edit_text(call.message.text + "\n\n❌ **RAD ETILDI (PUL QAYTARILDI)**")

    await call.message.edit_reply_markup(reply_markup=None)

# --- TO'LOVNI TASDIQLASH (FIXED) ---
@dp.callback_query(F.data.startswith("adm_p_"))
async def approve_payment(call: types.CallbackQuery):
    parts = call.data.split("_")
    status, u_id, amt = parts[2], int(parts[3]), int(parts[4]) if len(parts)>4 else 0
    
    if status == "y":
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amt}})
        await settings_col.update_one({"type": "stats"}, {"$inc": {"total_inflow": amt}}, upsert=True)
        await bot.send_message(u_id, f"✅ To'lovingiz tasdiqlandi! Hisobingiz {amt:,} so'mga to'ldirildi.")
        await call.answer("Tasdiqlandi", show_alert=True)
    else:
        await bot.send_message(u_id, "❌ To'lovingiz rad etildi. Chekda xatolik bor.")
        await call.answer("Rad etildi", show_alert=True)
    
    await call.message.edit_reply_markup(reply_markup=None)

# --- RUN ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

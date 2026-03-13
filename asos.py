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
users_col = db['users']
services_col = db['services']
categories_col = db['categories']
orders_col = db['orders']
settings_col = db['settings'] # Kartalar, kanallar va statistika uchun

# --- HOLATLAR ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    edit_card = State()
    add_channel = State()
    send_news = State()

class UserState(StatesGroup):
    order_details = State()
    payment_photo = State()
    payment_amount = State()
    help_message = State()

# --- KLAVIATURALAR ---
def main_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="🆘 Yordam")]
    ], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim/Xizmat boshqaruvi"), KeyboardButton(text="📊 Admin Statistika")],
        [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="💳 Karta sozlamalari")],
        [KeyboardButton(text="📢 Majburiy obuna"), KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- MAJBURIY OBUNA TEKSHIRUVI ---
async def check_sub(user_id):
    channels = await settings_col.find({"type": "channel"}).to_list(None)
    for ch in channels:
        try:
            member = await bot.get_chat_member(chat_id=ch['chat_id'], user_id=user_id)
            if member.status in ["left", "kicked"]: return False
        except: continue
    return True

# --- START ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    now = datetime.now()
    
    # Bazaga foydalanuvchini qo'shish
    await users_col.update_one(
        {"user_id": u_id},
        {"$set": {"last_seen": now.strftime("%Y-%m-%d"), "month": now.strftime("%Y-%m")},
         "$setOnInsert": {"balance": 0, "total_in": 0, "join_date": now.strftime("%Y-%m-%d")}},
        upsert=True
    )

    if not await check_sub(u_id):
        channels = await settings_col.find({"type": "channel"}).to_list(None)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Obuna bo'lish", url=c['link'])] for c in channels])
        kb.inline_keyboard.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        return await message.answer("Botdan foydalanish uchun kanallarga obuna bo'ling:", reply_markup=kb)
    
    await message.answer("Xush kelibsiz!", reply_markup=main_kb())

# --- FOYDALANUVCHI: XIZMATLAR VA BUYURTMA ---
@dp.message(F.text == "🛒 Xizmatlar")
async def show_cats(message: types.Message):
    cats = await categories_col.find().to_list(100)
    if not cats: return await message.answer("Hozircha xizmatlar yo'q.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"user_cat_{c['name']}")] for c in cats])
    await message.answer("Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("user_cat_"))
async def show_servs(call: types.CallbackQuery):
    cat_name = call.data.split("_")[2]
    servs = await services_col.find({"category": cat_name}).to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"buy_{s['_id']}")] for s in servs])
    await call.message.edit_text(f"{cat_name} bo'limidagi xizmatlar:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def order_start(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    serv = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})
    
    if user['balance'] < serv['price']:
        return await call.answer("❌ Mablag' yetarli emas!", show_alert=True)
    
    await state.update_data(s_id=s_id, price=serv['price'], name=serv['name'])
    await call.message.answer(f"📦 {serv['name']} uchun buyurtma berish.\nMa'lumotlarni yuboring (Link, ID va h.k.):", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Bekor qilish")]], resize_keyboard=True))
    await state.set_state(UserState.order_details)

@dp.message(UserState.order_details)
async def order_finish(message: types.Message, state: FSMContext):
    if message.text == "⬅️ Bekor qilish": return await start_cmd(message, state)
    data = await state.get_data()
    u_id = message.from_user.id
    
    # Pulni ushlab qolish
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['price']}})
    
    # Buyurtmani saqlash
    order = await orders_col.insert_one({
        "u_id": u_id, "name": data['name'], "price": data['price'], "details": message.text, "status": "pending"
    })
    
    # Adminga
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ord_y_{order.inserted_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"ord_n_{order.inserted_id}")]
    ])
    admin_msg = (
        f"🆕 **YANGI BUYURTMA**\n\n"
        f"👤 ID: `{u_id}`\n"
        f"🛠 Xizmat: {data['name']}\n"
        f"💰 Summa: {data['price']} so'm\n"
        f"📝 Tavsif: {message.text}"
    )
    await bot.send_message(ADMIN_ID, admin_msg, reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ Buyurtma qabul qilindi va pul ushlab qolindi. Admin tasdiqlashini kuting.", reply_markup=main_kb())
    await state.clear()

# --- ADMIN: BUYURTMA QARORI ---
@dp.callback_query(F.data.startswith("ord_"))
async def admin_ord_decision(call: types.CallbackQuery):
    _, decision, o_id = call.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if not order: return
    
    if decision == "y":
        await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "completed"}})
        await bot.send_message(order['u_id'], f"✅ Buyurtmangiz ({order['name']}) bajarildi!")
    else:
        # Pulni qaytarish
        await users_col.update_one({"user_id": order['u_id']}, {"$inc": {"balance": order['price']}})
        await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "rejected"}})
        await bot.send_message(order['u_id'], f"❌ Buyurtmangiz ({order['name']}) rad etildi. Pullar hisobingizga qaytarildi.")
    
    await call.message.delete()

# --- FOYDALANUVCHI: HISOB TO'LDIRISH ---
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def pay_start(message: types.Message, state: FSMContext):
    cards = await settings_col.find({"type": "card"}).to_list(None)
    card_text = "\n".join([f"💳 {c['name']}: `{c['number']}`" for c in cards])
    await message.answer(f"To'lov qilish uchun hamyonlar:\n{card_text}\n\nTo'lovdan so'ng screenshot yuboring:", parse_mode="Markdown", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Bekor qilish")]], resize_keyboard=True))
    await state.set_state(UserState.payment_photo)

@dp.message(UserState.payment_photo, F.photo)
async def pay_photo(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("To'lov summasini yozing:")
    await state.set_state(UserState.payment_amount)

@dp.message(UserState.payment_amount)
async def pay_amount(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam yozing!")
    data = await state.get_data()
    u_id = message.from_user.id
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiq", callback_data=f"pay_y_{u_id}_{message.text}"),
         InlineKeyboardButton(text="❌ Rad", callback_data=f"pay_n_{u_id}")]
    ])
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"💰 To'lov so'rovi\nID: {u_id}\nSumma: {message.text}", reply_markup=kb)
    await message.answer("✅ To'lov yuborildi. Tekshirilmoqda...", reply_markup=main_kb())
    await state.clear()

# --- ADMIN: TO'LOV QARORI ---
@dp.callback_query(F.data.startswith("pay_"))
async def admin_pay_decision(call: types.CallbackQuery):
    p = call.data.split("_")
    u_id, decision = int(p[2]), p[1]
    if decision == "y":
        amt = int(p[3])
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amt, "total_in": amt}})
        await bot.send_message(u_id, f"✅ Hisobingiz {amt} so'mga to'ldirildi!")
    else:
        await bot.send_message(u_id, "❌ To'lovingiz rad etildi.")
    await call.message.delete()

# --- FOYDALANUVCHI: STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def user_stat(message: types.Message):
    today = datetime.now().strftime("%Y-%m-%d")
    month = datetime.now().strftime("%Y-%m")
    t_count = await users_col.count_documents({"last_seen": today})
    m_count = await users_col.count_documents({"month": month})
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"📊 **Statistika**\n\n👤 Bugun faol: {t_count}\n📅 Shu oyda faol: {m_count}\n💰 Siz kiritgan jami summa: {user.get('total_in', 0)} so'm")

# --- ADMIN: /ADMIN ---
@dp.message(Command("admin"))
async def admin_start(message: types.Message, state: FSMContext):
    if message.from_user.id == ADMIN_ID:
        await state.clear()
        await message.answer("🛠 Admin panel:", reply_markup=admin_kb())

# --- ADMIN: KARTA SOZLAMALARI ---
@dp.message(F.text == "💳 Karta sozlamalari", F.from_user.id == ADMIN_ID)
async def card_settings(message: types.Message):
    await message.answer("Karta raqamini `Nomi:Raqami` shaklida yuboring (masalan: `Humo:9860...`):")
    await dp.fsm.get_context(message).set_state(AdminState.edit_card)

@dp.message(AdminState.edit_card)
async def card_save(message: types.Message, state: FSMContext):
    if ":" not in message.text: return await message.answer("Xato format. Nomi:Raqami")
    name, num = message.text.split(":", 1)
    await settings_col.update_one({"type": "card", "name": name}, {"$set": {"number": num}}, upsert=True)
    await message.answer("✅ Karta saqlandi.", reply_markup=admin_kb())
    await state.clear()

# --- ADMIN: STATISTIKA ---
@dp.message(F.text == "📊 Admin Statistika", F.from_user.id == ADMIN_ID)
async def admin_stat(message: types.Message):
    total = await users_col.count_documents({})
    # Hali ishlatilmagan summa (jami balanslar yig'indisi)
    cursor = users_col.aggregate([{"$group": {"_id": None, "total": {"$sum": "$balance"}}}])
    bal_res = await cursor.to_list(1)
    unused = bal_res[0]['total'] if bal_res else 0
    
    await message.answer(f"📊 **To'liq Statistika**\n\n👥 Jami foydalanuvchi: {total}\n💳 Ishlatilmagan summa: {unused} so'm")

# --- ADMIN: BO'LIM QO'SHISH ---
@dp.message(F.text == "📂 Bo'lim/Xizmat boshqaruvi", F.from_user.id == ADMIN_ID)
async def manage_init(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Bo'lim qo'shish", callback_data="adm_add_cat")],
        [InlineKeyboardButton(text="➕ Xizmat qo'shish", callback_data="adm_add_serv")]
    ])
    await message.answer("Tanlang:", reply_markup=kb)

@dp.callback_query(F.data == "adm_add_cat")
async def adm_cat_1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Bo'lim nomini yuboring:")
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat)
async def adm_cat_2(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer("✅ Bo'lim qo'shildi.", reply_markup=admin_kb())
    await state.clear()

# --- ADMIN: XIZMAT QO'SHISH + BILDIRISHNOMA ---
@dp.callback_query(F.data == "adm_add_serv")
async def adm_serv_1(call: types.CallbackQuery, state: FSMContext):
    cats = await categories_col.find().to_list(100)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"as_cat_{c['name']}")] for c in cats])
    await call.message.answer("Qaysi bo'limga?", reply_markup=kb)

@dp.callback_query(F.data.startswith("as_cat_"))
async def adm_serv_2(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat=call.data.split("_")[2])
    await call.message.answer("Xizmat nomi?")
    await state.set_state(AdminState.add_serv_name)

@dp.message(AdminState.add_serv_name)
async def adm_serv_3(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text)
    await message.answer("Narxi?")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price)
async def adm_serv_4(message: types.Message, state: FSMContext):
    d = await state.get_data()
    price = int(message.text)
    await services_col.insert_one({"category": d['cat'], "name": d['name'], "price": price})
    
    # Bildirishnoma
    users = await users_col.find().to_list(None)
    msg = f"📣 **YANGI XIZMAT!**\n\n📂 Bo'lim: {d['cat']}\n📦 Nom: {d['name']}\n💰 Narx: {price} so'm"
    for u in users:
        try: await bot.send_message(u['user_id'], msg, parse_mode="Markdown")
        except: continue
    
    await message.answer("✅ Xizmat qo'shildi va e'lon qilindi.", reply_markup=admin_kb())
    await state.clear()

# --- YORDAM TUGMASI ---
@dp.message(F.text == "🆘 Yordam")
async def help_cmd(message: types.Message, state: FSMContext):
    await message.answer("Muammoingizni yozing, admin javob beradi:", reply_markup=ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🏠 Bosh menyu")]], resize_keyboard=True))
    await state.set_state(UserState.help_message)

@dp.message(UserState.help_message)
async def help_send(message: types.Message, state: FSMContext):
    if message.text == "🏠 Bosh menyu": return await start_cmd(message, state)
    await bot.send_message(ADMIN_ID, f"🆘 **YORDAM SO'ROVI**\nID: `{message.from_user.id}`\nXabar: {message.text}")
    await message.answer("✅ Xabaringiz adminga yuborildi.", reply_markup=main_kb())
    await state.clear()

# --- ADMIN: MAJBURIY OBUNA ---
@dp.message(F.text == "📢 Majburiy obuna", F.from_user.id == ADMIN_ID)
async def sub_settings(message: types.Message):
    await message.answer("Kanalni `Nomi|ChatID|Link` shaklida yuboring (masalan: `Kanal1|-100123...|https://t.me/...`):")
    await dp.fsm.get_context(message).set_state(AdminState.add_channel)

@dp.message(AdminState.add_channel)
async def sub_save(message: types.Message, state: FSMContext):
    try:
        name, cid, link = message.text.split("|")
        await settings_col.insert_one({"type": "channel", "name": name, "chat_id": int(cid), "link": link})
        await message.answer("✅ Kanal qo'shildi.", reply_markup=admin_kb())
        await state.clear()
    except: await message.answer("Xato format. Nomi|ChatID|Link")

# --- ASOSIY MENYUGA QAYTISH ---
@dp.message(F.text == "🏠 Bosh menyu")
async def back_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyu:", reply_markup=main_kb())

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

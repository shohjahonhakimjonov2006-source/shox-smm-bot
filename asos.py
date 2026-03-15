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
promo_col = db['promo_codes']

# --- HOLATLAR (States) ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    add_card_name = State()
    add_card_num = State()
    edit_user_id = State() # Yangi: Foydalanuvchi IDsi
    edit_user_balance = State()
    broadcast_msg = State()
    add_promo_code = State()
    add_promo_sum = State()
    add_promo_limit = State() # Yangi: Promokod limiti
    set_daily_amount = State()

class UserState(StatesGroup):
    order_link = State() # Yangi: Havola yuborish
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
        await message.answer("🛠 **Admin paneliga xush kelibsiz!**", reply_markup=admin_kb())

# --- FOYDALANUVCHI: BUYURTMA BERISH ---
@dp.callback_query(F.data.startswith("ubuy_"))
async def user_buy_step1(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[1]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    user = await users_col.find_one({"user_id": call.from_user.id})
    
    if user['balance'] < service['price']:
        return await call.answer("❌ Mablag' yetarli emas!", show_alert=True)
    
    await state.update_data(s_id=s_id, s_price=service['price'], s_name=service['name'])
    await call.message.answer(f"🔗 {service['name']} uchun havola (link) yoki xabar yuboring:")
    await state.set_state(UserState.order_link)
    await call.answer()

@dp.message(UserState.order_link)
async def user_buy_step2(message: types.Message, state: FSMContext):
    data = await state.get_data()
    u_id = message.from_user.id
    
    # Pulni yechish
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": -data['s_price']}})
    
    # Buyurtmani saqlash
    order_id = await orders_col.insert_one({
        "user_id": u_id,
        "user_name": message.from_user.full_name,
        "service_name": data['s_name'],
        "link": message.text,
        "price": data['s_price'],
        "status": "pending",
        "date": datetime.now().strftime("%Y-%m-%d")
    })
    
    # Adminga yuborish
    today_orders = await orders_col.count_documents({"date": datetime.now().strftime("%Y-%m-%d")})
    user_upd = await users_col.find_one({"user_id": u_id})
    
    admin_text = (
        f"📦 **Yangi Buyurtma!**\n\n"
        f"🔢 Bugungi jami: {today_orders}\n"
        f"👤 Foydalanuvchi: {message.from_user.full_name} (ID: `{u_id}`)\n"
        f"🛠 Xizmat: {data['s_name']}\n"
        f"🔗 Havola: {message.text}\n"
        f"💰 Narxi: {data['s_price']:,} so'm\n"
        f"💳 Qolgan balansi: {user_upd['balance']:,} so'm"
    )
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"confirm_ord_{order_id.inserted_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"reject_ord_{order_id.inserted_id}")]
    ])
    
    await bot.send_message(ADMIN_ID, admin_text, reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ Buyurtmangiz qabul qilindi va adminga yuborildi. Tasdiqlanishini kuting.", reply_markup=main_kb())
    await state.clear()

# --- ADMIN: BUYURTMANI TASDIQLASH ---
@dp.callback_query(F.data.startswith("confirm_ord_"))
async def admin_confirm_order(call: types.CallbackQuery):
    o_id = call.data.split("_")[2]
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if order['status'] != "pending": return await call.answer("Bu buyurtma allaqachon ko'rilgan.")
    
    await orders_col.update_one({"_id": ObjectId(o_id)}, {"$set": {"status": "completed"}})
    await bot.send_message(order['user_id'], f"✅ Sizning '{order['service_name']}' buyurtmangiz muvaffaqiyatli bajarildi!")
    await call.message.edit_text(call.message.text + "\n\n✅ **BAJARILDI**")
    await call.answer("Tasdiqlandi")

# --- FOYDALANUVCHI: BALANS TO'LDIRISH ---
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def user_pay_start(message: types.Message):
    cards = await settings_col.find({"type": "card"}).to_list(10)
    if not cards: return await message.answer("Hozircha to'lov tizimi ulanmagan.")
    
    text = "💳 **To'lov qilish uchun karta ma'lumotlari:**\n\n"
    for c in cards:
        text += f"🔹 {c['name']}: `{c['number']}`\n"
    text += "\nTo'lovni amalga oshirib, **to'lov chekini (rasm)** yuboring:"
    await message.answer(text, parse_mode="Markdown")
    await dp.fsm.get_context(message).set_state(UserState.pay_photo)

@dp.message(UserState.pay_photo, F.photo)
async def user_pay_sum(message: types.Message, state: FSMContext):
    await state.update_data(photo_id=message.photo[-1].file_id)
    await message.answer("Endi to'lov summasini yozing (faqat raqam):")
    await state.set_state(UserState.pay_sum)

@dp.message(UserState.pay_sum)
async def user_pay_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam yozing!")
    data = await state.get_data()
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"pay_ok_{message.from_user.id}_{message.text}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"pay_no_{message.from_user.id}")]
    ])
    
    await bot.send_photo(ADMIN_ID, data['photo_id'], 
                         caption=f"💰 **Yangi to'lov!**\n👤 Foydalanuvchi: {message.from_user.full_name}\n🆔 ID: `{message.from_user.id}`\n💵 Summa: {message.text} so'm",
                         reply_markup=kb, parse_mode="Markdown")
    await message.answer("✅ To'lov yuborildi. Admin tasdiqlagach hisobingizga tushadi.")
    await state.clear()

@dp.callback_query(F.data.startswith("pay_ok_"))
async def admin_pay_confirm(call: types.CallbackQuery):
    _, _, u_id, amount = call.data.split("_")
    await users_col.update_one({"user_id": int(u_id)}, {"$inc": {"balance": int(amount), "total_in": int(amount)}})
    await bot.send_message(u_id, f"✅ To'lovingiz tasdiqlandi! Hisobingizga {amount} so'm qo'shildi.")
    await call.message.edit_caption(caption=call.message.caption + "\n\n✅ **TO'LOV QABUL QILINDI**")

# --- FOYDALANUVCHI: STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def user_stats(message: types.Message):
    u_id = message.from_user.id
    user = await users_col.find_one({"user_id": u_id})
    today = datetime.now().strftime("%Y-%m-%d")
    today_orders = await orders_col.count_documents({"user_id": u_id, "date": today})
    
    # Umumiy bot statistikasi
    total_users = await users_col.count_documents({})
    month_start = datetime.now().replace(day=1).strftime("%Y-%m-%d")
    month_users = await users_col.count_documents({"last_seen": {"$gte": month_start}})
    today_all_orders = await orders_col.count_documents({"date": today, "status": "completed"})
    
    text = (
        f"👤 **Sizning statisikangiz:**\n"
        f"💰 Balans: {user['balance']:,} so'm\n"
        f"📥 Jami kiritilgan: {user['total_in']:,} so'm\n"
        f"📦 Bugungi buyurtmalaringiz: {today_orders} ta\n\n"
        f"📊 **Bot statistikasi:**\n"
        f"👥 Bugun aktiv: {await users_col.count_documents({'last_seen': today})} ta\n"
        f"📅 Shu oyda aktiv: {month_users} ta\n"
        f"✅ Bugun bajarilgan buyurtmalar: {today_all_orders} ta"
    )
    await message.answer(text)

# --- BONUS VA PROMOKOD TIZIMI ---
@dp.message(F.text == "🎁 Bonuslar")
async def bonus_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Kunlik bonus", callback_data="get_daily_bonus")],
        [InlineKeyboardButton(text="🎟 Promokod kiritish", callback_data="enter_promo")]
    ])
    await message.answer("🎁 Bonus bo'limi. Tanlang:", reply_markup=kb)

@dp.callback_query(F.data == "get_daily_bonus")
async def daily_bonus(call: types.CallbackQuery):
    u_id = call.from_user.id
    user = await users_col.find_one({"user_id": u_id})
    today = datetime.now().strftime("%Y-%m-%d")
    
    if user.get('last_daily') == today:
        return await call.answer("❌ Bugun bonus olgansiz!", show_alert=True)
    
    settings = await settings_col.find_one({"type": "daily_bonus"})
    amount = settings['amount'] if settings else 100
    
    await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amount}, "$set": {"last_daily": today}})
    await call.answer(f"✅ Sizga {amount} so'm bonus berildi!", show_alert=True)

# --- YORDAM ---
@dp.message(F.text == "🆘 Yordam")
async def help_start(message: types.Message, state: FSMContext):
    await message.answer("Xabaringizni yozing, admin tez orada javob beradi:")
    await state.set_state(UserState.help_msg)

@dp.message(UserState.help_msg)
async def help_send(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 **Yordam so'rovi!**\n👤 Kimdan: {message.from_user.full_name}\n🆔 ID: `{message.from_user.id}`\n\n📝 Xabar: {message.text}")
    await message.answer("✅ Xabaringiz adminga yuborildi.")
    await state.clear()

# --- ADMIN: PROMOKOD SOZLAMALARI ---
@dp.message(F.text == "🎟 Bonus sozlamalari", F.from_user.id == ADMIN_ID)
async def admin_promo_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Kunlik bonus summasi", callback_data="set_daily_start")],
        [InlineKeyboardButton(text="➕ Yangi Promokod", callback_data="add_promo_start")]
    ])
    await message.answer("Bonus va Promokod sozlamalari:", reply_markup=kb)

@dp.callback_query(F.data == "add_promo_start")
async def add_promo_1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Promokod nomini yozing (Masalan: SOVGA2024):")
    await state.set_state(AdminState.add_promo_code)

@dp.message(AdminState.add_promo_code)
async def add_promo_2(message: types.Message, state: FSMContext):
    await state.update_data(p_code=message.text.upper())
    await message.answer("Promokod summasini yozing:")
    await state.set_state(AdminState.add_promo_sum)

@dp.message(AdminState.add_promo_sum)
async def add_promo_3(message: types.Message, state: FSMContext):
    await state.update_data(p_sum=int(message.text))
    await message.answer("Foydalanish limiti (necha kishi uchun):")
    await state.set_state(AdminState.add_promo_limit)

@dp.message(AdminState.add_promo_limit)
async def add_promo_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await promo_col.insert_one({
        "code": data['p_code'],
        "amount": data['p_sum'],
        "limit": int(message.text),
        "used": 0
    })
    # Barchaga xabar yuborish
    users = await users_col.find().to_list(None)
    for u in users:
        try:
            await bot.send_message(u['user_id'], f"🎟 **Yangi Promokod!**\nKodi: `{data['p_code']}`\nSummasi: {data['p_sum']:,} so'm\nFaqat birinchi {message.text} kishi uchun!")
        except: continue
        
    await message.answer("✅ Promokod qo'shildi va barchaga e'lon qilindi.")
    await state.clear()

# --- WEB SERVER (Render/Heroku uchun) ---
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

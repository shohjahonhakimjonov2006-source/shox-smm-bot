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

# --- KEEP-ALIVE WEB SERVER ---
async def handle(request): return web.Response(text="Bot is running!")
async def start_web_server():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 8080)))
    await site.start()

# --- HOLATLAR ---
class AdminState(StatesGroup):
    add_cat = State()
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
        await message.answer("🛠 Admin panelga kirish: /admin")

@dp.message(Command("admin"))
async def admin_panel_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("🛠 **Admin paneliga xush kelibsiz!**", reply_markup=admin_kb())

# --- ADMIN: XABAR YUBORISH (REKLAMA) ---
@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def broadcast_start(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni kiriting (Rasm, matn va h.k.):")
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg)
async def broadcast_send(message: types.Message, state: FSMContext):
    users = await users_col.find().to_list(None)
    sent = 0
    for u in users:
        try:
            await bot.copy_message(u['user_id'], message.chat.id, message.message_id)
            sent += 1
            await asyncio.sleep(0.05) # Spamga tushmaslik uchun
        except: continue
    await message.answer(f"✅ Xabar {sent} ta foydalanuvchiga yuborildi.")
    await state.clear()

# --- ADMIN: BUYURTMANI TASDIQLASH (FIXED) ---
@dp.callback_query(F.data.startswith("adm_o_"))
async def admin_order_res(call: types.CallbackQuery):
    # Format: adm_o_y_ID yoki adm_o_n_ID
    _, _, res, o_id = call.data.split("_")
    order = await orders_col.find_one({"_id": ObjectId(o_id)})
    if not order: return await call.answer("Buyurtma topilmadi!")

    u_id = order['u_id']
    if res == "y":
        await bot.send_message(u_id, f"✅ Buyurtmangiz bajarildi!\n📦 Xizmat: {order['name']}")
        await call.message.edit_text(call.message.text + "\n\n✅ HOLAT: Bajarildi")
    else:
        # Pulini qaytarish
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": order['price']}})
        await bot.send_message(u_id, f"❌ Buyurtmangiz rad etildi.\n📦 Xizmat: {order['name']}\n💰 Mablag' balansingizga qaytarildi.")
        await call.message.edit_text(call.message.text + "\n\n❌ HOLAT: Rad etildi")
    await call.answer()

# --- BONUSLAR BO'LIMI ---
@dp.message(F.text == "🎁 Bonuslar")
async def bonus_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Kunlik bonus", callback_data="get_daily")],
        [InlineKeyboardButton(text="🎟 Promo-kod kiritish", callback_data="use_promo")]
    ])
    await message.answer("🎁 Bonus turini tanlang:", reply_markup=kb)

@dp.callback_query(F.data == "get_daily")
async def daily_bonus(call: types.CallbackQuery):
    user = await users_col.find_one({"user_id": call.from_user.id})
    daily_cfg = await settings_col.find_one({"type": "daily_amount"})
    amount = daily_cfg['value'] if daily_cfg else 500
    
    last = user.get('last_daily')
    now = datetime.now()
    if last and datetime.fromisoformat(last) > now - timedelta(days=1):
        return await call.answer("❌ Kunlik bonusni olib bo'lgansiz. Ertaga qayting!", show_alert=True)
    
    await users_col.update_one({"user_id": call.from_user.id}, {
        "$inc": {"balance": amount},
        "$set": {"last_daily": now.isoformat()}
    })
    await call.answer(f"✅ Hisobingizga {amount} so'm qo'shildi!", show_alert=True)

@dp.callback_query(F.data == "use_promo")
async def use_promo_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("🎟 Promo-kodni kiriting:")
    await state.set_state(UserState.enter_promo)

@dp.message(UserState.enter_promo)
async def use_promo_finish(message: types.Message, state: FSMContext):
    code = message.text.strip().upper()
    promo = await promo_col.find_one({"code": code})
    if not promo:
        return await message.answer("❌ Bunday promo-kod mavjud emas.")
    
    user = await users_col.find_one({"user_id": message.from_user.id})
    if code in user.get('used_promos', []):
        return await message.answer("❌ Siz bu koddan foydalanib bo'lgansiz.")
    
    await users_col.update_one({"user_id": message.from_user.id}, {
        "$inc": {"balance": promo['sum']},
        "$push": {"used_promos": code}
    })
    await message.answer(f"✅ Tabriklaymiz! {promo['sum']} so'm hisobingizga qo'shildi.")
    await state.clear()

# --- ADMIN: BONUS SOZLAMALARI ---
@dp.message(F.text == "🎟 Bonus sozlamalari", F.from_user.id == ADMIN_ID)
async def admin_bonus_menu(message: types.Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Yangi Promo-kod", callback_data="add_promo")],
        [InlineKeyboardButton(text="💰 Kunlik bonus summasi", callback_data="set_daily_sum")],
        [InlineKeyboardButton(text="🗑 Promo-kodlarni ko'rish", callback_data="list_promos")]
    ])
    await message.answer("Bonus sozlamalari:", reply_markup=kb)

@dp.callback_query(F.data == "add_promo", F.from_user.id == ADMIN_ID)
async def add_promo_1(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Yangi promo-kod nomini yozing (Masalan: SOVGA2024):")
    await state.set_state(AdminState.add_promo_code)

@dp.message(AdminState.add_promo_code)
async def add_promo_2(message: types.Message, state: FSMContext):
    await state.update_data(p_code=message.text.strip().upper())
    await message.answer("Ushbu kod uchun beriladigan summani yozing:")
    await state.set_state(AdminState.add_promo_sum)

@dp.message(AdminState.add_promo_sum)
async def add_promo_3(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam yozing!")
    data = await state.get_data()
    await promo_col.insert_one({"code": data['p_code'], "sum": int(message.text)})
    await message.answer(f"✅ Promo-kod yaratildi: {data['p_code']} ({message.text} so'm)")
    await state.clear()

@dp.callback_query(F.data == "set_daily_sum", F.from_user.id == ADMIN_ID)
async def set_daily_init(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Kunlik bonus miqdorini yozing (Hozirgi standart: 500):")
    await state.set_state(AdminState.set_daily_amount)

@dp.message(AdminState.set_daily_amount)
async def set_daily_final(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return
    await settings_col.update_one({"type": "daily_amount"}, {"$set": {"value": int(message.text)}}, upsert=True)
    await message.answer(f"✅ Kunlik bonus miqdori {message.text} so'mga o'zgartirildi.")
    await state.clear()

# --- ADMIN: BALANS TAHRIRLASH ---
@dp.message(F.text == "👤 Balans tahrirlash", F.from_user.id == ADMIN_ID)
async def edit_bal_init(message: types.Message, state: FSMContext):
    await message.answer("Foydalanuvchi ID va summani yozing (Masalan: `7861165622 10000`):")
    await state.set_state(AdminState.edit_user_balance)

@dp.message(AdminState.edit_user_balance)
async def edit_bal_final(message: types.Message, state: FSMContext):
    try:
        parts = message.text.split()
        u_id, amount = int(parts[0]), int(parts[1])
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amount}})
        await message.answer(f"✅ ID: {u_id} balansiga {amount} so'm qo'shildi.")
        await state.clear()
    except:
        await message.answer("❌ Xato! Format: `ID SUMMA` (Masalan: 7861165622 5000)")

# --- FOYDALANUVCHI: BALANS & STATISTIKA ---
@dp.message(F.text == "💰 Balans")
async def bal_cmd(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"💰 **Sizning balansingiz:** {user.get('balance', 0):,} so'm\n"
                         f"📥 **Kiritilgan jami pul:** {user.get('total_in', 0):,} so'm", parse_mode="Markdown")

@dp.message(F.text == "📊 Statistika")
async def user_stat(message: types.Message):
    t_count = await users_col.count_documents({"last_seen": datetime.now().strftime("%Y-%m-%d")})
    res = await users_col.aggregate([{"$group": {"_id": None, "total": {"$sum": "$total_in"}}}]).to_list(1)
    total_money = res[0]['total'] if res else 0
    await message.answer(f"📊 **Statistika:**\n\n👥 Bugun: {t_count}\n💰 Jami aylanma: {total_money:,} so'm", parse_mode="Markdown")

# --- QOLGAN STANDART HANDLERLAR (🛒 Xizmatlar, 💳 Karta va b.) ---
# ... (Avvalgi koddagi user_cats, user_servs, buy_step1, buy_step2, buy_step3 handlerlarini shu yerga qo'shasiz)
# Eslatma: Buyurtma qismidagi adm_o_y callback'larini yuqoridagi yangi handler bilan moslashtirdim.

@dp.message(F.text == "🏠 Bosh menyu")
async def back_home(message: types.Message, state: FSMContext):
    await state.clear()
    await start_handler(message, state)

async def main():
    asyncio.create_task(start_web_server())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiohttp import web

# --- KONFIGURATSIYA ---
TOKEN = "8678413684:AAF6eNkkznizwFSoZYuQGGuHoYJg-ukXQM0"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- DATABASE ---
client = AsyncIOMotorClient(MONGO_URL)
db = client["smm_bot_v2"]
users_col = db["users"]
services_col = db["services"]
categories_col = db["categories"]
orders_col = db["orders"]
settings_col = db["settings"]
promos_col = db["promos"]

# --- STATES ---
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    set_card = State()
    set_card_owner = State()
    set_ref_price = State()
    create_promo_code = State()
    create_promo_amount = State()
    create_promo_limit = State()
    broadcast_msg = State()
    add_channel = State()
    edit_balance_id = State()
    edit_balance_amount = State()

class UserState(StatesGroup):
    order_confirm = State()
    order_link = State()
    order_qty = State()
    fill_amount = State()
    fill_receipt = State()
    enter_promo = State()
    help_msg = State()

# --- KEYBOARDS ---
def main_kb(user_id):
    btns = [
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 To'lov qilish"), KeyboardButton(text="📦 Buyurtmalarim")],
        [KeyboardButton(text="👥 Referal"), KeyboardButton(text="🎁 Promokod")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🏆 TOP")],
        [KeyboardButton(text="🆘 Yordam")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim/Xizmatlar"), KeyboardButton(text="📉 Statistika")],
        [KeyboardButton(text="💳 Karta sozlash"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="🎁 Ref/Promo sozlash"), KeyboardButton(text="➕ Majburiy obuna")],
        [KeyboardButton(text="👤 Balansni boshqarish"), KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga")]], resize_keyboard=True)

# --- UTILS ---
async def check_sub(user_id):
    setting = await settings_col.find_one({"key": "channels"})
    if not setting or not setting.get("list"): return True
    for ch in setting["list"]:
        try:
            member = await bot.get_chat_member(ch, user_id)
            if member.status in ["left", "kicked"]: return False
        except: continue
    return True

# --- START & REFERRAL ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    u_id = message.from_user.id
    
    if not await check_sub(u_id):
        setting = await settings_col.find_one({"key": "channels"})
        ch_url = setting['list'][0].replace("@", "https://t.me/")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Obuna bo'lish", url=ch_url)],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
        ])
        return await message.answer("Botdan foydalanish uchun kanalimizga a'zo bo'ling!", reply_markup=kb)

    user = await users_col.find_one({"user_id": u_id})
    if not user:
        ref_by = None
        if command.args and command.args.isdigit():
            ref_id = int(command.args)
            if ref_id != u_id:
                ref_by = ref_id
                ref_setting = await settings_col.find_one({"key": "ref_price"})
                bonus = ref_setting.get("value", 0) if ref_setting else 0
                await users_col.update_one({"user_id": ref_id}, {"$inc": {"balance": bonus, "ref_count": 1}})
                await bot.send_message(ref_id, f"🎉 Sizda yangi referal! Hisobingizga {bonus} so'm qo'shildi.")

        await users_col.insert_one({
            "user_id": u_id, "name": message.from_user.full_name, "balance": 0,
            "ref_by": ref_by, "ref_count": 0, "total_pay": 0, "used_promos": [], "joined_at": datetime.now()
        })
    
    await message.answer("Bot ishlamasa /start tugmasini bosing.", reply_markup=main_kb(u_id))

# --- USER: ORDERING ---
@dp.message(F.text == "🛒 Xizmatlar")
async def show_cats(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats: return await message.answer("Bo'limlar yo'q.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"user_cat_{c['_id']}")] for c in cats])
    await message.answer("Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("user_cat_"))
async def show_servs(call: types.CallbackQuery):
    cat_id = call.data.split("_")[2]
    servs = await services_col.find({"cat_id": cat_id}).to_list(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"buy_s_{s['_id']}")] for s in servs])
    await call.message.edit_text("Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_s_"))
async def buy_step1(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[2]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await call.message.answer("🔗 Havolani yuboring:", reply_markup=back_kb())
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link, F.text != "⬅️ Ortga")
async def buy_step2(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Miqdorni kiriting:", reply_markup=back_kb())
    await state.set_state(UserState.order_qty)

@dp.message(UserState.order_qty, F.text.isdigit())
async def buy_step3(message: types.Message, state: FSMContext):
    qty = int(message.text)
    data = await state.get_data()
    total = (data['s_price'] / 1000) * qty
    await state.update_data(qty=qty, total=total)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="conf_ord"),
         InlineKeyboardButton(text="⬅️ Ortga", callback_data="cancel_ord")]
    ])
    await message.answer(f"Buyurtma: {data['s_name']}\nLink: {data['link']}\nJami: {total:,} so'm", reply_markup=kb)
    await state.set_state(UserState.order_confirm)

@dp.callback_query(F.data == "conf_ord", UserState.order_confirm)
async def buy_final(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await users_col.find_one({"user_id": call.from_user.id})
    if user['balance'] < data['total']: return await call.answer("Mablag' yetarli emas!", show_alert=True)
    
    await users_col.update_one({"user_id": call.from_user.id}, {"$inc": {"balance": -data['total']}})
    order_id = str(uuid.uuid4())[:6].upper()
    await orders_col.insert_one({
        "order_id": order_id, "user_id": call.from_user.id, "user_name": call.from_user.full_name,
        "service": data['s_name'], "link": data['link'], "total": data['total'], "status": "Kutilmoqda", "date": datetime.now()
    })
    
    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_o_yes_{order_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_o_no_{order_id}")]
    ])
    await bot.send_message(ADMIN_ID, f"📦 Buyurtma #{order_id}\nUser: {call.from_user.full_name} ({call.from_user.id})\nLink: {data['link']}\nSumma: {data['total']:,}\nQoldiq: {user['balance']-data['total']:,}", reply_markup=adm_kb)
    await call.message.edit_text("✅ Buyurtma yuborildi!")
    await state.clear()

# --- ADMIN: ORDER STATUS ---
@dp.callback_query(F.data.startswith("adm_o_"))
async def adm_order_res(call: types.CallbackQuery):
    _, _, res, o_id = call.data.split("_")
    order = await orders_col.find_one({"order_id": o_id})
    if res == "yes":
        await orders_col.update_one({"order_id": o_id}, {"$set": {"status": "Bajarildi"}})
        await bot.send_message(order['user_id'], f"✅ Buyurtmangiz #{o_id} bajarildi!")
    else:
        await users_col.update_one({"user_id": order['user_id']}, {"$inc": {"balance": order['total']}})
        await orders_col.update_one({"order_id": o_id}, {"$set": {"status": "Rad etildi"}})
        await bot.send_message(order['user_id'], f"❌ Buyurtmangiz #{o_id} rad etildi, pul qaytarildi.")
    await call.message.delete()

# --- USER: REFILL BALANCE ---
@dp.message(F.text == "💳 To'lov qilish")
async def fill_pay(message: types.Message, state: FSMContext):
    card = await settings_col.find_one({"key": "card"})
    if not card: return await message.answer("Karta sozlanmagan.")
    await message.answer(f"Karta: `{card['number']}`\nEga: {card['owner']}\n\nTo'lov chekini yuboring:", parse_mode="Markdown", reply_markup=back_kb())
    await state.set_state(UserState.fill_receipt)

@dp.message(UserState.fill_receipt, F.photo)
async def fill_r(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("Summani kiriting:")
    await state.set_state(UserState.fill_amount)

@dp.message(UserState.fill_amount, F.text.isdigit())
async def fill_a(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = int(message.text)
    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_p_yes_{message.from_user.id}_{amount}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_p_no_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"💰 To'lov: {amount:,} so'm\nUser: {message.from_user.full_name} ({message.from_user.id})", reply_markup=adm_kb)
    await message.answer("✅ Adminga yuborildi.", reply_markup=main_kb(message.from_user.id))
    await state.clear()

@dp.callback_query(F.data.startswith("adm_p_"))
async def adm_pay_res(call: types.CallbackQuery):
    _, _, res, u_id, *amt = call.data.split("_")
    u_id = int(u_id)
    if res == "yes":
        amount = int(amt[0])
        await users_col.update_one({"user_id": u_id}, {"$inc": {"balance": amount, "total_pay": amount}})
        await bot.send_message(u_id, f"✅ To'lovingiz tasdiqlandi: +{amount:,} so'm")
    else:
        await bot.send_message(u_id, "❌ To'lovingiz rad etildi.")
    await call.message.delete()

# --- REFERRAL & STATS ---
@dp.message(F.text == "👥 Referal")
async def ref_page(message: types.Message):
    user = await users_col.find_one({"user_id": message.from_user.id})
    bot_info = await bot.get_me()
    ref_link = f"https://t.me/{bot_info.username}?start={message.from_user.id}"
    await message.answer(f"Sizning referal havolangiz:\n{ref_link}\n\nChaqirilganlar: {user['ref_count']} ta")

@dp.message(F.text == "📊 Statistika")
async def user_stat_page(message: types.Message):
    today = datetime.now().replace(hour=0, minute=0, second=0)
    month = today.replace(day=1)
    t_users = await users_col.count_documents({})
    t_orders = await orders_col.count_documents({"date": {"$gte": today}})
    user = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"Bot foydalanuvchilari: {t_users}\nBugungi buyurtmalar: {t_orders}\nSizning jami to'lovingiz: {user.get('total_pay', 0):,} so'm")

@dp.message(F.text == "🏆 TOP")
async def top_page(message: types.Message):
    top_ref = await users_col.find().sort("ref_count", -1).limit(5).to_list(None)
    top_pay = await users_col.find().sort("total_pay", -1).limit(5).to_list(None)
    text = "🏆 TOP Referallar:\n"
    for i, u in enumerate(top_ref, 1): text += f"{i}. {u['name']} - {u['ref_count']} ta\n"
    text += "\n💰 TOP To'lovlar:\n"
    for i, u in enumerate(top_pay, 1): text += f"{i}. {u['name']} - {u.get('total_pay', 0):,} so'm\n"
    await message.answer(text)

# --- PROMOKOD ---
@dp.message(F.text == "🎁 Promokod")
async def promo_page(message: types.Message, state: FSMContext):
    await message.answer("Promokodni kiriting:", reply_markup=back_kb())
    await state.set_state(UserState.enter_promo)

@dp.message(UserState.enter_promo, F.text != "⬅️ Ortga")
async def promo_apply(message: types.Message, state: FSMContext):
    promo = await promos_col.find_one({"code": message.text})
    if not promo or promo['used'] >= promo['limit']: return await message.answer("Xato yoki limit tugagan.")
    user = await users_col.find_one({"user_id": message.from_user.id})
    if message.text in user['used_promos']: return await message.answer("Siz ishlatgansiz.")
    
    await users_col.update_one({"user_id": message.from_user.id}, {"$inc": {"balance": promo['amount']}, "$push": {"used_promos": promo['code']}})
    await promos_col.update_one({"code": promo['code']}, {"$inc": {"used": 1}})
    await message.answer(f"✅ +{promo['amount']:,} so'm qo'shildi!")
    await state.clear()

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
@dp.message(F.text == "🛠 Admin Panel")
async def adm_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panel:", reply_markup=admin_kb())

@dp.message(F.text == "⬅️ Ortga")
async def go_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyu", reply_markup=main_kb(message.from_user.id))

@dp.message(F.text == "🏠 Bosh menyu")
async def go_home(message: types.Message):
    await message.answer("Bosh menyu", reply_markup=main_kb(message.from_user.id))

# --- RENDER SERVER ---
async def handle(request): return web.Response(text="Bot is running!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

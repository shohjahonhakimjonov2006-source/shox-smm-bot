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
TOKEN = "8678413684:AAFfK4PTF7_QFT5V-tRsd6GlLT3kWB2h7D8"
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
    set_card_num = State()
    set_card_owner = State()
    set_ref_reward = State()
    promo_code = State()
    promo_amount = State()
    promo_limit = State()
    broadcast_msg = State()
    add_sub_channel = State()
    edit_bal_id = State()
    edit_bal_amt = State()
    del_cat = State()

class UserState(StatesGroup):
    order_link = State()
    order_qty = State()
    order_confirm = State()
    fill_receipt = State()
    fill_amount = State()
    enter_promo = State()
    help_text = State()

# --- KEYBOARDS ---
def main_menu(uid):
    btns = [
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="💳 To'lov qilish"), KeyboardButton(text="📦 Buyurtmalarim")],
        [KeyboardButton(text="👥 Referal"), KeyboardButton(text="🎁 Promokod")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🏆 TOP")],
        [KeyboardButton(text="🆘 Yordam")]
    ]
    if uid == ADMIN_ID:
        btns.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim qo'shish"), KeyboardButton(text="❌ Bo'lim o'chirish")],
        [KeyboardButton(text="➕ Xizmat qo'shish"), KeyboardButton(text="📉 Admin Statistika")],
        [KeyboardButton(text="💳 Karta sozlash"), KeyboardButton(text="🏆 Admin TOP")],
        [KeyboardButton(text="🎁 Promo yaratish"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="💰 Ref Summa"), KeyboardButton(text="➕ Majburiy obuna")],
        [KeyboardButton(text="👤 Balansni tahrirlash"), KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga")]], resize_keyboard=True)

# --- MIDDLEWARE (SUB CHECK) ---
async def check_subscription(uid):
    channel_data = await settings_col.find_one({"key": "sub_channel"})
    if not channel_data: return True
    try:
        member = await bot.get_chat_member(chat_id=channel_data['id'], user_id=uid)
        return member.status not in ["left", "kicked"]
    except: return True

# --- START ---
@dp.message(Command("start"))
async def start_handler(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    
    if not await check_subscription(uid):
        ch = await settings_col.find_one({"key": "sub_channel"})
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Kanalga obuna bo'lish", url=ch['url'])],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
        ])
        return await message.answer("Botdan foydalanish uchun kanalga obuna bo'ling!", reply_markup=kb)

    user = await users_col.find_one({"user_id": uid})
    if not user:
        ref_id = int(command.args) if command.args and command.args.isdigit() else None
        if ref_id and ref_id != uid:
            ref_setting = await settings_col.find_one({"key": "ref_reward"})
            reward = ref_setting['val'] if ref_setting else 0
            await users_col.update_one({"user_id": ref_id}, {"$inc": {"balance": reward, "ref_count": 1}})
            try: await bot.send_message(ref_id, f"🎁 Yangi referal! Hisobingizga {reward} so'm qo'shildi.")
            except: pass

        await users_col.insert_one({
            "user_id": uid, "name": message.from_user.full_name, "balance": 0,
            "ref_count": 0, "total_pay": 0, "joined_at": datetime.now(), "used_promos": []
        })
    
    await message.answer("Xizmat ko'rsatish botiga xush kelibsiz!", reply_markup=main_menu(uid))

# --- ADMIN: BO'LIM VA XIZMATLAR (Tuzatildi) ---
@dp.message(F.text == "📂 Bo'lim qo'shish", F.from_user.id == ADMIN_ID)
async def adm_add_cat_start(message: types.Message, state: FSMContext):
    await message.answer("Yangi bo'lim nomini yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat, F.text != "⬅️ Ortga")
async def adm_add_cat_save(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ {message.text} bo'limi qo'shildi!", reply_markup=admin_menu())
    await state.clear()

@dp.message(F.text == "➕ Xizmat qo'shish", F.from_user.id == ADMIN_ID)
async def adm_add_serv_start(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats: return await message.answer("Avval bo'lim qo'shishingiz kerak!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"addserv_{c['_id']}")] for c in cats])
    await message.answer("Xizmat qaysi bo'limga qo'shilsin?", reply_markup=kb)

@dp.callback_query(F.data.startswith("addserv_"))
async def adm_add_serv_name(call: types.CallbackQuery, state: FSMContext):
    cat_id = call.data.split("_")[1]
    await state.update_data(cat_id=cat_id)
    await call.message.answer("Xizmat nomini yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.add_serv_name)

@dp.message(AdminState.add_serv_name, F.text != "⬅️ Ortga")
async def adm_add_serv_price(message: types.Message, state: FSMContext):
    await state.update_data(s_name=message.text)
    await message.answer("Xizmat narxini yozing (faqat son):")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price, F.text.isdigit())
async def adm_add_serv_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await services_col.insert_one({
        "cat_id": data['cat_id'],
        "name": data['s_name'],
        "price": int(message.text)
    })
    await message.answer("✅ Xizmat muvaffaqiyatli qo'shildi!", reply_markup=admin_menu())
    await state.clear()

# --- ADMIN: KARTA SOZLASH ---
@dp.message(F.text == "💳 Karta sozlash", F.from_user.id == ADMIN_ID)
async def adm_card_start(message: types.Message, state: FSMContext):
    await message.answer("Karta raqamini yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.set_card_num)

@dp.message(AdminState.set_card_num, F.text != "⬅️ Ortga")
async def adm_card_name(message: types.Message, state: FSMContext):
    await state.update_data(c_num=message.text)
    await message.answer("Karta egasi ismini yozing:")
    await state.set_state(AdminState.set_card_owner)

@dp.message(AdminState.set_card_owner, F.text != "⬅️ Ortga")
async def adm_card_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await settings_col.update_one({"key": "card"}, {"$set": {"num": data['c_num'], "owner": message.text}}, upsert=True)
    await message.answer("✅ Karta ma'lumotlari saqlandi!", reply_markup=admin_menu())
    await state.clear()

# --- ADMIN: STATISTIKA (Tuzatildi) ---
@dp.message(F.text == "📉 Admin Statistika", F.from_user.id == ADMIN_ID)
async def adm_stats(message: types.Message):
    total_users = await users_col.count_documents({})
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    users_today = await users_col.count_documents({"joined_at": {"$gte": today}})
    orders_today = await orders_col.count_documents({"date": {"$gte": today}})
    
    # Umumiy balanslar yig'indisi
    all_users = await users_col.find().to_list(None)
    total_balance = sum(u.get('balance', 0) for u in all_users)
    total_payments = sum(u.get('total_pay', 0) for u in all_users)

    text = (
        f"📊 **Bot Statistikasi**\n\n"
        f"👤 Jami foydalanuvchilar: {total_users}\n"
        f"🆕 Bugun qo'shilganlar: {users_today}\n"
        f"📦 Bugungi buyurtmalar: {orders_today}\n"
        f"💰 Foydalanuvchilar jami balansi: {total_balance:,} so'm\n"
        f"💳 Jami qilingan to'lovlar: {total_payments:,} so'm"
    )
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN: TOP (TALAB 7) ---
@dp.message(F.text == "🏆 Admin TOP", F.from_user.id == ADMIN_ID)
async def admin_top_lists(message: types.Message):
    # TOP 10 To'lovchilar
    top_payers = await users_col.find().sort("total_pay", -1).limit(10).to_list(None)
    payer_text = "💰 **TOP 10 Eng ko'p to'lov qilganlar:**\n"
    for i, u in enumerate(top_payers, 1):
        payer_text += f"{i}. {u['name']} | ID: `{u['user_id']}` | {u['total_pay']:,} so'm\n"
    
    # TOP 19 Referallar
    top_refs = await users_col.find().sort("ref_count", -1).limit(19).to_list(None)
    ref_text = "\n👥 **TOP 19 Eng ko'p referal keltirganlar:**\n"
    for i, u in enumerate(top_refs, 1):
        ref_text += f"{i}. {u['name']} | ID: `{u['user_id']}` | {u['ref_count']} ta\n"
        
    await message.answer(payer_text + ref_text, parse_mode="Markdown")

# --- ADMIN: PROMO (TALAB 8, 10) ---
@dp.message(F.text == "🎁 Promo yaratish", F.from_user.id == ADMIN_ID)
async def adm_promo1(message: types.Message, state: FSMContext):
    await message.answer("Yangi Promo-kod nomini yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.promo_code)

@dp.message(AdminState.promo_code, F.text != "⬅️ Ortga")
async def adm_promo2(message: types.Message, state: FSMContext):
    await state.update_data(p_code=message.text.upper())
    await message.answer("Promo-kod summasini kiriting:")
    await state.set_state(AdminState.promo_amount)

@dp.message(AdminState.promo_amount, F.text.isdigit())
async def adm_promo3(message: types.Message, state: FSMContext):
    await state.update_data(p_amt=int(message.text))
    await message.answer("Promo-kod necha kishi uchun ishlasin (limit):")
    await state.set_state(AdminState.promo_limit)

@dp.message(AdminState.promo_limit, F.text.isdigit())
async def adm_promo_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_code, p_amt, p_lim = data['p_code'], data['p_amt'], int(message.text)
    
    await promos_col.insert_one({"code": p_code, "amount": p_amt, "limit": p_lim, "used": 0})
    await message.answer(f"✅ Promo-kod yaratildi!")
    
    # Barcha foydalanuvchilarga reklama
    users = await users_col.find().to_list(None)
    for u in users:
        try:
            await bot.send_message(u['user_id'], f"🎁 **Yangi Promo-kod!**\n\nKod: `{p_code}`\nSumma: {p_amt:,} so'm\nLimit: {p_lim} kishi uchun!\n\nTezroq botga kirib ishlating!")
        except: continue
    await state.clear()

# --- ADMIN: MAJBURIY OBUNA (TALAB 13) ---
@dp.message(F.text == "➕ Majburiy obuna", F.from_user.id == ADMIN_ID)
async def adm_sub_start(message: types.Message, state: FSMContext):
    await message.answer("Kanal IDsi va Linkini yuboring.\nFormat: `-100123 | https://t.me/link`", reply_markup=back_kb())
    await state.set_state(AdminState.add_sub_channel)

@dp.message(AdminState.add_sub_channel, F.text != "⬅️ Ortga")
async def adm_sub_save(message: types.Message, state: FSMContext):
    try:
        cid, clink = message.text.split(" | ")
        await settings_col.update_one({"key": "sub_channel"}, {"$set": {"id": cid.strip(), "url": clink.strip()}}, upsert=True)
        await message.answer("✅ Majburiy obuna kanali saqlandi!", reply_markup=admin_menu())
        await state.clear()
    except:
        await message.answer("Xato format! Namuna: `-100123 | https://t.me/link`")

# --- ADMIN: BROADCAST ---
@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def adm_bc_start(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg, F.text != "⬅️ Ortga")
async def adm_bc_send(message: types.Message, state: FSMContext):
    users = await users_col.find().to_list(None)
    count = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.text)
            count += 1
        except: continue
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yuborildi.", reply_markup=admin_menu())
    await state.clear()

# --- FOYDALANUVCHI: STATISTIKA ---
@dp.message(F.text == "📊 Statistika")
async def user_stats(message: types.Message):
    uid = message.from_user.id
    user = await users_col.find_one({"user_id": uid})
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    total_u = await users_col.count_documents({})
    today_u = await users_col.count_documents({"joined_at": {"$gte": today}})
    today_o = await orders_col.count_documents({"date": {"$gte": today}})
    
    text = (
        f"📊 **Bot statistikasi**\n\n"
        f"👤 Jami foydalanuvchilar: {total_u}\n"
        f"🆕 Bugun qo'shilganlar: {today_u}\n"
        f"📦 Bugungi jami buyurtmalar: {today_o}\n\n"
        f"💰 Sizning jami to'lovingiz: {user.get('total_pay', 0):, } so'm"
    )
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN PANEL KIRISH ---
@dp.message(F.text == "🛠 Admin Panel", F.from_user.id == ADMIN_ID)
async def adm_panel_entry(message: types.Message):
    await message.answer("Admin boshqaruv paneliga xush kelibsiz!", reply_markup=admin_menu())

@dp.message(F.text == "🏠 Bosh menyu")
@dp.message(F.text == "⬅️ Ortga")
async def back_to_main(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyuga qaytdingiz.", reply_markup=main_menu(message.from_user.id))

# --- SERVER ---
async def handle(request): return web.Response(text="Bot Active")

async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

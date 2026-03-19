import asyncio
import logging
import os
import uuid
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton
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
        [KeyboardButton(text="📂 Bo'lim/Xizmat boshqaruvi")],
        [KeyboardButton(text="📉 Admin Statistika"), KeyboardButton(text="🏆 Admin TOP")],
        [KeyboardButton(text="💳 Karta sozlash"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="🎁 Promo yaratish"), KeyboardButton(text="💰 Ref Summa")],
        [KeyboardButton(text="➕ Majburiy obuna"), KeyboardButton(text="👤 Balansni tahrirlash")],
        [KeyboardButton(text="🏠 Bosh menyu")]
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

# --- START & REGISTRATION ---
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
    
    await message.answer("Botga xush kelibsiz! Kerakli bo'limni tanlang.", reply_markup=main_menu(uid))

# --- ADMIN: TOP LISTS (TALAAB 7) ---
@dp.message(F.text == "🏆 Admin TOP", F.from_user.id == ADMIN_ID)
async def admin_top_lists(message: types.Message):
    # TOP 10 To'lovchilar
    top_payers = await users_col.find().sort("total_pay", -1).limit(10).to_list(None)
    payer_text = "💰 **TOP 10 To'lov qilganlar:**\n"
    for i, u in enumerate(top_payers, 1):
        payer_text += f"{i}. {u['name']} (ID: `{u['user_id']}`) — {u['total_pay']:,} so'm\n"
    
    # TOP 19 Referallar
    top_refs = await users_col.find().sort("ref_count", -1).limit(19).to_list(None)
    ref_text = "\n👥 **TOP 19 Referal yig'ganlar:**\n"
    for i, u in enumerate(top_refs, 1):
        ref_text += f"{i}. {u['name']} (ID: `{u['user_id']}`) — {u['ref_count']} ta\n"
        
    await message.answer(payer_text + ref_text, parse_mode="Markdown")

# --- ADMIN: PROMO SYSTEM (TALAB 8, 10) ---
@dp.message(F.text == "🎁 Promo yaratish", F.from_user.id == ADMIN_ID)
async def adm_promo1(message: types.Message, state: FSMContext):
    await message.answer("Yangi Promo-kod nomini yozing (Masalan: UZBEK):", reply_markup=back_kb())
    await state.set_state(AdminState.promo_code)

@dp.message(AdminState.promo_code, F.text != "⬅️ Ortga")
async def adm_promo2(message: types.Message, state: FSMContext):
    await state.update_data(p_code=message.text.upper())
    await message.answer("Promo-kod summasini kiriting:")
    await state.set_state(AdminState.promo_amount)

@dp.message(AdminState.promo_amount, F.text.isdigit())
async def adm_promo3(message: types.Message, state: FSMContext):
    await state.update_data(p_amt=int(message.text))
    await message.answer("Promo-kod ishlatilish sonini (limit) kiriting:")
    await state.set_state(AdminState.promo_limit)

@dp.message(AdminState.promo_limit, F.text.isdigit())
async def adm_promo_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    p_code = data['p_code']
    p_amt = data['p_amt']
    p_lim = int(message.text)
    
    await promos_col.insert_one({"code": p_code, "amount": p_amt, "limit": p_lim, "used": 0})
    await message.answer(f"✅ Promo-kod yaratildi va barchaga yuborilmoqda!", reply_markup=admin_menu())
    
    # Barchaga reklama (Talab 10)
    users = await users_col.find().to_list(None)
    for u in users:
        try: await bot.send_message(u['user_id'], f"🎁 Yangi Promo-kod: `{p_code}`\n💰 Summa: {p_amt:,} so'm\n🔢 Limit: {p_lim} kishiga!")
        except: continue
    await state.clear()

# --- ADMIN: REFERRAL REWARD (TALAB 9) ---
@dp.message(F.text == "💰 Ref Summa", F.from_user.id == ADMIN_ID)
async def adm_ref_reward(message: types.Message, state: FSMContext):
    await message.answer("Har bir yangi referal uchun beriladigan summani kiriting (o'chirish uchun 0):", reply_markup=back_kb())
    await state.set_state(AdminState.set_ref_reward)

@dp.message(AdminState.set_ref_reward, F.text.isdigit())
async def adm_ref_save(message: types.Message, state: FSMContext):
    amt = int(message.text)
    await settings_col.update_one({"key": "ref_reward"}, {"$set": {"val": amt}}, upsert=True)
    await message.answer(f"✅ Referal summasi {amt} so'mga o'rnatildi.", reply_markup=admin_menu())
    await state.clear()

# --- ADMIN: MAJBURIY OBUNA (TALAB 13) ---
@dp.message(F.text == "➕ Majburiy obuna", F.from_user.id == ADMIN_ID)
async def adm_sub1(message: types.Message, state: FSMContext):
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ Obunani o'chirish", callback_data="del_sub")]])
    await message.answer("Kanal ID raqamini va URLini kiriting.\nFormat: `ID | URL` (Masalan: `-100123456 | https://t.me/kanal`)", parse_mode="Markdown", reply_markup=kb)
    await state.set_state(AdminState.add_sub_channel)

@dp.message(AdminState.add_sub_channel, F.text.contains("|"))
async def adm_sub2(message: types.Message, state: FSMContext):
    cid, curl = message.text.split("|")
    await settings_col.update_one({"key": "sub_channel"}, {"$set": {"id": cid.strip(), "url": curl.strip()}}, upsert=True)
    await message.answer("✅ Majburiy obuna kanali o'rnatildi.", reply_markup=admin_menu())
    await state.clear()

@dp.callback_query(F.data == "del_sub")
async def adm_sub_del(call: types.CallbackQuery):
    await settings_col.delete_one({"key": "sub_channel"})
    await call.message.edit_text("✅ Majburiy obuna o'chirildi.")

# --- ADMIN: BROADCAST (TALAB 12) ---
@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def adm_bc1(message: types.Message, state: FSMContext):
    await message.answer("Barcha foydalanuvchilarga yuboriladigan xabarni yozing:", reply_markup=back_kb())
    await state.set_state(AdminState.broadcast_msg)

@dp.message(AdminState.broadcast_msg, F.text != "⬅️ Ortga")
async def adm_bc2(message: types.Message, state: FSMContext):
    users = await users_col.find().to_list(None)
    for u in users:
        try: await bot.send_message(u['user_id'], message.text)
        except: continue
    await message.answer("✅ Xabar hamma foydalanuvchilarga yuborildi.", reply_markup=admin_menu())
    await state.clear()

# --- USER: HELP (TALAB 11) ---
@dp.message(F.text == "🆘 Yordam")
async def user_help(message: types.Message, state: FSMContext):
    await message.answer("Admin uchun xabaringizni yozing:", reply_markup=back_kb())
    await state.set_state(UserState.help_text)

@dp.message(UserState.help_text, F.text != "⬅️ Ortga")
async def user_help_send(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 **Yangi xabar (Yordam):**\n👤 FIO: {message.from_user.full_name}\n🆔 ID: `{message.from_user.id}`\n\n💬 Matn: {message.text}", parse_mode="Markdown")
    await message.answer("✅ Xabaringiz adminga yuborildi. Tez orada javob olasiz.", reply_markup=main_menu(message.from_user.id))
    await state.clear()

# --- ADMIN PANEL ---
@dp.message(F.text == "🛠 Admin Panel", F.from_user.id == ADMIN_ID)
async def adm_panel(message: types.Message):
    await message.answer("Admin boshqaruv paneliga xush kelibsiz:", reply_markup=admin_menu())

@dp.message(F.text == "🏠 Bosh menyu")
@dp.message(F.text == "⬅️ Ortga")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Asosiy menyuga qaytdingiz.", reply_markup=main_menu(message.from_user.id))

# --- SERVER RUN (RENDER CONFLICT FIX) ---
async def handle(request): return web.Response(text="Bot is running smoothly!")

async def main():
    # Render port
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    # Conflict oldini olish
    await bot.delete_webhook(drop_pending_updates=True)
    logging.info("🚀 Bot start polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

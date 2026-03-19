import asyncio
import logging
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import *
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

# ================= CONFIG =================
TOKEN = "PASTE_NEW_TOKEN"
ADMIN_ID = 7861165622
MONGO_URL = "mongodb://localhost:27017"

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# ================= DB =================
client = AsyncIOMotorClient(MONGO_URL)
db = client["smm_bot"]
users = db["users"]
services = db["services"]
categories = db["categories"]
orders = db["orders"]
settings = db["settings"]
promos = db["promos"]

# ================= STATES =================
class AdminState(StatesGroup):
    add_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    set_ref = State()
    promo_code = State()
    promo_amount = State()
    promo_limit = State()
    broadcast = State()
    sub_channel = State()

class UserState(StatesGroup):
    promo = State()
    help = State()

# ================= KEYBOARDS =================
def main_menu(uid):
    kb = [
        [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
        [KeyboardButton(text="🎁 Promokod"), KeyboardButton(text="👥 Referal")],
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🆘 Yordam")]
    ]
    if uid == ADMIN_ID:
        kb.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim qo'shish"), KeyboardButton(text="➕ Xizmat qo'shish")],
        [KeyboardButton(text="🏆 Admin TOP"), KeyboardButton(text="📉 Statistika")],
        [KeyboardButton(text="🎁 Promo yaratish"), KeyboardButton(text="❌ Promo o'chirish")],
        [KeyboardButton(text="💰 Ref summa"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="➕ Majburiy obuna"), KeyboardButton(text="❌ Majburiy obuna o'chirish")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# ================= SUB CHECK =================
async def check_sub(uid):
    sub = await settings.find_one({"key": "sub"})
    if not sub:
        return True
    try:
        member = await bot.get_chat_member(sub['id'], uid)
        return member.status not in ["left", "kicked"]
    except:
        return True

# ================= START =================
@dp.message(Command("start"))
async def start(msg: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    uid = msg.from_user.id

    if not await check_sub(uid):
        sub = await settings.find_one({"key": "sub"})
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Obuna bo'lish", url=sub['url'])],
            [InlineKeyboardButton(text="Tekshirish", callback_data="check_sub")]
        ])
        return await msg.answer("Avval kanalga obuna bo‘ling", reply_markup=kb)

    user = await users.find_one({"user_id": uid})
    if not user:
        await users.insert_one({
            "user_id": uid,
            "name": msg.from_user.full_name,
            "balance": 0,
            "ref_count": 0,
            "total_pay": 0,
            "used_promos": []
        })

    await msg.answer("Xush kelibsiz!", reply_markup=main_menu(uid))

# ================= ADMIN PANEL =================
@dp.message(F.text == "🛠 Admin Panel")
async def admin_panel(msg: types.Message):
    if msg.from_user.id == ADMIN_ID:
        await msg.answer("Admin panel", reply_markup=admin_menu())

# ================= TOP =================
@dp.message(F.text == "🏆 Admin TOP")
async def top(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return

    payers = await users.find().sort("total_pay", -1).limit(10).to_list(None)
    text = "🏆 TOP 10 To'lov:\n\n"
    for i, u in enumerate(payers, 1):
        text += f"{i}. {u['name']} | {u['total_pay']:,}\n"

    refs = await users.find().sort("ref_count", -1).limit(19).to_list(None)
    text += "\n👥 TOP Referal:\n\n"
    for i, u in enumerate(refs, 1):
        text += f"{i}. {u['name']} | {u['ref_count']} ta\n"

    await msg.answer(text)

# ================= PROMO CREATE =================
@dp.message(F.text == "🎁 Promo yaratish")
async def promo1(msg: types.Message, state: FSMContext):
    await msg.answer("Promo kod:")
    await state.set_state(AdminState.promo_code)

@dp.message(AdminState.promo_code)
async def promo2(msg: types.Message, state: FSMContext):
    await state.update_data(code=msg.text.upper())
    await msg.answer("Summa:")
    await state.set_state(AdminState.promo_amount)

@dp.message(AdminState.promo_amount)
async def promo3(msg: types.Message, state: FSMContext):
    await state.update_data(amount=int(msg.text))
    await msg.answer("Limit:")
    await state.set_state(AdminState.promo_limit)

@dp.message(AdminState.promo_limit)
async def promo_save(msg: types.Message, state: FSMContext):
    data = await state.get_data()
    await promos.insert_one({
        "code": data['code'],
        "amount": data['amount'],
        "limit": int(msg.text),
        "used": 0
    })

    users_list = await users.find().to_list(None)
    for u in users_list:
        try:
            await bot.send_message(u['user_id'], f"🎁 Yangi promo: {data['code']}")
        except:
            pass

    await msg.answer("Promo yaratildi", reply_markup=admin_menu())
    await state.clear()

# ================= DELETE PROMO =================
@dp.message(F.text == "❌ Promo o'chirish")
async def delpromo(msg: types.Message):
    if msg.from_user.id != ADMIN_ID: return

    pr = await promos.find().to_list(None)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=p['code'], callback_data=f"del_{p['_id']}")]
        for p in pr
    ])
    await msg.answer("Tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("del_"))
async def delpromo2(call: CallbackQuery):
    pid = call.data.split("_")[1]
    await promos.delete_one({"_id": ObjectId(pid)})
    await call.message.answer("O‘chirildi")

# ================= PROMO USER =================
@dp.message(F.text == "🎁 Promokod")
async def promo_user(msg: types.Message, state: FSMContext):
    await msg.answer("Kod:")
    await state.set_state(UserState.promo)

@dp.message(UserState.promo)
async def promo_apply(msg: types.Message, state: FSMContext):
    code = msg.text.upper()
    user = await users.find_one({"user_id": msg.from_user.id})
    promo = await promos.find_one({"code": code})

    if not promo:
        return await msg.answer("Topilmadi")

    if promo['used'] >= promo['limit']:
        return await msg.answer("Limit tugagan")

    if code in user.get("used_promos", []):
        return await msg.answer("Ishlatilgansiz")

    await users.update_one(
        {"user_id": msg.from_user.id},
        {"$inc": {"balance": promo['amount']}, "$push": {"used_promos": code}}
    )
    await promos.update_one({"code": code}, {"$inc": {"used": 1}})

    await msg.answer(f"{promo['amount']} qo‘shildi")
    await state.clear()

# ================= REF SETTINGS =================
@dp.message(F.text == "💰 Ref summa")
async def ref_set(msg: types.Message, state: FSMContext):
    await msg.answer("Summani kiriting:")
    await state.set_state(AdminState.set_ref)

@dp.message(AdminState.set_ref)
async def ref_save(msg: types.Message, state: FSMContext):
    await settings.update_one(
        {"key": "ref"},
        {"$set": {"val": int(msg.text)}},
        upsert=True
    )
    await msg.answer("Saqlandi")
    await state.clear()

# ================= HELP =================
@dp.message(F.text == "🆘 Yordam")
async def help1(msg: types.Message, state: FSMContext):
    await msg.answer("Yozing:")
    await state.set_state(UserState.help)

@dp.message(UserState.help)
async def help2(msg: types.Message, state: FSMContext):
    await bot.send_message(
        ADMIN_ID,
        f"{msg.from_user.full_name} ({msg.from_user.id})\n{msg.text}"
    )
    await msg.answer("Yuborildi")
    await state.clear()

# ================= BROADCAST =================
@dp.message(F.text == "📢 Xabar yuborish")
async def bc1(msg: types.Message, state: FSMContext):
    await msg.answer("Xabar:")
    await state.set_state(AdminState.broadcast)

@dp.message(AdminState.broadcast)
async def bc2(msg: types.Message, state: FSMContext):
    all_users = await users.find().to_list(None)
    for u in all_users:
        try:
            await bot.send_message(u['user_id'], msg.text)
        except:
            pass
    await msg.answer("Yuborildi")
    await state.clear()

# ================= SUB =================
@dp.message(F.text == "➕ Majburiy obuna")
async def sub1(msg: types.Message, state: FSMContext):
    await msg.answer("Format: ID | link")
    await state.set_state(AdminState.sub_channel)

@dp.message(AdminState.sub_channel)
async def sub2(msg: types.Message, state: FSMContext):
    cid, link = msg.text.split("|")
    await settings.update_one(
        {"key": "sub"},
        {"$set": {"id": cid.strip(), "url": link.strip()}},
        upsert=True
    )
    await msg.answer("Saqlandi")
    await state.clear()

@dp.message(F.text == "❌ Majburiy obuna o'chirish")
async def sub_del(msg: types.Message):
    await settings.delete_one({"key": "sub"})
    await msg.answer("O‘chirildi")

# ================= RUN =================
async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

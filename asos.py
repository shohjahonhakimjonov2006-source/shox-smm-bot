import asyncio
import logging
import os
import uuid
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F, MAGIC_FILTER
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
)
from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId

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
    set_ref_price = State()
    create_promo = State()
    promo_limit = State()
    promo_amount = State()
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
        [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🏆 TOP"), KeyboardButton(text="🆘 Yordam")]
    ]
    if user_id == ADMIN_ID:
        btns.append([KeyboardButton(text="🛠 Admin Panel")])
    return ReplyKeyboardMarkup(keyboard=btns, resize_keyboard=True)

def back_kb():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga")]], resize_keyboard=True)

def admin_kb():
    return ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="📂 Bo'lim/Xizmat"), KeyboardButton(text="💳 Karta sozlash")],
        [KeyboardButton(text="💰 Ref/Promo sozlash"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="📉 Admin Statistika"), KeyboardButton(text="➕ Majburiy obuna")],
        [KeyboardButton(text="👤 Balansni boshqarish"), KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

# --- MIDDLEWARE (MAJBURIY OBUNA) ---
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
    
    # Majburiy obuna tekshiruvi
    if not await check_sub(u_id):
        setting = await settings_col.find_one({"key": "channels"})
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Obuna bo'lish", url=f"https://t.me/{setting['list'][0].replace('@','')}")],
                                                   [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]])
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
            "ref_by": ref_by, "ref_count": 0, "total_pay": 0, "joined_at": datetime.now()
        })
    
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang.", reply_markup=main_kb(u_id))

# --- USER: ORDERING LOGIC ---
@dp.callback_query(F.data.startswith("buy_serv_"))
async def order_step1(call: types.CallbackQuery, state: FSMContext):
    s_id = call.data.split("_")[2]
    service = await services_col.find_one({"_id": ObjectId(s_id)})
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await call.message.answer(f"Xizmat: {service['name']}\nNarxi: {service['price']} so'm\n🔗 Havolani yuboring:", reply_markup=back_kb())
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link, F.text != "⬅️ Ortga")
async def order_step2(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("Miqdorni kiriting:", reply_markup=back_kb())
    await state.set_state(UserState.order_qty)

@dp.message(UserState.order_qty, F.text.isdigit())
async def order_step3(message: types.Message, state: FSMContext):
    qty = int(message.text)
    data = await state.get_data()
    total = (data['s_price'] / 1000) * qty
    await state.update_data(qty=qty, total=total)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="confirm_order"),
         InlineKeyboardButton(text="❌ Bekor qilish", callback_data="cancel_order")]
    ])
    await message.answer(f"Buyurtmani tasdiqlang:\n\nSiz: {data['s_name']}\nLink: {data['link']}\nMiqdor: {qty}\nJami: {total:,} so'm", reply_markup=kb)
    await state.set_state(UserState.order_confirm)

@dp.callback_query(F.data == "confirm_order", UserState.order_confirm)
async def order_final(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await users_col.find_one({"user_id": call.from_user.id})
    
    if user['balance'] < data['total']:
        return await call.answer("Mablag' yetarli emas!", show_alert=True)
    
    # Hisobdan yechish
    await users_col.update_one({"user_id": call.from_user.id}, {"$inc": {"balance": -data['total']}})
    order_id = str(uuid.uuid4())[:8]
    await orders_col.insert_one({
        "order_id": order_id, "user_id": call.from_user.id, "user_name": call.from_user.full_name,
        "service": data['s_name'], "link": data['link'], "qty": data['qty'], 
        "total": data['total'], "status": "Kutilmoqda", "date": datetime.now()
    })
    
    # Adminga yuborish
    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_ord_yes_{order_id}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_ord_no_{order_id}")]
    ])
    await bot.send_message(ADMIN_ID, f"🔔 Yangi Buyurtma!\nID: {call.from_user.id}\nNomi: {call.from_user.full_name}\nXizmat: {data['s_name']}\nLink: {data['link']}\nSumma: {data['total']:,}\nQoldiq: {user['balance'] - data['total']:,}", reply_markup=adm_kb)
    
    await call.message.edit_text("✅ Buyurtma adminga yuborildi!")
    await state.clear()

# --- ADMIN: ORDER APPROVAL ---
@dp.callback_query(F.data.startswith("adm_ord_"))
async def admin_order_res(call: types.CallbackQuery):
    _, _, res, o_id = call.data.split("_")
    order = await orders_col.find_one({"order_id": o_id})
    if res == "yes":
        await orders_col.update_one({"order_id": o_id}, {"$set": {"status": "Bajarildi"}})
        await bot.send_message(order['user_id'], f"✅ Buyurtmangiz (#{o_id}) bajarildi!")
        await call.message.edit_text(call.message.text + "\n\n✅ TASDIQLANDI")
    else:
        await users_col.update_one({"user_id": order['user_id']}, {"$inc": {"balance": order['total']}})
        await orders_col.update_one({"order_id": o_id}, {"$set": {"status": "Rad etildi"}})
        await bot.send_message(order['user_id'], f"❌ Buyurtmangiz (#{o_id}) rad etildi. Mablag' qaytarildi.")
        await call.message.edit_text(call.message.text + "\n\n❌ RAD ETILDI")

# --- USER: PAYMENTS ---
@dp.message(F.text == "💳 To'lov qilish")
async def pay_start(message: types.Message, state: FSMContext):
    card = await settings_col.find_one({"key": "card_info"})
    text = f"To'lov qilish uchun karta:\n\n`{card['number']}`\nEga: {card['owner']}\n\nTo'lov qilgach screenshotni yuboring:" if card else "Karta hali belgilanmagan."
    await message.answer(text, parse_mode="Markdown", reply_markup=back_kb())
    await state.set_state(UserState.fill_receipt)

@dp.message(UserState.fill_receipt, F.photo)
async def pay_receipt(message: types.Message, state: FSMContext):
    await state.update_data(photo=message.photo[-1].file_id)
    await message.answer("To'lov summasini kiriting:")
    await state.set_state(UserState.fill_amount)

@dp.message(UserState.fill_amount, F.text.isdigit())
async def pay_final(message: types.Message, state: FSMContext):
    data = await state.get_data()
    amount = int(message.text)
    adm_kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"adm_pay_yes_{message.from_user.id}_{amount}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"adm_pay_no_{message.from_user.id}")]
    ])
    await bot.send_photo(ADMIN_ID, data['photo'], caption=f"💰 To'lov!\nID: {message.from_user.id}\nNomi: {message.from_user.full_name}\nSumma: {amount:,} so'm", reply_markup=adm_kb)
    await message.answer("✅ To'lov adminga yuborildi.", reply_markup=main_kb(message.from_user.id))
    await state.clear()

# --- STATISTICS & TOP ---
@dp.message(F.text == "📊 Statistika")
async def user_stats(message: types.Message):
    u_id = message.from_user.id
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    month = today.replace(day=1)
    
    total_users = await users_col.count_documents({})
    today_users = await users_col.count_documents({"joined_at": {"$gte": today}})
    today_orders = await orders_col.count_documents({"date": {"$gte": today}})
    user_data = await users_col.find_one({"user_id": u_id})
    
    text = (f"📊 Bot statistikasi:\n"
            f"👥 Jami foydalanuvchilar: {total_users}\n"
            f"🆕 Bugun qo'shilganlar: {today_users}\n"
            f"📦 Bugun bajarilgan buyurtmalar: {today_orders}\n\n"
            f"👤 Sizning jami to'lovingiz: {user_data.get('total_pay', 0):,} so'm")
    await message.answer(text)

@dp.message(F.text == "🏆 TOP")
async def top_users(message: types.Message):
    top_ref = await users_col.find().sort("ref_count", -1).limit(5).to_list(None)
    top_pay = await users_col.find().sort("total_pay", -1).limit(5).to_list(None)
    
    text = "🏆 **Eng ko'p referal yig'ganlar:**\n"
    for i, u in enumerate(top_ref, 1):
        text += f"{i}. {u['name']} - {u['ref_count']} ta\n"
    
    text += "\n💰 **Eng ko'p to'lov qilganlar:**\n"
    for i, u in enumerate(top_pay, 1):
        text += f"{i}. {u['name']} - {u.get('total_pay', 0):,} so'm"
    
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN PANEL & SETTINGS ---
@dp.message(Command("admin"))
@dp.message(F.text == "🛠 Admin Panel")
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        await message.answer("Admin panelga xush kelibsiz!", reply_markup=admin_kb())

@dp.message(F.text == "🏠 Bosh menyu")
async def back_to_main(message: types.Message):
    await message.answer("Bosh menyudasiz.", reply_markup=main_kb(message.from_user.id))

# --- PROMOKOD TIZIMI ---
@dp.message(F.text == "🎁 Promokod")
async def promo_enter(message: types.Message, state: FSMContext):
    await message.answer("Promokodni kiriting:", reply_markup=back_kb())
    await state.set_state(UserState.enter_promo)

@dp.message(UserState.enter_promo, F.text != "⬅️ Ortga")
async def promo_check(message: types.Message, state: FSMContext):
    code = message.text
    promo = await promos_col.find_one({"code": code})
    if not promo or promo['used_count'] >= promo['limit']:
        return await message.answer("❌ Promokod xato yoki muddati tugagan.")
    
    user = await users_col.find_one({"user_id": message.from_user.id})
    if code in user.get("used_promos", []):
        return await message.answer("❌ Siz bu promokoddan foydalangansiz.")
    
    await users_col.update_one({"user_id": message.from_user.id}, 
                               {"$inc": {"balance": promo['amount']}, "$push": {"used_promos": code}})
    await promos_col.update_one({"code": code}, {"$inc": {"used_count": 1}})
    await message.answer(f"✅ Tabriklaymiz! Hisobingizga {promo['amount']:,} so'm qo'shildi.")
    await state.clear()

# --- BACK NAVIGATION ---
@dp.message(F.text == "⬅️ Ortga")
async def universal_back(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bekor qilindi.", reply_markup=main_kb(message.from_user.id))

# --- SERVER START ---
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

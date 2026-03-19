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
    # Bo'lim/Xizmat
    add_cat = State()
    del_cat = State()
    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()
    del_serv = State()
    # Karta
    set_card_num = State()
    set_card_name = State()
    # Balans
    edit_bal_id = State()
    edit_bal_amount = State()
    # Ref/Promo
    set_ref_amount = State()
    add_promo_code = State()
    add_promo_amount = State()
    add_promo_limit = State()
    # Boshqa
    broadcast = State()
    add_channel = State()

class UserState(StatesGroup):
    order_link = State()
    order_qty = State()
    order_confirm = State()
    fill_receipt = State()
    fill_amount = State()
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
        [KeyboardButton(text="📂 Bo'lim qo'shish"), KeyboardButton(text="❌ Bo'lim o'chirish")],
        [KeyboardButton(text="➕ Xizmat qo'shish"), KeyboardButton(text="🗑 Xizmat o'chirish")],
        [KeyboardButton(text="💳 Karta sozlash"), KeyboardButton(text="📉 Admin Statistika")],
        [KeyboardButton(text="🎁 Ref/Promo sozlash"), KeyboardButton(text="📢 Xabar yuborish")],
        [KeyboardButton(text="👤 Balansni boshqarish"), KeyboardButton(text="➕ Majburiy obuna")],
        [KeyboardButton(text="🏠 Bosh menyu")]
    ], resize_keyboard=True)

def back_btn():
    return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="⬅️ Ortga")]], resize_keyboard=True)

# --- MIDDLEWARE & UTILS ---
async def is_subscribed(user_id):
    data = await settings_col.find_one({"key": "channels"})
    if not data or not data.get("list"): return True
    for ch in data["list"]:
        try:
            chat = await bot.get_chat_member(ch, user_id)
            if chat.status in ["left", "kicked", "null"]: return False
        except: continue
    return True

# --- START & REGISTRATION ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message, command: CommandObject, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    
    if not await is_subscribed(uid):
        data = await settings_col.find_one({"key": "channels"})
        ch = data["list"][0]
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Obuna bo'lish", url=f"https://t.me/{ch.replace('@','')}")],
            [InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")]
        ])
        return await message.answer("Botdan foydalanish uchun kanalga a'zo bo'ling!", reply_markup=kb)

    user = await users_col.find_one({"user_id": uid})
    if not user:
        ref_by = None
        if command.args and command.args.isdigit():
            ref_id = int(command.args)
            if ref_id != uid:
                ref_by = ref_id
                r_set = await settings_col.find_one({"key": "ref_price"})
                bonus = r_set["val"] if r_set else 0
                await users_col.update_one({"user_id": ref_id}, {"$inc": {"balance": bonus, "ref_count": 1}})
                try: await bot.send_message(ref_id, f"🎁 Yangi referal! +{bonus} so'm.")
                except: pass

        await users_col.insert_one({
            "user_id": uid, "name": message.from_user.full_name, "balance": 0,
            "ref_by": ref_by, "ref_count": 0, "total_pay": 0, "used_promos": [], "joined_at": datetime.now()
        })
    
    await message.answer("Xush kelibsiz! Bot ishlamasa /start bosing.", reply_markup=main_kb(uid))

# --- ADMIN: CATEGORY & SERVICE ---
@dp.message(F.text == "📂 Bo'lim qo'shish", F.from_user.id == ADMIN_ID)
async def adm_add_cat(message: types.Message, state: FSMContext):
    await message.answer("Yangi bo'lim nomini yozing:", reply_markup=back_btn())
    await state.set_state(AdminState.add_cat)

@dp.message(AdminState.add_cat, F.text != "⬅️ Ortga")
async def adm_save_cat(message: types.Message, state: FSMContext):
    await categories_col.insert_one({"name": message.text})
    await message.answer(f"✅ '{message.text}' bo'limi qo'shildi.", reply_markup=admin_kb())
    await state.clear()

@dp.message(F.text == "➕ Xizmat qo'shish", F.from_user.id == ADMIN_ID)
async def adm_add_serv(message: types.Message, state: FSMContext):
    cats = await categories_col.find().to_list(None)
    if not cats: return await message.answer("Avval bo'lim qo'shing!")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"as_{c['_id']}")] for c in cats])
    await message.answer("Qaysi bo'limga xizmat qo'shamiz?", reply_markup=kb)

@dp.callback_query(F.data.startswith("as_"))
async def adm_serv_step2(call: types.CallbackQuery, state: FSMContext):
    await state.update_data(cat_id=call.data.split("_")[1])
    await call.message.answer("Xizmat nomini yozing:", reply_markup=back_btn())
    await state.set_state(AdminState.add_serv_name)

@dp.message(AdminState.add_serv_name, F.text != "⬅️ Ortga")
async def adm_serv_step3(message: types.Message, state: FSMContext):
    await state.update_data(s_name=message.text)
    await message.answer("Xizmat narxini yozing (1000 ta uchun):")
    await state.set_state(AdminState.add_serv_price)

@dp.message(AdminState.add_serv_price, F.text.isdigit())
async def adm_serv_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await services_col.insert_one({"cat_id": data['cat_id'], "name": data['s_name'], "price": int(message.text)})
    await message.answer("✅ Xizmat saqlandi.", reply_markup=admin_kb())
    await state.clear()

# --- ADMIN: CARD SETTINGS ---
@dp.message(F.text == "💳 Karta sozlash", F.from_user.id == ADMIN_ID)
async def adm_card(message: types.Message, state: FSMContext):
    await message.answer("Karta raqamini yozing:", reply_markup=back_btn())
    await state.set_state(AdminState.set_card_num)

@dp.message(AdminState.set_card_num, F.text != "⬅️ Ortga")
async def adm_card_2(message: types.Message, state: FSMContext):
    await state.update_data(c_num=message.text)
    await message.answer("Karta egasi ismini yozing:")
    await state.set_state(AdminState.set_card_name)

@dp.message(AdminState.set_card_name, F.text != "⬅️ Ortga")
async def adm_card_save(message: types.Message, state: FSMContext):
    data = await state.get_data()
    await settings_col.update_one({"key": "card"}, {"$set": {"number": data['c_num'], "owner": message.text}}, upsert=True)
    await message.answer("✅ Karta ma'lumotlari yangilandi.", reply_markup=admin_kb())
    await state.clear()

# --- USER: ORDERING ---
@dp.message(F.text == "🛒 Xizmatlar")
async def u_cats(message: types.Message):
    cats = await categories_col.find().to_list(None)
    if not cats: return await message.answer("Hozircha xizmatlar yo'q.")
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=c['name'], callback_data=f"uc_{c['_id']}")] for c in cats])
    await message.answer("📁 Bo'limni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("uc_"))
async def u_servs(call: types.CallbackQuery):
    cat_id = call.data.split("_")[1]
    servs = await services_col.find({"cat_id": cat_id}).to_list(None)
    if not servs: return await call.answer("Bu bo'limda xizmat yo'q.", show_alert=True)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"buy_{s['_id']}")] for s in servs])
    await call.message.edit_text("✨ Xizmatni tanlang:", reply_markup=kb)

@dp.callback_query(F.data.startswith("buy_"))
async def u_buy1(call: types.CallbackQuery, state: FSMContext):
    s = await services_col.find_one({"_id": ObjectId(call.data.split("_")[1])})
    await state.update_data(s_id=str(s['_id']), s_name=s['name'], s_price=s['price'])
    await call.message.answer(f"💠 {s['name']}\n🔗 Havolani yuboring:", reply_markup=back_btn())
    await state.set_state(UserState.order_link)

@dp.message(UserState.order_link, F.text != "⬅️ Ortga")
async def u_buy2(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Miqdorni kiriting (masalan: 1000):")
    await state.set_state(UserState.order_qty)

@dp.message(UserState.order_qty, F.text.isdigit())
async def u_buy3(message: types.Message, state: FSMContext):
    qty = int(message.text)
    data = await state.get_data()
    total = (data['s_price'] / 1000) * qty
    await state.update_data(qty=qty, total=total)
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data="u_confirm")],
        [InlineKeyboardButton(text="⬅️ Bekor qilish", callback_data="u_cancel")]
    ])
    await message.answer(f"📝 Buyurtmani tasdiqlang:\n\nXizmat: {data['s_name']}\nLink: {data['link']}\nMiqdor: {qty}\nJami: {total:,} so'm", reply_markup=kb)
    await state.set_state(UserState.order_confirm)

@dp.callback_query(F.data == "u_confirm", UserState.order_confirm)
async def u_buy_done(call: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user = await users_col.find_one({"user_id": call.from_user.id})
    if user['balance'] < data['total']:
        return await call.answer("❌ Balans yetarli emas!", show_alert=True)
    
    # Pulni yechish
    await users_col.update_one({"user_id": call.from_user.id}, {"$inc": {"balance": -data['total']}})
    oid = str(uuid.uuid4())[:8].upper()
    
    order = {
        "oid": oid, "uid": user['user_id'], "name": user['name'],
        "service": data['s_name'], "link": data['link'], "total": data['total'],
        "status": "Kutilmoqda", "date": datetime.now()
    }
    await orders_col.insert_one(order)
    
    # Adminga xabar
    akb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Tasdiqlash", callback_data=f"ord_ok_{oid}"),
         InlineKeyboardButton(text="❌ Rad etish", callback_data=f"ord_no_{oid}")]
    ])
    await bot.send_message(ADMIN_ID, f"📦 Yangi Buyurtma: #{oid}\nUser: {user['name']} ({user['user_id']})\nXizmat: {data['s_name']}\nLink: {data['link']}\nSumma: {data['total']:,}\nQoldiq: {user['balance'] - data['total']:,}", reply_markup=akb)
    
    await call.message.edit_text(f"✅ Buyurtma qabul qilindi! ID: #{oid}")
    await state.clear()

# --- ADMIN: ORDER APPROVAL ---
@dp.callback_query(F.data.startswith("ord_"))
async def adm_ord_res(call: types.CallbackQuery):
    action, oid = call.data.split("_")[1], call.data.split("_")[2]
    order = await orders_col.find_one({"oid": oid})
    if action == "ok":
        await orders_col.update_one({"oid": oid}, {"$set": {"status": "Bajarildi"}})
        await bot.send_message(order['uid'], f"✅ Buyurtmangiz (#{oid}) bajarildi!")
    else:
        await users_col.update_one({"user_id": order['uid']}, {"$inc": {"balance": order['total']}})
        await orders_col.update_one({"oid": oid}, {"$set": {"status": "Rad etildi"}})
        await bot.send_message(order['uid'], f"❌ Buyurtmangiz (#{oid}) rad etildi. Mablag' qaytarildi.")
    await call.message.delete()

# --- USER: HELP ---
@dp.message(F.text == "🆘 Yordam")
async def u_help(message: types.Message, state: FSMContext):
    await message.answer("Muammoingizni yozing, admin javob beradi:", reply_markup=back_btn())
    await state.set_state(UserState.help_msg)

@dp.message(UserState.help_msg, F.text != "⬅️ Ortga")
async def u_help_send(message: types.Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"🆘 Yordam so'rovi!\nID: {message.from_user.id}\nNomi: {message.from_user.full_name}\n\nMatn: {message.text}")
    await message.answer("✅ Xabaringiz yuborildi.", reply_markup=main_kb(message.from_user.id))
    await state.clear()

# --- BROADCAST & OTHER ADMIN ---
@dp.message(F.text == "📢 Xabar yuborish", F.from_user.id == ADMIN_ID)
async def adm_bc(message: types.Message, state: FSMContext):
    await message.answer("Xabar matnini yuboring:", reply_markup=back_btn())
    await state.set_state(AdminState.broadcast)

@dp.message(AdminState.broadcast, F.text != "⬅️ Ortga")
async def adm_bc_send(message: types.Message, state: FSMContext):
    users = await users_col.find().to_list(None)
    count = 0
    for u in users:
        try:
            await bot.send_message(u['user_id'], message.text)
            count += 1
            await asyncio.sleep(0.05)
        except: continue
    await message.answer(f"✅ {count} ta foydalanuvchiga yuborildi.", reply_markup=admin_kb())
    await state.clear()

# --- ORTGA QAYTISH ---
@dp.message(F.text == "⬅️ Ortga")
async def back_handler(message: types.Message, state: FSMContext):
    await state.clear()
    uid = message.from_user.id
    if uid == ADMIN_ID:
        await message.answer("Bekor qilindi.", reply_markup=admin_kb())
    else:
        await message.answer("Asosiy menyu.", reply_markup=main_kb(uid))

@dp.message(F.text == "🏠 Bosh menyu")
async def home_handler(message: types.Message, state: FSMContext):
    await state.clear()
    await message.answer("Bosh menyu", reply_markup=main_kb(message.from_user.id))

# --- SERVER & POLLING ---
async def handle(request): return web.Response(text="SMM Bot is Active!")

async def main():
    app = web.Application()
    app.router.add_get("/", handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 8080))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()
    
    logging.info("🚀 Bot start polling...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

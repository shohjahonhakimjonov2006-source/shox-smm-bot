import logging
import asyncio
import aiohttp
import motor.motor_asyncio
import os
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# --- SOZLAMALAR ---
API_TOKEN = '8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo'
ADMIN_ID = 7861165622
SMM_API_KEY = '00c9d8e11e3935fe8861533a792fd2fe'
SMM_API_URL = 'https://smmapi.safobuilder.uz/shox_smmbot/api/v2'
KARTA_RAQAM = "9860030125568441"

# --- MONGODB ---
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?retryWrites=true&w=majority&appName=ZOirbek2003"
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client.smm_pro_database
users_col = db.users
services_col = db.services
orders_col = db.orders

logging.basicConfig(level=logging.INFO)
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

class OrderState(StatesGroup):
    entering_link = State()
    entering_quantity = State()

# --- MENYULAR ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish")],
    [KeyboardButton(text="👤 Mening hisobim"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

social_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="Telegram"), KeyboardButton(text="Tik tok")],
    [KeyboardButton(text="Stars va Premium"), KeyboardButton(text="Facebook")],
    [KeyboardButton(text="Instagram"), KeyboardButton(text="YouTube")],
    [KeyboardButton(text="WhatsApp"), KeyboardButton(text="Twitter")],
    [KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

# --- START ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_deposited': 0}},
        upsert=True
    )
    await message.answer("Xush kelibsiz! Kerakli bo'limni tanlang:", reply_markup=main_menu)

# --- MENING HISOBIM ---
@dp.message(F.text == "👤 Mening hisobim")
async def my_account(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    order_count = await orders_col.count_documents({'user_id': message.from_user.id})
    
    balance = user.get('balance', 0) if user else 0
    deposited = user.get('total_deposited', 0) if user else 0
    
    text = (
        f"👤 Sizning ID raqamingiz: `{message.from_user.id}`\n\n"
        f"💵 Balansingiz: {balance:,.2f} so'm\n"
        f"📊 Buyurtmalaringiz: {order_count} ta\n"
        f"💰 Kiritgan pullaringiz: {deposited:,.2f} so'm"
    )
    await message.answer(text, parse_mode="Markdown")

# --- BUYURTMA BERISH ---
@dp.message(F.text == "🚀 Buyurtma berish")
async def show_socials(message: types.Message):
    await message.answer("📁 Quyidagi ijtimoiy tarmoqlardan birini tanlang:", reply_markup=social_menu)

@dp.message(F.text.in_(["Telegram", "Tik tok", "Instagram", "YouTube", "Facebook", "Twitter", "WhatsApp"]))
async def show_services(message: types.Message):
    # Bu yerda API xizmatlari nomiga qarab filter qilishingiz mumkin. 
    # Hozircha bazadagi xizmatlarni chiqaramiz.
    services = await services_col.find().limit(20).to_list(length=20)
    if not services:
        return await message.answer("Xizmatlar topilmadi. Admin /admin orqali yangilashi kerak.")
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s['name'][:30]} - {s['price']} so'm", callback_data=f"srv_{s['id']}")]
        for s in services
    ])
    await message.answer(f"📁 {message.text} bo'limi. Xizmatni tanlang:", reply_markup=kb)

# --- BUYURTMALARIM ---
@dp.message(F.text == "📊 Buyurtmalarim")
async def my_orders(message: types.Message):
    orders = await orders_col.find({'user_id': message.from_user.id}).sort('_id', -1).limit(10).to_list(length=10)
    if not orders:
        return await message.answer("Sizda hali buyurtmalar mavjud emas.")
    
    text = "📊 **Buyurtmalar:**\n\n"
    kb_list = []
    for o in orders:
        status = "✅ Bajarilgan" if o.get('status') == "Completed" else "⏳ Jarayonda"
        text += f"🆔 ID: {o['order_id']} | API\n📁 Xizmat: {o['service_name']}\n♻️ Holat: {status}\n⏰ Sana: {o['date']}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        kb_list.append([InlineKeyboardButton(text=f"ID: {o['order_id']}", callback_data=f"view_{o['order_id']}")])
    
    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb_list), parse_mode="Markdown")

@dp.callback_query(F.data.startswith("view_"))
async def detail_order(callback: types.CallbackQuery):
    o_id = callback.data.split("_")[1]
    order = await orders_col.find_one({'order_id': int(o_id)})
    if not order: return await callback.answer("Ma'lumot topilmadi.")
    
    status = "✅ Bajarilgan" if order.get('status') == "Completed" else "⏳ Jarayonda"
    res = (
        f"🆔 Buyurtma IDsi: {order['order_id']}\n\n"
        f"📁 {order['service_name']}\n\n"
        f"♻️ Holat: {status}\n"
        f"🔗 Havola: {order['link']}\n"
        f"🔢 Miqdor: {order['quantity']} ta\n"
        f"💰 Narxi: {order['cost']:,.2f} so'm\n"
        f"⏰ Sana: {order['date']}"
    )
    await callback.message.answer(res, disable_web_page_preview=True)
    await callback.answer()

# --- BUYURTMA BERISH LOGIKASI ---
@dp.callback_query(F.data.startswith("srv_"))
async def srv_click(callback: types.CallbackQuery, state: FSMContext):
    s_id = callback.data.split("_")[1]
    service = await services_col.find_one({'id': s_id})
    
    if not service:
        return await callback.message.answer("Xatolik: Xizmat topilmadi. Admin xizmatlarni yangilashi shart.")
        
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await callback.message.answer(f"📌 {service['name']}\n\n🔗 Havolani yuboring:")
    await state.set_state(OrderState.entering_link)

@dp.message(OrderState.entering_link)
async def process_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Miqdorni kiriting:")
    await state.set_state(OrderState.entering_quantity)

@dp.message(OrderState.entering_quantity)
async def process_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam kiriting!")
    qty = int(message.text)
    data = await state.get_data()
    cost = (data['s_price'] / 1000) * qty
    
    user = await users_col.find_one({'user_id': message.from_user.id})
    if user['balance'] < cost:
        return await message.answer(f"⚠️ Balans yetarli emas! Narxi: {cost} so'm")

    async with aiohttp.ClientSession() as session:
        params = {'key': SMM_API_KEY, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}
        async with session.post(SMM_API_URL, data=params) as resp:
            res = await resp.json()
            if 'order' in res:
                await users_col.update_one({'user_id': message.from_user.id}, {'$inc': {'balance': -cost}})
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await orders_col.insert_one({
                    'order_id': res['order'], 'user_id': message.from_user.id,
                    'service_name': data['s_name'], 'cost': cost, 'link': data['link'],
                    'quantity': qty, 'date': now, 'status': 'Pending'
                })
                await bot.send_message(ADMIN_ID, f"🔔 Yangi buyurtma!\nID: {res['order']}\nUser: {message.from_user.id}\nSumma: {cost}")
                await message.answer(f"✅ Buyurtma qabul qilindi!\nID: {res['order']}", reply_markup=main_menu)
            else:
                await message.answer("❌ API xatosi.")
    await state.clear()

# --- ADMIN: XIZMATLARNI YANGILASH ---
@dp.message(Command("admin"))
async def admin_cmd(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="🔄 Xizmatlarni yangilash")], [KeyboardButton(text="🏠 Asosiy menyu")]], resize_keyboard=True)
        await message.answer("Admin paneli:", reply_markup=kb)

@dp.message(F.text == "🔄 Xizmatlarni yangilash")
async def update_srv(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    async with aiohttp.ClientSession() as session:
        async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as r:
            data = await r.json()
            if isinstance(data, list):
                await services_col.delete_many({})
                for s in data:
                    await services_col.insert_one({'id': str(s['service']), 'name': s['name'], 'price': float(s['rate']), 'min': int(s['min'])})
                await message.answer("✅ Xizmatlar yangilandi!")

@dp.message(F.text == "🏠 Asosiy menyu")
async def back_main(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

# --- RENDER TIMEOUT YECHIMI ---
async def main():
    port = int(os.environ.get("PORT", 10000))
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

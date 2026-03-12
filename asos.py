import logging
import asyncio
import aiohttp
import motor.motor_asyncio
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

# --- HOLATLAR ---
class OrderState(StatesGroup):
    selecting_category = State()
    selecting_service = State()
    entering_link = State()
    entering_quantity = State()

# --- ASOSIY MENYU ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish")],
    [KeyboardButton(text="👤 Mening hisobim"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

# --- BUYURTMA BERISH (KATEGORIYALAR) ---
def get_categories_kb():
    categories = [
        "Telegram", "Tik tok", "Stars va Premium", "Facebook", 
        "Twitch", "Threads", "Instagram", "YouTube", 
        "WhatsApp", "Twitter", "VK Obunachilar", "Tekin nakrutka"
    ]
    buttons = []
    for i in range(0, len(categories), 2):
        row = [KeyboardButton(text=categories[i])]
        if i+1 < len(categories):
            row.append(KeyboardButton(text=categories[i+1]))
        buttons.append(row)
    buttons.append([KeyboardButton(text="🏠 Asosiy menyu")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

# --- START ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_spent': 0}},
        upsert=True
    )
    await message.answer("Xush kelibsiz!", reply_markup=main_menu)

# --- MENING HISOBIM ---
@dp.message(F.text == "👤 Mening hisobim")
async def my_account(message: types.Message):
    user = await users_col.find_one({'user_id': message.from_user.id})
    order_count = await orders_col.count_documents({'user_id': message.from_user.id})
    
    text = (
        f"👤 Sizning ID raqamingiz: `{message.from_user.id}`\n\n"
        f"💵 Balansingiz: {user.get('balance', 0):,.2f} so'm\n"
        f"📊 Buyurtmalaringiz: {order_count} ta\n"
        f"💰 Kiritgan pullaringiz: {user.get('total_spent', 0):,.2f} so'm"
    )
    await message.answer(text, parse_mode="Markdown")

# --- BUYURTMA BERISH BOSHQARUV ---
@dp.message(F.text == "🚀 Buyurtma berish")
async def start_order(message: types.Message):
    await message.answer("📁 Quyidagi ijtimoiy tarmoqlardan birini tanlang:", reply_markup=get_categories_kb())

@dp.message(F.text.in_(["Telegram", "Instagram", "YouTube", "Tik tok", "Facebook", "Twitter"]))
async def select_category(message: types.Message, state: FSMContext):
    cat = message.text
    # API'dan ushbu kategoriya bo'yicha xizmatlarni qidirish (Sizning API'ingizda kategoriya bo'yicha filter bo'lishi kerak)
    # Hozircha bazadagi barcha xizmatlarni chiqarib turamiz:
    services = await services_col.find().limit(15).to_list(length=15)
    
    if not services:
        return await message.answer("Ushbu bo'limda xizmatlar topilmadi.")

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{s['name'][:30]} - {s['price']} so'm", callback_data=f"srv_{s['id']}")] 
        for s in services
    ])
    await message.answer(f"🔍 {cat} uchun xizmatni tanlang:", reply_markup=kb)

# --- BUYURTMALARIM (RO'YXAT) ---
@dp.message(F.text == "📊 Buyurtmalarim")
async def order_list(message: types.Message):
    orders = await orders_col.find({'user_id': message.from_user.id}).sort('_id', -1).limit(10).to_list(length=10)
    if not orders:
        return await message.answer("Sizda hali buyurtmalar yo'q.")

    text = "📊 **Buyurtmalar:**\n\n"
    kb = []
    for o in orders:
        status = "✅ Bajarilgan" if o.get('status') == "Completed" else "⏳ Jarayonda"
        text += f"🆔 ID: {o['order_id']} | API\n📁 Xizmat: {o['service_name']}\n♻️ Holat: {status}\n⏰ Sana: {o['date']}\n⎯⎯⎯⎯⎯⎯⎯⎯⎯⎯\n"
        kb.append([InlineKeyboardButton(text=f"🛒 Buyurtma #{o['order_id']}", callback_data=f"view_{o['order_id']}")])

    await message.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb), parse_mode="Markdown")

# --- BUYURTMA DETALLARI ---
@dp.callback_query(F.data.startswith("view_"))
async def view_order_detail(callback: types.CallbackQuery):
    order_id = int(callback.data.split("_")[1])
    order = await orders_col.find_one({'order_id': order_id})
    
    if not order:
        return await callback.answer("Ma'lumot topilmadi.")

    status = "✅ Bajarilgan" if order.get('status') == "Completed" else "⏳ Jarayonda"
    detail = (
        f"🆔 Buyurtma IDsi: {order['order_id']}\n\n"
        f"📁 {order['service_name']}\n\n"
        f"♻️ Holat: {status}\n"
        f"🔗 Havola: {order['link']}\n"
        f"🔢 Miqdor: {order['quantity']} ta\n"
        f"💰 Narxi: {order['cost']:,.2f} so'm\n\n"
        f"⏰ Sana: {order['date']}"
    )
    await callback.message.answer(detail, disable_web_page_preview=True)
    await callback.answer()

# --- BUYURTMA JARAYONI (Qisqacha) ---
@dp.callback_query(F.data.startswith("srv_"))
async def order_process(callback: types.CallbackQuery, state: FSMContext):
    s_id = callback.data.split("_")[1]
    service = await services_col.find_one({'id': s_id})
    await state.update_data(s_id=s_id, s_name=service['name'], s_price=service['price'])
    await callback.message.answer(f"📌 {service['name']}\n\n🔗 Havolani yuboring:")
    await state.set_state(OrderState.entering_link)

@dp.message(OrderState.entering_link)
async def get_link(message: types.Message, state: FSMContext):
    await state.update_data(link=message.text)
    await message.answer("🔢 Miqdorni kiriting:")
    await state.set_state(OrderState.entering_quantity)

@dp.message(OrderState.entering_quantity)
async def get_qty(message: types.Message, state: FSMContext):
    if not message.text.isdigit(): return await message.answer("Faqat raqam!")
    qty = int(message.text)
    data = await state.get_data()
    total_cost = (data['s_price'] / 1000) * qty
    
    user = await users_col.find_one({'user_id': message.from_user.id})
    if user['balance'] < total_cost:
        return await message.answer("Mablag' yetarli emas!")

    # API-ga yuborish
    async with aiohttp.ClientSession() as session:
        params = {'key': SMM_API_KEY, 'action': 'add', 'service': data['s_id'], 'link': data['link'], 'quantity': qty}
        async with session.post(SMM_API_URL, data=params) as resp:
            res = await resp.json()
            if 'order' in res:
                now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                await orders_col.insert_one({
                    'order_id': res['order'], 
                    'user_id': message.from_user.id,
                    'service_name': data['s_name'],
                    'cost': total_cost,
                    'link': data['link'],
                    'quantity': qty,
                    'status': 'In Progress',
                    'date': now
                })
                await users_col.update_one({'user_id': message.from_user.id}, {'$inc': {'balance': -total_cost}})
                
                # ADMINGA HABAR
                await bot.send_message(ADMIN_ID, f"🔔 Yangi buyurtma!\nUser: {message.from_user.id}\nID: {res['order']}\nSumma: {total_cost} so'm")
                await message.answer(f"✅ Buyurtma qabul qilindi!\nID: {res['order']}", reply_markup=main_menu)
            else:
                await message.answer("API xatosi!")
    await state.clear()

@dp.message(F.text == "🏠 Asosiy menyu")
async def go_home(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

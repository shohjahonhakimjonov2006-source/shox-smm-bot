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
ADMIN_ID = 7861165622 # O'zingizning ID raqamingiz
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

# --- ASOSIY MENYU ---
main_menu = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🚀 Buyurtma berish")],
    [KeyboardButton(text="👤 Mening hisobim"), KeyboardButton(text="📊 Buyurtmalarim")],
    [KeyboardButton(text="💰 Balans to'ldirish"), KeyboardButton(text="👨‍💻 Bog'lanish")]
], resize_keyboard=True)

# --- ADMIN BUYRUG'I ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        admin_kb = ReplyKeyboardMarkup(keyboard=[
            [KeyboardButton(text="🔄 Xizmatlarni yangilash")],
            [KeyboardButton(text="🏠 Asosiy menyu")]
        ], resize_keyboard=True)
        await message.answer("🛠 Admin panelga xush kelibsiz!", reply_markup=admin_kb)
    else:
        await message.answer(f"❌ Siz admin emassiz. Sizning ID: `{message.from_user.id}`", parse_mode="Markdown")

# --- XIZMATLARNI YANGILASH ---
@dp.message(F.text == "🔄 Xizmatlarni yangilash")
async def update_srv(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    status = await message.answer("🔄 API-dan xizmatlar yuklanmoqda...")
    async with aiohttp.ClientSession() as session:
        try:
            async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as r:
                data = await r.json()
                if isinstance(data, list):
                    await services_col.delete_many({}) # Eski ma'lumotlarni o'chirish
                    for s in data:
                        await services_col.insert_one({
                            'id': str(s['service']),
                            'name': s['name'],
                            'price': float(s['rate']),
                            'category': s.get('category', 'Umumiy')
                        })
                    await status.edit_text(f"✅ Baza yangilandi! {len(data)} ta xizmat qo'shildi.")
                else:
                    await status.edit_text("❌ API noto'g'ri ma'lumot qaytardi.")
        except Exception as e:
            await status.edit_text(f"❌ Xatolik: {str(e)}")

# --- START ---
@dp.message(Command("start"))
async def start_cmd(message: types.Message):
    await users_col.update_one(
        {'user_id': message.from_user.id},
        {'$setOnInsert': {'balance': 0, 'total_spent': 0}},
        upsert=True
    )
    await message.answer("Assalomu alaykum! SMM botga xush kelibsiz.", reply_markup=main_menu)

@dp.message(F.text == "🏠 Asosiy menyu")
async def go_home(message: types.Message):
    await message.answer("Asosiy menyu", reply_markup=main_menu)

# --- RENDER PORT BINDING ---
async def main():
    # Render portini ulab qo'yamiz (Timed out xatosini oldini oladi)
    port = int(os.environ.get("PORT", 10000))
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot stopped")

import asyncio
import logging
import sys
import os
import certifi
from threading import Thread
from flask import Flask
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.deep_linking import create_start_link
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from motor.motor_asyncio import AsyncIOMotorClient

# --- SOZLAMALAR ---
API_TOKEN = '8678413684:AAHnoyOgk5AhKwF4kYbcu_11d5M5rpLgpw0'
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/smm_ultra?retryWrites=true&w=majority"
ADMIN_ID = 7861165622

# MongoDB ulanishi
client = AsyncIOMotorClient(MONGO_URL, tlsCAFile=certifi.where())
db = client['smm_ultra']
users_col = db['users']
settings_col = db['settings']
stats_backup_col = db['stats_backup']

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- FSM STATES (Admin uchun) ---
class AdminState(StatesGroup):
    waiting_broadcast = State()
    waiting_channel_id = State()
    waiting_channel_url = State()
    waiting_gift_text = State()
    waiting_points = State()
    waiting_find_id = State()

# --- YORDAMCHI FUNKSIYALAR ---
async def get_config():
    config = await settings_col.find_one({"id": "main"})
    if not config:
        config = {
            "id": "main", "channels": [], "gift_text": "Sovg'alar",
            "terms_text": "Shartlar", "point_per_ref": 10,
            "cert_limit": 50, "private_link": "https://t.me/+example"
        }
        await settings_col.insert_one(config)
    return config

async def check_all_subs(user_id, channels):
    for ch in channels:
        try:
            member = await bot.get_chat_member(ch['id'], user_id)
            if member.status in ['left', 'kicked']: return False
        except: return False
    return True

# --- MENYULAR ---
def main_menu():
    kb = [
        [KeyboardButton(text="🎁 Konkursga qatnashish")],
        [KeyboardButton(text="📊 Reyting"), KeyboardButton(text="💰 Ballarim")],
        [KeyboardButton(text="📜 Shartlar"), KeyboardButton(text="🏆 Sovg'alar")],
        [KeyboardButton(text="🎓 Sertifikat olish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="adm_send")],
        [InlineKeyboardButton(text="➕ Kanal qo'shish", callback_data="adm_add_ch"), InlineKeyboardButton(text="🗑 Kanallarni tozalash", callback_data="adm_clear_ch")],
        [InlineKeyboardButton(text="💰 Ballni o'zgartirish", callback_data="adm_set_p")],
        [InlineKeyboardButton(text="🔍 ID orqali topish", callback_data="adm_find")],
        [InlineKeyboardButton(text="🔄 Statistikani tozalash", callback_data="adm_reset_stats")]
    ])

# --- USER HANDLERLAR ---
@dp.message(CommandStart())
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    config = await get_config()
    
    user = await users_col.find_one({"user_id": user_id})
    if not user:
        count = await users_col.count_documents({})
        user_data = {
            "user_id": user_id, "custom_id": count + 1,
            "full_name": message.from_user.full_name, "points": 0,
            "referred_by": None, "full_claimed": False
        }
        if len(args) > 1 and args[1].isdigit():
            ref_id = int(args[1])
            if ref_id != user_id:
                user_data["referred_by"] = ref_id
                bonus = config['point_per_ref'] // 3
                await users_col.update_one({"user_id": ref_id}, {"$inc": {"points": bonus}})
                await bot.send_message(ref_id, f"🎁 Yangi do'st! Sizga {bonus} ball berildi.")
        await users_col.insert_one(user_data)
    
    await message.answer("Xush kelibsiz!", reply_markup=main_menu())

@dp.message(F.text == "🎁 Konkursga qatnashish")
async def join_contest(message: types.Message):
    config = await get_config()
    if not config['channels']:
        await message.answer("Konkurs vaqtinchalik to'xtatilgan.")
        return
        
    is_sub = await check_all_subs(message.from_user.id, config['channels'])
    if is_sub:
        link = await create_start_link(bot, str(message.from_user.id), encode=False)
        user = await users_col.find_one({"user_id": message.from_user.id})
        if user.get("referred_by") and not user.get("full_claimed"):
            total_bonus = config['point_per_ref'] - (config['point_per_ref'] // 3)
            await users_col.update_one({"user_id": user['referred_by']}, {"$inc": {"points": total_bonus}})
            await users_col.update_one({"user_id": message.from_user.id}, {"$set": {"full_claimed": True}})
            await bot.send_message(user['referred_by'], "🔥 Do'stingiz kanallarga obuna bo'ldi! Qolgan ballar berildi.")
        await message.answer(f"Siz ro'yxatdan o'tdingiz!\n\nReferal havolangiz:\n{link}")
    else:
        kb = [[InlineKeyboardButton(text="Obuna bo'lish", url=c['url'])] for c in config['channels']]
        kb.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        await message.answer("Konkursda qatnashish uchun kanallarga obuna bo'ling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.message(F.text == "📊 Reyting")
async def show_rating(message: types.Message):
    cursor = users_col.find().sort("points", -1).limit(100)
    text = "🏆 **TOP 100**\n\n"
    i = 1
    async for u in cursor:
        text += f"{i}. {u['full_name']} — {u['points']} ball\n"
        i += 1
    await message.answer(text, parse_mode="Markdown")

# --- ADMIN PANEL ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_main(message: types.Message):
    await message.answer("Boshqaruv paneli:", reply_markup=admin_kb())

@dp.callback_query(F.data == "adm_send", F.from_user.id == ADMIN_ID)
async def adm_send_start(call: types.CallbackQuery, state: FSMContext):
    await call.message.answer("Xabarni kiriting:")
    await state.set_state(AdminState.waiting_broadcast)

@dp.message(AdminState.waiting_broadcast)
async def process_broadcast(message: types.Message, state: FSMContext):
    users = users_col.find()
    async for u in users:
        try: await bot.send_message(u['user_id'], message.text)
        except: continue
    await message.answer("Yuborildi!")
    await state.clear()

# --- WEB SERVER (Render uchun) ---
app = Flask(__name__)
@app.route('/')
def home(): return "Bot is running!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))

async def main():
    logging.basicConfig(level=logging.INFO)
    # Flaskni alohida oqimda ishga tushirish
    Thread(target=run_flask).start()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

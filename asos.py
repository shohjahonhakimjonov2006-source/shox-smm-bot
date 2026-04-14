import asyncio
import logging
import sqlite3
import os
import aiohttp
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.utils.deep_linking import create_start_link
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- SOZLAMALAR ---
API_TOKEN = '8672594017:AAElGsXRSz8hVeKRhVJw9URE0eCBb1_XYaI'
ADMIN_ID = 7861165622 
APP_URL = "https://shox-smm-bot.onrender.com"
# SHU YERGA GOOGLE SCRIPT URL MANZILINI QO'YING
GOOGLE_SHEET_URL = "https://script.google.com/macros/s/AKfycbyVq4gkT8vu1kRdHNKesmES2OwCiJo-Pw-rvxrLlaCuef-rI6LOSA45qIwV2tPGwjJP/exec"

logging.basicConfig(level=logging.INFO)

# --- MA'LUMOTLAR OMBORI ---
conn = sqlite3.connect('anon_pro.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, joined_at DATE, ref_by TEXT, phone TEXT)')
cursor.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sent_at DATE)')
cursor.execute('CREATE TABLE IF NOT EXISTS admins (admin_id INTEGER PRIMARY KEY)')
cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (ADMIN_ID,))
conn.commit()

class ChatStates(StatesGroup):
    waiting_for_phone = State() # YANGI: Telefon kutish
    waiting_for_anon_message = State()
    waiting_for_reply = State()
    waiting_for_broadcast_content = State()
    waiting_for_link_url = State()
    waiting_for_new_admin = State()
    waiting_for_remove_admin = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- YORDAMCHI FUNKSIYALAR ---
def is_admin(user_id):
    cursor.execute("SELECT 1 FROM admins WHERE admin_id = ?", (user_id,))
    return cursor.fetchone() is not None

async def save_to_google_sheets(name, user_id, username, phone, ref_by, status="Active"):
    """Google Sheetsga ma'lumot yuborish"""
    async with aiohttp.ClientSession() as session:
        params = {
            "name": name,
            "id": user_id,
            "username": f"@{username}" if username else "Yo'q",
            "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "phone": phone,
            "status": status,
            "ref_by": ref_by
        }
        try:
            await session.get(GOOGLE_SHEET_URL, params=params)
        except Exception as e:
            logging.error(f"Google Sheets xatosi: {e}")

# --- RENDER UYG'OTISH TIZIMI ---
async def self_ping():
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(APP_URL) as response:
                    logging.info(f"Self-ping yuborildi: {response.status}")
        except Exception as e:
            logging.error(f"Self-ping xatosi: {e}")
        await asyncio.sleep(780)

async def handle(request):
    return web.Response(text="Bot faol ishlamoqda!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    port = int(os.environ.get("PORT", 10000))
    site = web.TCPSite(runner, '0.0.0.0', port)
    await site.start()

async def send_personal_link(message: types.Message, user_id: int):
    link = await create_start_link(bot, str(user_id), encode=False)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Havolani ulashish", switch_inline_query=f"\nMen bilan anonim gaplashing:\n{link}")
    ]])
    await message.answer(f"🔗 Shaxsiy havolangiz:\n\n{link}", reply_markup=kb)

# --- HANDLERLAR ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    
    # Referalni aniqlash
    args = message.text.split()
    ref_by_name = "To'g'ridan-to'g'ri"
    if len(args) > 1 and args[1].isdigit():
        ref_id = int(args[1])
        try:
            ref_user = await bot.get_chat(ref_id)
            ref_by_name = ref_user.full_name
        except:
            ref_by_name = "Noma'lum foydalanuvchi"

    # Bazada bormi tekshirish
    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        # Yangi foydalanuvchi bo'lsa telefon so'raymiz
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
        await state.update_data(ref_by_name=ref_by_name)
        await message.answer(f"Salom {message.from_user.full_name}! Botdan foydalanish uchun telefon raqamingizni yuboring:", reply_markup=kb)
        await state.set_state(ChatStates.waiting_for_phone)
    else:
        # Eski foydalanuvchi bo'lsa davom etadi
        if len(args) > 1 and args[1] != str(user_id):
            await state.update_data(target_id=args[1])
            await state.set_state(ChatStates.waiting_for_anon_message)
            await message.answer("📝 Anonim xabaringizni yozing:")
        else:
            await message.answer("Xush kelibsiz!")
            await send_personal_link(message, user_id)

@dp.message(ChatStates.waiting_for_phone, F.contact)
async def get_phone(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    phone = message.contact.phone_number
    data = await state.get_data()
    ref_by = data.get('ref_by_name', "To'g'ridan-to'g'ri")
    
    # Bazaga saqlash
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?)", 
                   (user_id, message.from_user.username, datetime.now().date(), ref_by, phone))
    conn.commit()
    
    # Google Sheetsga yuborish
    await save_to_google_sheets(message.from_user.full_name, user_id, message.from_user.username, phone, ref_by)
    
    await message.answer("✅ Ro'yxatdan o'tdingiz!", reply_markup=types.ReplyKeyboardRemove())
    await send_personal_link(message, user_id)
    await state.clear()

@dp.message(ChatStates.waiting_for_anon_message)
async def handle_anon(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('target_id')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply_{message.from_user.id}")]])
    
    try:
        header = "📩 Yangi anonim xabar:\n\n"
        if is_admin(int(target_id)): 
            header = f"👤 Admin uchun (Ism: {message.from_user.full_name}, ID: {message.from_user.id})\n{header}"
        
        await bot.send_message(target_id, header + (message.text or ""), entities=message.entities, reply_markup=kb)
        cursor.execute("INSERT INTO messages (sent_at) VALUES (?)", (datetime.now().date(),))
        conn.commit()
        await message.answer("✅ Xabar yuborildi!")
        await send_personal_link(message, message.from_user.id)
        await state.clear()
    except Exception:
        # Agar bloklagan bo'lsa statusni Sheetsda yangilashga harakat qilamiz
        await save_to_google_sheets(message.from_user.full_name, target_id, "", "", "", status="Blocked")
        await message.answer("❌ Xatolik! Bot bloklangan bo'lishi mumkin.")

# --- QOLGAN ADMIN VA REKLAMA QISMLARI O'ZGARIShSIZ QOLADI ---
# ... (Siz yuborgan koddagi barcha boshqa funksiyalar shu yerda davom etadi) ...

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    today = datetime.now().date()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sent_at = ?", (today,))
    msg_today = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    
    text = (f"📊 **Bot Statistikasi**\n\n"
            f"📩 Bugungi xabarlar: {msg_today} ta\n"
            f"👤 Jami foydalanuvchilar: {total_users} ta")
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# [Barcha boshqa handlerlar (admin qo'shish, reklama va h.k.) saqlanadi]
# ... (Joyni tejash uchun ularni qayta yozmadim, lekin ular kodingizda bo'lishi kerak) ...

async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(self_ping())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

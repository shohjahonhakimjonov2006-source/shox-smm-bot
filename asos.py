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
GOOGLE_SHEET_URL = "SIZNING_GOOGLE_SCRIPT_URL_MANZILINGIZ"

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
    waiting_for_phone = State()
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
                    logging.info(f"Self-ping: {response.status}")
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
    args = message.text.split()
    
    target_id = None
    ref_by_name = "To'g'ridan-to'g'ri"
    
    if len(args) > 1:
        target_id = args[1]
        try:
            ref_user = await bot.get_chat(int(target_id))
            ref_by_name = ref_user.full_name
        except:
            ref_by_name = "Noma'lum"

    cursor.execute("SELECT phone FROM users WHERE user_id = ?", (user_id,))
    existing_user = cursor.fetchone()

    if not existing_user:
        # Yangi foydalanuvchi - telefon so'raymiz
        kb = ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="📱 Telefon raqamni yuborish", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
        # target_id ni saqlab qo'yamiz, telefon yuborgach kerak bo'ladi
        await state.update_data(ref_by_name=ref_by_name, pending_target=target_id)
        await message.answer(f"Salom {message.from_user.full_name}! Botdan foydalanish uchun telefon raqamingizni yuboring:", reply_markup=kb)
        await state.set_state(ChatStates.waiting_for_phone)
    else:
        # Eski foydalanuvchi
        if target_id and target_id != str(user_id):
            await state.update_data(target_id=target_id)
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
    pending_target = data.get('pending_target')
    
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?, ?, ?)", 
                   (user_id, message.from_user.username, datetime.now().date(), ref_by, phone))
    conn.commit()
    
    await save_to_google_sheets(message.from_user.full_name, user_id, message.from_user.username, phone, ref_by)
    await message.answer("✅ Ro'yxatdan o'tdingiz!", reply_markup=types.ReplyKeyboardRemove())
    
    if pending_target and pending_target != str(user_id):
        # Agar havola orqali kirgan bo'lsa, xabar yozishga o'tkazamiz
        await state.update_data(target_id=pending_target)
        await state.set_state(ChatStates.waiting_for_anon_message)
        await message.answer("📝 Endi anonim xabaringizni yozishingiz mumkin:")
    else:
        await send_personal_link(message, user_id)
        await state.clear()

@dp.message(ChatStates.waiting_for_anon_message)
async def handle_anon(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('target_id')
    
    # Qabul qiluvchi adminmi?
    target_is_admin = is_admin(int(target_id))
    
    # Javob berish tugmasi (qabul qiluvchi uchun)
    kb_for_receiver = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply_{message.from_user.id}")
    ]])
    
    try:
        header = "📩 Yangi anonim xabar:\n\n"
        if target_is_admin:
            # Agar admin bo'lsa barcha ma'lumotlarni ko'rsatamiz
            cursor.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
            user_phone = cursor.fetchone()[0]
            header = (f"👤 **Admin uchun ma'lumot:**\n"
                      f"Ism: {message.from_user.full_name}\n"
                      f"ID: {message.from_user.id}\n"
                      f"User: @{message.from_user.username or 'Yo`q'}\n"
                      f"Tel: {user_phone}\n\n"
                      f"{header}")
        
        await bot.send_message(target_id, header + (message.text or ""), entities=message.entities, reply_markup=kb_for_receiver)
        
        cursor.execute("INSERT INTO messages (sent_at) VALUES (?)", (datetime.now().date(),))
        conn.commit()
        
        # Yuboruvchi uchun "Yana xabar yuborish" tugmasi
        kb_for_sender = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Yana anonim xabar yuborish", callback_data=f"resend_{target_id}")
        ]])
        
        await message.answer("✅ Xabar yuborildi!", reply_markup=kb_for_sender)
        await send_personal_link(message, message.from_user.id)
        await state.clear()
        
    except Exception:
        await save_to_google_sheets(message.from_user.full_name, target_id, "", "", "", status="Blocked")
        await message.answer("❌ Xatolik! Bot bloklangan bo'lishi mumkin.")

@dp.callback_query(F.data.startswith("resend_"))
async def resend_callback(callback: types.CallbackQuery, state: FSMContext):
    target_id = callback.data.split("_")[1]
    await state.update_data(target_id=target_id)
    await state.set_state(ChatStates.waiting_for_anon_message)
    await callback.message.answer("📝 Marhamat, qayta xabaringizni yozing:")
    await callback.answer()

@dp.callback_query(F.data.startswith("reply_"))
async def start_reply(callback: types.CallbackQuery, state: FSMContext):
    sender_id = callback.data.split("_")[1]
    await state.update_data(reply_to=sender_id)
    await state.set_state(ChatStates.waiting_for_reply)
    await callback.message.answer("✍️ Javobingizni yozing:")
    await callback.answer()

@dp.message(ChatStates.waiting_for_reply)
async def deliver_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    reply_to = data.get('reply_to')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Yana javob yozish", callback_data=f"reply_{message.from_user.id}")]])
    
    try:
        await bot.send_message(reply_to, f"📩 Sizga javob keldi:\n\n{message.text}", entities=message.entities, reply_markup=kb)
        await message.answer("✅ Javobingiz yetkazildi!")
        await state.clear()
    except:
        await message.answer("❌ Xabar yetib bormadi.")

# --- ADMIN PANEL ---

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    if is_admin(message.from_user.id):
        kb_list = [
            [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
            [InlineKeyboardButton(text="📢 Reklama", callback_data="broadcast")]
        ]
        if message.from_user.id == ADMIN_ID:
            kb_list.append([
                InlineKeyboardButton(text="➕ Admin qo'shish", callback_data="add_adm"),
                InlineKeyboardButton(text="➖ Admin o'chirish", callback_data="rem_adm")
            ])
        kb = InlineKeyboardMarkup(inline_keyboard=kb_list)
        await message.answer("🛠 Admin boshqaruv paneli:", reply_markup=kb)

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    today = datetime.now().date()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sent_at = ?", (today,))
    msg_today = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    await callback.message.answer(f"📊 Statistika:\n\nBugun: {msg_today} xabar\nJami: {total_users} user")
    await callback.answer()

@dp.callback_query(F.data == "broadcast")
async def br_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatStates.waiting_for_broadcast_content)
    await callback.message.answer("Reklama xabarini yuboring:")
    await callback.answer()

@dp.message(ChatStates.waiting_for_broadcast_content)
async def br_content(message: types.Message, state: FSMContext):
    await state.update_data(content=message)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Havola", callback_data="add_link")],
        [InlineKeyboardButton(text="❌ Havolasiz", callback_data="send_no_link")]
    ])
    await message.answer("Tugmali havola qo'shilsinmi?", reply_markup=kb)

@dp.callback_query(F.data == "send_no_link")
async def no_link(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    content = data['content']
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            await content.copy_to(u[0])
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await callback.message.answer(f"✅ {count} ta foydalanuvchiga yuborildi.")
    await state.clear()
    await callback.answer()

# Loyihani ishga tushirish
async def main():
    asyncio.create_task(start_web_server())
    asyncio.create_task(self_ping())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

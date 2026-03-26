import asyncio
import logging
import sqlite3
import os
from datetime import datetime
from aiohttp import web
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.utils.deep_linking import create_start_link
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# --- SOZLAMALAR ---
API_TOKEN = '8672594017:AAElGsXRSz8hVeKRhVJw9URE0eCBb1_XYaI'
ADMIN_ID = 7861165622 

logging.basicConfig(level=logging.INFO)

# --- MA'LUMOTLAR OMBORI ---
conn = sqlite3.connect('anon_pro.db', check_same_thread=False)
cursor = conn.cursor()
cursor.execute('CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, username TEXT, joined_at DATE)')
cursor.execute('CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, sent_at DATE)')
conn.commit()

class ChatStates(StatesGroup):
    waiting_for_anon_message = State()
    waiting_for_reply = State()
    waiting_for_broadcast_content = State()
    waiting_for_link_url = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

# --- RENDER PORT (WEB SERVER) ---
async def handle(request):
    return web.Response(text="Bot faol ishlamoqda!")

async def start_web_server():
    app = web.Application()
    app.router.add_get('/', handle)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, '0.0.0.0', int(os.environ.get("PORT", 10000)))
    await site.start()

# --- YORDAMCHI FUNKSIYALAR ---
async def send_personal_link(message: types.Message, user_id: int):
    link = await create_start_link(bot, str(user_id), encode=False)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🚀 Havolani ulashish", switch_inline_query=f"\nMen bilan anonim gaplashing:\n{link}")
    ]])
    await message.answer(f"🔗 Shaxsiy havolangiz:\n\n{link}", reply_markup=kb)

def log_event():
    cursor.execute("INSERT INTO messages (sent_at) VALUES (?)", (datetime.now().date(),))
    conn.commit()

# --- HANDLERLAR ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (user_id, message.from_user.username, datetime.now().date()))
    conn.commit()

    args = message.text.split()
    if len(args) > 1:
        target_id = args[1]
        if target_id == str(user_id):
            return await message.answer("❌ O'zingizga yozish mumkin emas.")
        await state.update_data(target_id=target_id)
        await state.set_state(ChatStates.waiting_for_anon_message)
        await message.answer("📝 Anonim xabaringizni yozing:")
    else:
        await message.answer("Xush kelibsiz!")
        await send_personal_link(message, user_id)

# Anonim xabar yuborish mantiqi
@dp.message(ChatStates.waiting_for_anon_message)
async def handle_anon(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('target_id')
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply_{message.from_user.id}")]])
    
    try:
        header = "📩 Yangi anonim xabar:\n\n"
        if int(target_id) == ADMIN_ID:
            header = f"👤 Admin uchun (Ism: {message.from_user.full_name}, ID: {message.from_user.id})\n{header}"
        
        await bot.send_message(target_id, header + (message.text or ""), entities=message.entities, reply_markup=kb)
        log_event()
        await message.answer("✅ Xabar yuborildi!")
        await send_personal_link(message, message.from_user.id)
        await state.clear()
    except:
        await message.answer("❌ Xatolik! Bot bloklangan bo'lishi mumkin.")

# JAVOB BERISH TUGMASI (Tuzatilgan qism)
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
        log_event()
        await message.answer("✅ Javobingiz yetkazildi!")
        await send_personal_link(message, message.from_user.id)
        await state.clear()
    except:
        await message.answer("❌ Xabar yetib bormadi.")

# --- ADMIN PANEL ---

@dp.message(Command("admin"))
async def admin_menu(message: types.Message):
    if message.from_user.id == ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Statistika", callback_data="stats")],
            [InlineKeyboardButton(text="📢 Reklama", callback_data="broadcast")]
        ])
        await message.answer("🛠 Admin boshqaruv paneli:", reply_markup=kb)

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    today = datetime.now().date()
    this_month = today.strftime("%Y-%m")
    
    # 1. Bugungi javoblar (xabarlar) soni
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sent_at = ?", (today,))
    msg_today = cursor.fetchone()[0]
    
    # 2. Bugun botga qo'shilganlar
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at = ?", (today,))
    users_today = cursor.fetchone()[0]
    
    # 3. Shu oyda qo'shilganlar
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{this_month}%",))
    users_month = cursor.fetchone()[0]
    
    text = (f"📊 **Bot Statistikasi**\n\n"
            f"📩 Bugungi jami xabarlar: {msg_today} ta\n"
            f"👤 Bugun qo'shilganlar: {users_today} ta\n"
            f"📅 Shu oyda qo'shilganlar: {users_month} ta")
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# Reklama yuborish (Oldingi mantiq saqlangan)
@dp.callback_query(F.data == "broadcast")
async def br_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatStates.waiting_for_broadcast_content)
    await callback.message.answer("Reklama xabarini yuboring (Matn, Rasm, Video...):")
    await callback.answer()

@dp.message(ChatStates.waiting_for_broadcast_content)
async def br_content(message: types.Message, state: FSMContext):
    await state.update_data(content=message)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Havola qo'shish", callback_data="add_link")],
        [InlineKeyboardButton(text="❌ Havolasiz yuborish", callback_data="send_no_link")]
    ])
    await message.answer("Postga tugmali havola qo'shilsinmi?", reply_markup=kb)

@dp.callback_query(F.data == "add_link")
async def add_link(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatStates.waiting_for_link_url)
    await callback.message.answer("Tugma uchun URL yuboring (masalan: https://t.me/...):")
    await callback.answer()

@dp.callback_query(F.data == "send_no_link")
async def no_link(callback: types.CallbackQuery, state: FSMContext):
    await final_broadcast(callback.message, state, None)
    await callback.answer()

@dp.message(ChatStates.waiting_for_link_url)
async def get_link(message: types.Message, state: FSMContext):
    if message.text.startswith("http"):
        await final_broadcast(message, state, message.text)
    else:
        await message.answer("URL noto'g'ri. http... bilan yuboring.")

async def final_broadcast(message, state, url):
    data = await state.get_data()
    content = data['content']
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🔗 Kirish", url=url)]]) if url else None
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            await content.copy_to(u[0], reply_markup=kb)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await message.answer(f"✅ {count} ta foydalanuvchiga yuborildi.")
    await state.clear()

async def main():
    asyncio.create_task(start_web_server())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

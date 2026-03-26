import asyncio
import logging
import sqlite3
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command, CommandStart
from aiogram.utils.deep_linking import create_start_link
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, SwitchInlineQueryChosenChat
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup

# --- Sozlamalar ---
API_TOKEN = '8473159649:AAG0IugU_AKJ6EMPVjWvfZj9f5w_qHXmEUc'
ADMIN_ID = 7861165622  # O'zingizning ID-ingiz

logging.basicConfig(level=logging.INFO)

# --- Ma'lumotlar ombori (Kengaytirilgan) ---
conn = sqlite3.connect('anon_pro.db')
cursor = conn.cursor()
cursor.execute('''CREATE TABLE IF NOT EXISTS users 
                  (user_id INTEGER PRIMARY KEY, username TEXT, joined_at DATE)''')
cursor.execute('''CREATE TABLE IF NOT EXISTS messages 
                  (id INTEGER PRIMARY KEY AUTOINCREMENT, sent_at DATE)''')
conn.commit()

class ChatStates(StatesGroup):
    waiting_for_anon_message = State()
    waiting_for_reply = State()
    waiting_for_broadcast = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- Yordamchi Funksiyalar ---
async def send_personal_link(message: types.Message, user_id: int):
    link = await create_start_link(bot, str(user_id), encode=False)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Havolani ulashish", 
                              switch_inline_query=f"\nMen bilan anonim gaplashish uchun bosing:\n{link}")]
    ])
    await message.answer(f"🔗 Bu sizning shaxsiy havolangiz:\n\n{link}", reply_markup=kb)

def log_message():
    cursor.execute("INSERT INTO messages (sent_at) VALUES (?)", (datetime.now().date(),))
    conn.commit()

# --- Handlerlar ---

@dp.message(CommandStart())
async def start_cmd(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    today = datetime.now().date()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?, ?, ?)", (user_id, message.from_user.username, today))
    conn.commit()

    args = message.text.split()
    if len(args) > 1:
        target_id = args[1]
        if target_id == str(user_id):
            await message.answer("❌ O'zingizga yozish mumkin emas.")
            return
        await state.update_data(target_id=target_id)
        await state.set_state(ChatStates.waiting_for_anon_message)
        await message.answer("📝 Anonim xabaringizni yozing:")
    else:
        await message.answer("Xush kelibsiz! Quyidagi havola orqali sizga anonim xabar yozishlari mumkin.")
        await send_personal_link(message, user_id)

# Anonim xabar yuborish
@dp.message(ChatStates.waiting_for_anon_message)
async def handle_anon(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('target_id')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply_{message.from_user.id}")]
    ])
    
    try:
        header = "📩 Yangi anonim xabar:\n\n"
        if int(target_id) == ADMIN_ID:
            header = f"👤 Kimdan: {message.from_user.full_name} (ID: {message.from_user.id})\n{header}"
        
        await bot.send_message(target_id, f"{header}{message.text}", reply_markup=kb)
        await message.answer("✅ Xabar yuborildi!")
        log_message()
        await send_personal_link(message, message.from_user.id) # Yuborganga ham o'z havolasini berish
        await state.clear()
    except:
        await message.answer("❌ Xatolik yuz berdi.")

# Javob berish tugmasi
@dp.callback_query(F.data.startswith("reply_"))
async def start_reply(callback: types.CallbackQuery, state: FSMContext):
    sender_id = callback.data.split("_")[1]
    await state.update_data(reply_to=sender_id)
    await state.set_state(ChatStates.waiting_for_reply)
    await callback.message.answer("✍️ Javobingizni yozing:")
    await callback.answer()

# Javobni yetkazish
@dp.message(ChatStates.waiting_for_reply)
async def deliver_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    reply_to = data.get('reply_to')
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✍️ Yana javob yozish", callback_data=f"reply_{message.from_user.id}")]
    ])
    
    try:
        await bot.send_message(reply_to, f"📩 Sizga javob keldi:\n\n{message.text}", reply_markup=kb)
        await message.answer("✅ Javobingiz yetkazildi!")
        log_message()
        await send_personal_link(message, message.from_user.id)
        await state.clear()
    except:
        await message.answer("❌ Xabar yetib bormadi.")

# --- Admin Panel ---
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
    
    # Statistika hisoblash
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sent_at = ?", (today,))
    msg_today = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at = ?", (today,))
    users_today = cursor.fetchone()[0]
    
    cursor.execute("SELECT COUNT(*) FROM users WHERE joined_at LIKE ?", (f"{this_month}%",))
    users_month = cursor.fetchone()[0]
    
    text = (f"📊 **Bot Statistikasi**\n\n"
            f"📅 Bugungi xabarlar: {msg_today} ta\n"
            f"🆕 Bugun qo'shilganlar: {users_today} ta\n"
            f"📅 Shu oyda qo'shilganlar: {users_month} ta")
    await callback.message.answer(text, parse_mode="Markdown")
    await callback.answer()

# Reklama yuborish handlerlari (avvalgi kod bilan bir xil)
@dp.callback_query(F.data == "broadcast")
async def br_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatStates.waiting_for_broadcast)
    await callback.message.answer("Reklama xabarini yuboring:")
    await callback.answer()

@dp.message(ChatStates.waiting_for_broadcast)
async def br_do(message: types.Message, state: FSMContext):
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    for u in users:
        try: await message.copy_to(u[0])
        except: pass
    await message.answer("✅ Tarqatildi.")
    await state.clear()

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

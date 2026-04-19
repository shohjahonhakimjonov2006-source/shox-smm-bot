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
API_TOKEN = '8672594017:AAEXn8w8dUyhENFdcTk1qZwTRqQ6tI3rAOs'
ADMIN_ID = 7861165622 
APP_URL = "https://shox-smm-bot.onrender.com"
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
            "phone": phone if phone else "Yuborilmagan",
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

    # Foydalanuvchini bazaga darhol qo'shish (Telefon so'ramasdan)
    cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
    if not cursor.fetchone():
        cursor.execute("INSERT OR IGNORE INTO users (user_id, username, joined_at, ref_by) VALUES (?, ?, ?, ?)", 
                       (user_id, message.from_user.username, datetime.now().date(), ref_by_name))
        conn.commit()
        await save_to_google_sheets(message.from_user.full_name, user_id, message.from_user.username, "Yo'q", ref_by_name)

    if target_id and target_id != str(user_id):
        await state.update_data(target_id=target_id)
        await state.set_state(ChatStates.waiting_for_anon_message)
        await message.answer("📝 Anonim xabaringizni yozing:")
    else:
        await message.answer(f"Xush kelibsiz, {message.from_user.full_name}!")
        await send_personal_link(message, user_id)

@dp.message(ChatStates.waiting_for_anon_message)
async def handle_anon(message: types.Message, state: FSMContext):
    data = await state.get_data()
    target_id = data.get('target_id')
    
    target_is_admin = is_admin(int(target_id))
    kb_for_receiver = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✍️ Javob berish", callback_data=f"reply_{message.from_user.id}")
    ]])
    
    try:
        header = "📩 Yangi anonim xabar:\n\n"
        if target_is_admin:
            cursor.execute("SELECT phone FROM users WHERE user_id = ?", (message.from_user.id,))
            res = cursor.fetchone()
            user_phone = res[0] if res and res[0] else "Yuborilmagan"
            header = (f"👤 **Admin uchun ma'lumot:**\n"
                      f"Ism: {message.from_user.full_name}\n"
                      f"ID: {message.from_user.id}\n"
                      f"User: @{message.from_user.username or 'Yo`q'}\n"
                      f"Tel: {user_phone}\n\n"
                      f"{header}")
        
        await bot.send_message(target_id, header + (message.text or ""), entities=message.entities, reply_markup=kb_for_receiver)
        cursor.execute("INSERT INTO messages (sent_at) VALUES (?)", (datetime.now().date(),))
        conn.commit()
        
        kb_for_sender = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🔄 Yana anonim xabar yuborish", callback_data=f"resend_{target_id}")
        ]])
        
        await message.answer("✅ Xabar yuborildi!", reply_markup=kb_for_sender)
        await send_personal_link(message, message.from_user.id)
        await state.clear()
        
    except Exception:
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

# Admin qo'shish va o'chirish handlerlari
@dp.callback_query(F.data == "add_adm")
async def add_adm_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id == ADMIN_ID:
        await state.set_state(ChatStates.waiting_for_new_admin)
        await callback.message.answer("Yangi adminning ID raqamini yuboring:")
    await callback.answer()

@dp.message(ChatStates.waiting_for_new_admin)
async def add_adm_finish(message: types.Message, state: FSMContext):
    try:
        new_id = int(message.text)
        cursor.execute("INSERT OR IGNORE INTO admins VALUES (?)", (new_id,))
        conn.commit()
        await message.answer(f"✅ {new_id} muvaffaqiyatli admin qilindi.")
        await state.clear()
    except ValueError:
        await message.answer("❌ Xato! Faqat raqamlardan iborat ID yuboring.")

@dp.callback_query(F.data == "rem_adm")
async def rem_adm_start(callback: types.CallbackQuery, state: FSMContext):
    if callback.from_user.id == ADMIN_ID:
        await state.set_state(ChatStates.waiting_for_remove_admin)
        await callback.message.answer("O'chiriladigan adminning ID raqamini yuboring:")
    await callback.answer()

@dp.message(ChatStates.waiting_for_remove_admin)
async def rem_adm_finish(message: types.Message, state: FSMContext):
    try:
        rem_id = int(message.text)
        if rem_id == ADMIN_ID:
            await message.answer("❌ Asosiy adminni o'chirib bo'lmaydi!")
        else:
            cursor.execute("DELETE FROM admins WHERE admin_id = ?", (rem_id,))
            conn.commit()
            await message.answer(f"✅ {rem_id} adminlikdan olindi.")
            await state.clear()
    except ValueError:
        await message.answer("❌ Xato! Faqat raqamlardan iborat ID yuboring.")

@dp.callback_query(F.data == "stats")
async def show_stats(callback: types.CallbackQuery):
    today = datetime.now().date()
    cursor.execute("SELECT COUNT(*) FROM messages WHERE sent_at = ?", (today,))
    msg_today = cursor.fetchone()[0]
    cursor.execute("SELECT COUNT(*) FROM users")
    total_users = cursor.fetchone()[0]
    await callback.message.answer(f"📊 Statistika:\n\nBugun: {msg_today} xabar\nJami: {total_users} user")
    await callback.answer()

# Reklama mantiqi
@dp.callback_query(F.data == "broadcast")
async def br_start(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatStates.waiting_for_broadcast_content)
    await callback.message.answer("Reklama xabarini (rasm, video yoki matn) yuboring:")
    await callback.answer()

@dp.message(ChatStates.waiting_for_broadcast_content)
async def br_content(message: types.Message, state: FSMContext):
    await state.update_data(broadcast_msg=message)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Havola qo'shish", callback_data="add_link")],
        [InlineKeyboardButton(text="❌ Havolasiz yuborish", callback_data="send_no_link")]
    ])
    await message.answer("Reklamaga tugmali havola qo'shilsinmi?", reply_markup=kb)

@dp.callback_query(F.data == "add_link")
async def add_link_url(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(ChatStates.waiting_for_link_url)
    await callback.message.answer("Tugma uchun URL manzilini yuboring (masalan: https://t.me/...):")
    await callback.answer()

@dp.message(ChatStates.waiting_for_link_url)
async def process_broadcast_with_link(message: types.Message, state: FSMContext):
    if not message.text.startswith("http"):
        await message.answer("❌ Xato! Havola http:// yoki https:// bilan boshlanishi kerak.")
        return

    data = await state.get_data()
    broadcast_msg = data['broadcast_msg']
    url = message.text
    
    # "Kirish" tugmasini yaratish
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="Kirish", url=url)]])
    
    cursor.execute("SELECT user_id FROM users")
    users = cursor.fetchall()
    count = 0
    for u in users:
        try:
            await broadcast_msg.copy_to(u[0], reply_markup=kb)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    
    await message.answer(f"✅ Havola bilan {count} ta foydalanuvchiga yuborildi.")
    await state.clear()

@dp.callback_query(F.data == "send_no_link")
async def no_link(callback: types.CallbackQuery, state: FSMContext):
    data = await state.get_data()
    content = data['broadcast_msg']
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

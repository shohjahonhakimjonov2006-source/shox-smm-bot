import asyncio
import logging
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardMarkup, KeyboardButton
from aiogram.utils.deep_linking import create_start_link
from motor.motor_asyncio import AsyncIOMotorClient

# --- SOZLAMALAR ---
API_TOKEN = '8678413684:AAHnoyOgk5AhKwF4kYbcu_11d5M5rpLgpw0'
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/smm_ultra?retryWrites=true&w=majority"
ADMIN_ID = 7861165622

# --- BAZA ---
client = AsyncIOMotorClient(MONGO_URL)
db = client['smm_ultra']
users_col = db['users']
settings_col = db['settings']
stats_backup_col = db['stats_backup']

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# --- YORDAMCHI FUNKSIYALAR ---
async def get_settings():
    s = await settings_col.find_one({"id": "config"})
    if not s:
        s = {
            "id": "config",
            "channels": [], 
            "gift_text": "Sovg'alar hali belgilanmagan",
            "terms_text": "O'yin shartlari hali kiritilmagan",
            "point_per_ref": 10,
            "cert_limit": 50,
            "private_channel": "https://t.me/+example"
        }
        await settings_col.insert_one(s)
    return s

async def is_subscribed(user_id, channels):
    for ch in channels:
        try:
            chat_id = ch['id']
            member = await bot.get_chat_member(chat_id, user_id)
            if member.status in ['left', 'kicked']: return False
        except Exception: return False
    return True

# --- KLAVIATURALAR ---
def main_menu():
    kb = [
        [KeyboardButton(text="🎁 Konkursga qatnashish")],
        [KeyboardButton(text="📊 Reyting"), KeyboardButton(text="💰 Ballarim")],
        [KeyboardButton(text="📜 Shartlar"), KeyboardButton(text="🏆 Sovg'alar")],
        [KeyboardButton(text="🎓 Sertifikat olish")]
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_menu():
    kb = [
        [InlineKeyboardButton(text="📢 Xabar yuborish", callback_data="adm_broadcast")],
        [InlineKeyboardButton(text="📢 Kanallar", callback_data="adm_channels"), InlineKeyboardButton(text="⚙️ Ball miqdori", callback_data="adm_points")],
        [InlineKeyboardButton(text="🎁 Sovg'alarni o'zgartirish", callback_data="adm_gifts")],
        [InlineKeyboardButton(text="🔄 Statistikani tozalash", callback_data="adm_clear_stats")],
        [InlineKeyboardButton(text="🔍 ID orqali topish", callback_data="adm_find_user")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# --- USER HANDLERLAR ---
@dp.message(CommandStart())
async def start_cmd(message: types.Message):
    user_id = message.from_user.id
    args = message.text.split()
    config = await get_settings()
    
    user = await users_col.find_one({"user_id": user_id})
    
    if not user:
        # Yangi foydalanuvchi ID raqamini aniqlash
        total_users = await users_col.count_documents({})
        new_user = {
            "user_id": user_id,
            "custom_id": total_users + 1,
            "username": message.from_user.username,
            "full_name": message.from_user.full_name,
            "points": 0,
            "referred_by": None,
            "full_point_claimed": False
        }
        
        # FAQAT REFERAL HAVOLA ORQALI KELGANDA
        if len(args) > 1 and args[1].isdigit():
            referrer_id = int(args[1])
            if referrer_id != user_id:
                new_user["referred_by"] = referrer_id
                # Start bosgan zahoti 1/3 ball
                bonus = config['point_per_ref'] // 3
                await users_col.update_one({"user_id": referrer_id}, {"$inc": {"points": bonus}})
                await bot.send_message(referrer_id, f"🔔 Yangi do'st! Start bosgani uchun {bonus} ball berildi.")
        
        await users_col.insert_one(new_user)
    
    await message.answer("Xush kelibsiz! Konkursda ishtirok eting.", reply_markup=main_menu())

@dp.message(F.text == "💰 Ballarim")
async def my_points(message: types.Message):
    u = await users_col.find_one({"user_id": message.from_user.id})
    await message.answer(f"Sizning balingiz: **{u['points']}** ball", parse_mode="Markdown")

@dp.message(F.text == "🎁 Konkursga qatnashish")
async def join_contest(message: types.Message):
    config = await get_settings()
    user_id = message.from_user.id
    
    if await is_subscribed(user_id, config['channels']):
        link = await create_start_link(bot, str(user_id), encode=False)
        await message.answer(f"Siz barcha kanallarga obunasiz! ✅\n\nSizning taklif havolangiz:\n{link}")
        
        # Qolgan ballni berish
        u = await users_col.find_one({"user_id": user_id})
        if u.get("referred_by") and not u.get("full_point_claimed"):
            full_bonus = config['point_per_ref'] - (config['point_per_ref'] // 3)
            await users_col.update_one({"user_id": u['referred_by']}, {"$inc": {"points": full_bonus}})
            await users_col.update_one({"user_id": user_id}, {"$set": {"full_point_claimed": True}})
            await bot.send_message(u['referred_by'], "🔥 Do'stingiz kanallarga obuna bo'ldi! To'liq ball berildi.")
    else:
        btns = [[InlineKeyboardButton(text="Kanalga o'tish", url=c['url'])] for c in config['channels']]
        btns.append([InlineKeyboardButton(text="✅ Tekshirish", callback_data="check_sub")])
        await message.answer("Konkursda qatnashish uchun quyidagi kanallarga obuna bo'ling:", reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

# --- ADMIN HANDLERLAR ---
@dp.message(Command("admin"), F.from_user.id == ADMIN_ID)
async def admin_panel(message: types.Message):
    await message.answer("🛠 Admin Panelga xush kelibsiz:", reply_markup=admin_menu())

@dp.callback_query(F.data == "adm_broadcast")
async def start_broadcast(call: types.CallbackQuery):
    await call.message.answer("Xabaringizni yuboring (Hamma foydalanuvchilarga boradi):")
    # Bu yerda FSM (Finite State Machine) ishlatish tavsiya etiladi, lekin soddalik uchun xabar kutish mantiqi

@dp.message(F.text == "📊 Reyting")
async def rating(message: types.Message):
    cursor = users_col.find().sort("points", -1).limit(100)
    text = "🏆 **TOP 100 FOYDALANUVCHI**\n\n"
    rank = 1
    async for u in cursor:
        text += f"{rank}. {u['full_name']} — {u['points']} ball\n"
        rank += 1
    await message.answer(text, parse_mode="Markdown")

# --- BOTNI ISHGA TUSHIRISH ---
async def main():
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

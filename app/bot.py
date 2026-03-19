import asyncio
import logging
from aiogram import Bot, Dispatcher
from .config import BOT_TOKEN
from .handlers import register

# Loglarni ko'rish uchun (xatolarni terminalda chiqaradi)
logging.basicConfig(level=logging.INFO)

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Handlerlarni ro'yxatga olish
register(dp, bot)

async def main():
    print("Bot ishga tushdi...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        print("Bot to'xtatildi")

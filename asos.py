async def on_startup():
    await bot.send_message(ADMIN_ID, "🚀 Bot Render'da muvaffaqiyatli ishga tushdi!")

async def main():
    # Render portini tinglash
    port = int(os.environ.get("PORT", 10000))
    asyncio.create_task(asyncio.start_server(lambda r, w: None, '0.0.0.0', port))
    
    # Botni ishga tushirish haqida xabar
    await on_startup()
    
    await dp.start_polling(bot)

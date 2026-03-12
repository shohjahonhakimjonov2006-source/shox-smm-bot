# --- ADMIN KLAVIATURASI ---
admin_kb = ReplyKeyboardMarkup(keyboard=[
    [KeyboardButton(text="🔄 Xizmatlarni yangilash")],
    [KeyboardButton(text="📊 Statistika"), KeyboardButton(text="🏠 Asosiy menyu")]
], resize_keyboard=True)

# --- XIZMATLARNI YANGILASH FUNKSIYASI ---
@dp.message(F.text == "🔄 Xizmatlarni yangilash")
async def update_services_from_api(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    msg = await message.answer("🔄 API bilan aloqa o'rnatilmoqda...")
    
    async with aiohttp.ClientSession() as session:
        try:
            # API-dan xizmatlar ro'yxatini olish
            async with session.post(SMM_API_URL, data={'key': SMM_API_KEY, 'action': 'services'}) as resp:
                services_list = await resp.json()
                
                if isinstance(services_list, list):
                    # Bazani tozalash
                    await services_col.delete_many({})
                    
                    # Yangi xizmatlarni bazaga joylash
                    for s in services_list:
                        await services_col.insert_one({
                            'id': str(s['service']),
                            'name': s['name'],
                            'category': s['category'], # JSONdagi "category" maydoni
                            'price': float(s['rate']),
                            'min': int(s['min']),
                            'max': int(s['max']),
                            'refill': s.get('refill', False)
                        })
                    
                    await msg.edit_text(f"✅ Yangilanish muvaffaqiyatli! \n📦 Jami: {len(services_list)} ta xizmat yuklandi.")
                else:
                    await msg.edit_text("❌ API xatosi: Ma'lumotlar ro'yxat shaklida kelmadi.")
        except Exception as e:
            await msg.edit_text(f"❌ Xatolik: {str(e)}")

# --- FOYDALANUVCHI TANLAGAN KATEGORIYANI KO'RSATISH ---
@dp.message(F.text.in_(["Telegram", "Instagram", "Tik tok", "YouTube", "Facebook"]))
async def show_category_services(message: types.Message):
    # Foydalanuvchi bosgan tugma nomi bilan bazadagi "category"ni solishtiramiz
    cat = message.text
    services = await services_col.find({"category": {"$regex": cat, "$options": "i"}}).to_list(length=20)
    
    if not services:
        return await message.answer(f"😔 Kechirasiz, {cat} bo'limida hozircha xizmatlar yo'q.")
    
    kb = []
    for s in services:
        kb.append([InlineKeyboardButton(text=f"{s['name']} - {s['price']} so'm", callback_data=f"srv_{s['id']}")])
    
    await message.answer(f"📁 {cat} bo'limidagi xizmatlar:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

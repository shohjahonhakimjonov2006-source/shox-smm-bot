# --- ADMIN HOLATLARI (FSM) ---
class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
    # Qo'lda xizmat qo'shish uchun:
    manual_service_name = State()
    manual_service_price = State()
    manual_service_id = State()
    manual_service_cat = State()

# --- ADMIN PANEL ---
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return await message.answer(f"❌ Siz admin emassiz. ID: {message.from_user.id}")
    
    admin_kb = ReplyKeyboardMarkup(keyboard=[
        [KeyboardButton(text="🔄 Xizmatlarni yangilash"), KeyboardButton(text="📊 Statistika")],
        [KeyboardButton(text="💰 Balans qo'shish"), KeyboardButton(text="➕ Yangi xizmat qo'shish")],
        [KeyboardButton(text="🏠 Asosiy menyu")]
    ], resize_keyboard=True)
    
    await message.answer("🛠 **Admin boshqaruv paneli:**", reply_markup=admin_kb)

# --- 📊 STATISTIKA VA UMUMIY SUMMALAR ---
@dp.message(F.text == "📊 Statistika")
async def admin_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    
    user_count = await users_col.count_documents({})
    order_count = await orders_col.count_documents({})
    
    # Umumiy kiritilgan summalar (Aggregatsiya)
    pipeline = [{"$group": {"_id": None, "total": {"$sum": "$total_deposited"}}}]
    cursor = users_col.aggregate(pipeline)
    result = await cursor.to_list(length=1)
    total_money = result[0]['total'] if result else 0
    
    stats_text = (
        "📊 **Botning umumiy holati:**\n\n"
        f"👥 Foydalanuvchilar: {user_count} ta\n"
        f"📦 Jami buyurtmalar: {order_count} ta\n"
        f"💰 Kiritilgan jami mablag': {total_money:,.2f} so'm"
    )
    await message.answer(stats_text, parse_mode="Markdown")

# --- ➕ QO'LDA XIZMAT QO'SHISH (MANUAL ADD) ---
@dp.message(F.text == "➕ Yangi xizmat qo'shish")
async def manual_srv_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("📝 Xizmat nomini yuboring:\n(Masalan: Telegram VIP Obunachi)")
    await state.set_state(AdminState.manual_service_name)

@dp.message(AdminState.manual_service_name)
async def manual_srv_name(message: types.Message, state: FSMContext):
    await state.update_data(m_name=message.text)
    await message.answer("💵 1000 tasi uchun narxni kiriting (faqat raqam):")
    await state.set_state(AdminState.manual_service_price)

@dp.message(AdminState.manual_service_price)
async def manual_srv_price(message: types.Message, state: FSMContext):
    if not message.text.replace('.', '', 1).isdigit():
        return await message.answer("❌ Narxni raqamda yuboring!")
    await state.update_data(m_price=float(message.text))
    await message.answer("🔑 SMM Panel ID-sini (Service Key) yuboring:\n(API-dagi ID raqami)")
    await state.set_state(AdminState.manual_service_id)

@dp.message(AdminState.manual_service_id)
async def manual_srv_id(message: types.Message, state: FSMContext):
    await state.update_data(m_id=message.text)
    await message.answer("📁 Kategoriya nomini yuboring:\n(Masalan: Telegram)")
    await state.set_state(AdminState.manual_service_cat)

@dp.message(AdminState.manual_service_cat)
async def manual_srv_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    
    # Bazaga qo'shish
    await services_col.insert_one({
        'id': data['m_id'],
        'name': data['m_name'],
        'price': data['m_price'],
        'category': message.text,
        'manual': True # Qo'lda qo'shilganini belgilab qo'yamiz
    })
    
    await message.answer(f"✅ Yangi xizmat qo'shildi va menyuda paydo bo'ldi!\n\n📌 {data['m_name']}")
    await state.clear()

# --- BALANS QO'SHISH (Sizda bor kod, lekin integratsiya qilingan) ---
@dp.message(F.text == "💰 Balans qo'shish")
async def add_balance_start(message: types.Message, state: FSMContext):
    if message.from_user.id != ADMIN_ID: return
    await message.answer("👤 Foydalanuvchi ID raqamini kiriting:")
    await state.set_state(AdminState.waiting_for_user_id)

@dp.message(AdminState.waiting_for_user_id)
async def process_uid(message: types.Message, state: FSMContext):
    await state.update_data(t_id=int(message.text))
    await message.answer("💵 Summani kiriting:")
    await state.set_state(AdminState.waiting_for_amount)

@dp.message(AdminState.waiting_for_amount)
async def process_amount(message: types.Message, state: FSMContext):
    amount = float(message.text)
    data = await state.get_data()
    await users_col.update_one({'user_id': data['t_id']}, {'$inc': {'balance': amount, 'total_deposited': amount}})
    await message.answer(f"✅ {data['t_id']} hisobiga {amount} qo'shildi.")
    await state.clear()

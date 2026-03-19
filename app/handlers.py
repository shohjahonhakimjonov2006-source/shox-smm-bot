from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.fsm.context import FSMContext
from datetime import datetime
from bson import ObjectId

from .db import users, orders, services
from .states import OrderState
from .api import create_order, order_status

def menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Services"), KeyboardButton(text="💰 Balance")],
            [KeyboardButton(text="💳 Pay"), KeyboardButton(text="📦 Orders")]
        ],
        resize_keyboard=True
    )

def register(dp, bot):

    @dp.message(Command("start"))
    async def start(msg: types.Message):
        user = await users.find_one({"id": msg.from_user.id})
        if not user:
            await users.insert_one({"id": msg.from_user.id, "balance": 0})
        await msg.answer("🚀 ULTRA SMM BOT xizmatiga xush kelibsiz!", reply_markup=menu())

    @dp.message(F.text == "💰 Balance")
    async def balance(msg: types.Message):
        user = await users.find_one({"id": msg.from_user.id})
        bal = user.get("balance", 0) if user else 0
        await msg.answer(f"Sizning balansingiz: {bal} so'm")

    @dp.message(F.text == "🛒 Services")
    async def services_list(msg: types.Message):
        data = await services.find().to_list(100)
        if not data:
            return await msg.answer("Hozircha xizmatlar qo'shilmagan.")

        builder = InlineKeyboardBuilder()
        for s in data:
            builder.row(InlineKeyboardButton(text=f"{s['name']} - {s['price']}", callback_data=f"svc_{s['_id']}"))
        
        await msg.answer("Xizmatni tanlang:", reply_markup=builder.as_markup())

    @dp.callback_query(F.data.startswith("svc_"))
    async def select_svc(call: types.CallbackQuery, state: FSMContext):
        sid = call.data.split("_")[1]
        service = await services.find_one({"_id": ObjectId(sid)})
        
        if not service:
            return await call.answer("Xizmat topilmadi!", show_alert=True)

        service['_id'] = str(service['_id']) # State ichida saqlash uchun stringga o'tkazamiz
        await state.update_data(service=service)
        await call.message.answer(f"Tanlandi: {service['name']}\n\nHavolani yuboring:")
        await state.set_state(OrderState.link)
        await call.answer()

    @dp.message(OrderState.link)
    async def process_link(msg: types.Message, state: FSMContext):
        await state.update_data(link=msg.text)
        await msg.answer("Miqdorni kiriting (masalan: 1000):")
        await state.set_state(OrderState.qty)

    @dp.message(OrderState.qty)
    async def process_qty(msg: types.Message, state: FSMContext):
        if not msg.text.isdigit():
            return await msg.answer("Faqat raqam kiriting!")

        data = await state.get_data()
        service = data['service']
        qty = int(msg.text)
        link = data['link']
        
        price = float(service['price']) * qty
        user = await users.find_one({"id": msg.from_user.id})

        if user.get("balance", 0) < price:
            return await msg.answer(f"❌ Mablag' yetarli emas!\nKerak: {price}\nSizda: {user.get('balance')}")

        # API Order
        res = await create_order(service['api_id'], link, qty)
        
        if res.get("order"):
            await users.update_one({"id": msg.from_user.id}, {"$inc": {"balance": -price}})
            await orders.insert_one({
                "user": msg.from_user.id,
                "order_id": res.get("order"),
                "status": "Pending",
                "date": datetime.utcnow()
            })
            await msg.answer(f"✅ Buyurtma qabul qilindi!\nID: {res.get('order')}")
        else:
            await msg.answer(f"❌ API Xatolik: {res.get('error', 'Noma`lum')}")
        
        await state.clear()

    @dp.message(F.text == "📦 Orders")
    async def my_orders(msg: types.Message):
        user_orders = await orders.find({"user": msg.from_user.id}).sort("date", -1).limit(5).to_list(5)
        if not user_orders:
            return await msg.answer("Buyurtmalar topilmadi.")

        res_text = "Oxirgi 5 ta buyurtmangiz:\n\n"
        for o in user_orders:
            status_api = await order_status(o['order_id'])
            res_text += f"🆔 {o['order_id']} | 🔄 {status_api.get('status', 'Noma`lum')}\n"
        
        await msg.answer(res_text)

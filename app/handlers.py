from aiogram import types, F
from aiogram.filters import Command
from aiogram.types import *
from datetime import datetime

from .db import users, orders, services
from .states import OrderState, PayState
from .api import create_order, order_status
from .config import ADMIN_ID

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
        await msg.answer("🚀 ULTRA SMM BOT", reply_markup=menu())

    @dp.message(F.text == "💰 Balance")
    async def balance(msg):
        user = await users.find_one({"id": msg.from_user.id})
        await msg.answer(f"Balance: {user['balance']}")

    @dp.message(F.text == "🛒 Services")
    async def services_list(msg):
        data = await services.find().to_list(50)

        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s["name"], callback_data=f"svc_{s['_id']}")]
            for s in data
        ])

        await msg.answer("Select service:", reply_markup=kb)

    @dp.callback_query(F.data.startswith("svc_"))
    async def select(call, state):
        sid = call.data.split("_")[1]
        service = await services.find_one({"_id": sid})

        await state.update_data(service=service)
        await call.message.answer("Send link:")
        await state.set_state(OrderState.link)

    @dp.message(OrderState.link)
    async def link(msg, state):
        await state.update_data(link=msg.text)
        await msg.answer("Quantity:")
        await state.set_state(OrderState.qty)

    @dp.message(OrderState.qty)
    async def qty(msg, state):
        data = await state.get_data()

        service = data["service"]
        qty = int(msg.text)
        link = data["link"]

        price = service["price"] * qty
        user = await users.find_one({"id": msg.from_user.id})

        if user["balance"] < price:
            return await msg.answer("❌ Not enough balance")

        res = await create_order(service["api_id"], link, qty)

        await users.update_one(
            {"id": msg.from_user.id},
            {"$inc": {"balance": -price}}
        )

        await orders.insert_one({
            "user": msg.from_user.id,
            "order_id": res.get("order"),
            "status": "pending",
            "date": datetime.utcnow()
        })

        await msg.answer(f"✅ Order placed: {res.get('order')}")
        await state.clear()

    @dp.message(F.text == "📦 Orders")
    async def my_orders(msg):
        data = await orders.find({"user": msg.from_user.id}).to_list(50)

        text = ""
        for o in data:
            st = await order_status(o["order_id"])
            text += f"{o['order_id']} - {st.get('status')}\n"

        await msg.answer(text or "No orders")

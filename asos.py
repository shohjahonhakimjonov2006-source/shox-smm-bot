import asyncio
import logging
import os
from datetime import datetime

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

from motor.motor_asyncio import AsyncIOMotorClient
from bson import ObjectId
from aiohttp import web


TOKEN = "8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo"
ADMIN_ID = 7861165622

MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?appName=ZOirbek2003"


logging.basicConfig(level=logging.INFO)

bot = Bot(token=TOKEN)
dp = Dispatcher()


client = AsyncIOMotorClient(MONGO_URL)

db = client["bot_database"]

users_col = db["users"]
services_col = db["services"]
categories_col = db["categories"]
orders_col = db["orders"]
settings_col = db["settings"]
promo_col = db["promo_codes"]
payments_col = db["payments"]
class AdminState(StatesGroup):

    add_cat = State()

    add_serv_cat = State()
    add_serv_name = State()
    add_serv_price = State()

    add_card_name = State()
    add_card_num = State()

    edit_user_id = State()
    edit_user_balance = State()

    broadcast_msg = State()

    add_promo_code = State()
    add_promo_sum = State()
    add_promo_limit = State()

    set_daily_amount = State()


class UserState(StatesGroup):

    order_link = State()

    pay_photo = State()
    pay_sum = State()

    help_msg = State()

    enter_promo = State()
def main_kb():

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Xizmatlar"), KeyboardButton(text="💰 Balans")],
            [KeyboardButton(text="💳 Hisobni to'ldirish"), KeyboardButton(text="📊 Statistika")],
            [KeyboardButton(text="🎁 Bonuslar"), KeyboardButton(text="🆘 Yordam")]
        ],
        resize_keyboard=True
    )


def admin_kb():

    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📂 Bo'lim/Xizmatlar"), KeyboardButton(text="📊 Admin Statistika")],
            [KeyboardButton(text="💳 Karta sozlamalari"), KeyboardButton(text="👤 Balans tahrirlash")],
            [KeyboardButton(text="📢 Xabar yuborish"), KeyboardButton(text="🎟 Bonus sozlamalari")],
            [KeyboardButton(text="🏠 Bosh menyu")]
        ],
        resize_keyboard=True
    )
@dp.message(Command("start"))
async def start_handler(message: types.Message, state: FSMContext):

    await state.clear()

    u_id = message.from_user.id

    today = datetime.now().strftime("%Y-%m-%d")

    await users_col.update_one(
        {"user_id": u_id},
        {
            "$set": {
                "full_name": message.from_user.full_name,
                "last_seen": today
            },
            "$setOnInsert": {
                "balance": 0,
                "total_in": 0,
                "last_daily": None,
                "used_promos": []
            }
        },
        upsert=True
    )

    await message.answer(
        f"Xush kelibsiz {message.from_user.full_name}",
        reply_markup=main_kb()
    )

    if u_id == ADMIN_ID:
        await message.answer(
            "Admin panel: /admin",
            reply_markup=admin_kb()
        )
@dp.message(F.text == "💰 Balans")
async def user_balance(message: types.Message):

    user = await users_col.find_one({"user_id": message.from_user.id})

    text = (
        f"💰 Hisobingiz\n\n"
        f"Balans: {user['balance']} so'm\n"
        f"Botga kiritgan: {user['total_in']} so'm"
    )

    await message.answer(text)
@dp.message(F.text == "🛒 Xizmatlar")
async def user_services(message: types.Message):

    cats = await categories_col.find().to_list(None)

    if not cats:

        await message.answer("Hozircha xizmatlar yo'q")

        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for c in cats:

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=c["name"],
                callback_data=f"cat_{c['_id']}"
            )
        ])

    await message.answer("Bo'limni tanlang", reply_markup=kb)
@dp.callback_query(F.data.startswith("cat_"))
async def show_services(call: types.CallbackQuery):

    cat_id = call.data.split("_")[1]

    services = await services_col.find(
        {"category": cat_id}
    ).to_list(None)

    if not services:

        await call.answer("Bu bo'limda xizmat yo'q", show_alert=True)

        return

    kb = InlineKeyboardMarkup(inline_keyboard=[])

    for s in services:

        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text=f"{s['name']} - {s['price']} so'm",
                callback_data=f"buy_{s['_id']}"
            )
        ])

    await call.message.answer(
        "Xizmatni tanlang",
        reply_markup=kb
    )
@dp.callback_query(F.data.startswith("buy_"))
async def buy_service(call: types.CallbackQuery, state: FSMContext):

    s_id = call.data.split("_")[1]

    service = await services_col.find_one(
        {"_id": ObjectId(s_id)}
    )

    user = await users_col.find_one(
        {"user_id": call.from_user.id}
    )

    if user["balance"] < service["price"]:

        await call.answer("Balans yetarli emas", show_alert=True)

        return

    await state.update_data(
        service=service["name"],
        price=service["price"],
        s_id=s_id
    )

    await call.message.answer("Havola yuboring")

    await state.set_state(UserState.order_link)
@dp.message(UserState.order_link)
async def order_finish(message: types.Message, state: FSMContext):

    data = await state.get_data()

    await users_col.update_one(
        {"user_id": message.from_user.id},
        {"$inc": {"balance": -data["price"]}}
    )

    order = await orders_col.insert_one({
        "user_id": message.from_user.id,
        "service": data["service"],
        "link": message.text,
        "price": data["price"],
        "status": "pending"
    })

    await bot.send_message(
        ADMIN_ID,
        f"Yangi buyurtma\n\n"
        f"User: {message.from_user.full_name}\n"
        f"ID: {message.from_user.id}\n"
        f"Xizmat: {data['service']}\n"
        f"Havola: {message.text}\n"
        f"Summa: {data['price']}"
    )

    await message.answer("Buyurtma yuborildi")

    await state.clear()
async def handle(request):
    return web.Response(text="Bot ishlayapti")


async def start_web():

    app = web.Application()

    app.router.add_get("/", handle)

    runner = web.AppRunner(app)

    await runner.setup()

    site = web.TCPSite(
        runner,
        "0.0.0.0",
        int(os.environ.get("PORT", 8080))
    )

    await site.start()
async def main():

    asyncio.create_task(start_web())

    await bot.delete_webhook(drop_pending_updates=True)

    await dp.start_polling(bot)


if __name__ == "__main__":

    asyncio.run(main())
@dp.callback_query(F.data.startswith("ord_ok_"))
async def order_accept(call: types.CallbackQuery):

    order_id = call.data.split("_")[2]

    order = await orders_col.find_one({"_id": ObjectId(order_id)})

    await orders_col.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": "completed"}}
    )

    await bot.send_message(
        order["user_id"],
        f"✅ Buyurtmangiz bajarildi\n\nXizmat: {order['service']}"
    )

    await call.message.edit_text("Buyurtma bajarildi")
@dp.callback_query(F.data.startswith("ord_no_"))
async def order_cancel(call: types.CallbackQuery):

    order_id = call.data.split("_")[2]

    order = await orders_col.find_one({"_id": ObjectId(order_id)})

    await users_col.update_one(
        {"user_id": order["user_id"]},
        {"$inc": {"balance": order["price"]}}
    )

    await orders_col.update_one(
        {"_id": ObjectId(order_id)},
        {"$set": {"status": "canceled"}}
    )

    await bot.send_message(
        order["user_id"],
        "❌ Buyurtmangiz rad etildi\nPul balansingizga qaytarildi"
    )

    await call.message.edit_text("Buyurtma rad etildi")
@dp.message(F.text == "💳 Hisobni to'ldirish")
async def deposit_start(message: types.Message):

    cards = await settings_col.find({"type": "card"}).to_list(None)

    text = "To'lov uchun kartalar\n\n"

    for c in cards:

        text += f"{c['name']}\n{c['number']}\n\n"

    text += "Chek rasmini yuboring"

    await message.answer(text)
@dp.message(F.photo)
async def payment_photo(message: types.Message, state: FSMContext):

    await state.update_data(photo=message.photo[-1].file_id)

    await message.answer("To'lov summasini yozing")

    await state.set_state(UserState.pay_sum)
9@dp.message(UserState.pay_sum)
async def payment_sum(message: types.Message, state: FSMContext):

    data = await state.get_data()

    payment = await payments_col.insert_one({
        "user_id": message.from_user.id,
        "sum": int(message.text),
        "photo": data["photo"],
        "status": "pending"
    })

    kb = InlineKeyboardMarkup(
        inline_keyboard=[[
            InlineKeyboardButton(
                text="Tasdiqlash",
                callback_data=f"pay_ok_{payment.inserted_id}"
            )
        ]]
    )

    await bot.send_photo(
        ADMIN_ID,
        data["photo"],
        caption=f"To'lov\nUser: {message.from_user.id}\nSumma: {message.text}",
        reply_markup=kb
    )

    await message.answer("Chek adminga yuborildi")

    await state.clear()
@dp.callback_query(F.data.startswith("pay_ok_"))
async def payment_accept(call: types.CallbackQuery):

    pay_id = call.data.split("_")[2]

    pay = await payments_col.find_one({"_id": ObjectId(pay_id)})

    await users_col.update_one(
        {"user_id": pay["user_id"]},
        {
            "$inc": {
                "balance": pay["sum"],
                "total_in": pay["sum"]
            }
        }
    )

    await payments_col.update_one(
        {"_id": ObjectId(pay_id)},
        {"$set": {"status": "done"}}
    )

    await bot.send_message(
        pay["user_id"],
        f"💰 Hisobingiz {pay['sum']} so'mga to'ldirildi"
    )

    await call.message.edit_caption("To'lov tasdiqlandi")
@dp.message(F.text == "👤 Balans tahrirlash")
async def edit_balance_start(message: types.Message, state: FSMContext):

    await message.answer("User ID yuboring")

    await state.set_state(AdminState.edit_user_id)


@dp.message(AdminState.edit_user_id)
async def edit_balance_id(message: types.Message, state: FSMContext):

    await state.update_data(user_id=int(message.text))

    await message.answer("Qo'shiladigan yoki ayriladigan summa")

    await state.set_state(AdminState.edit_user_balance)


@dp.message(AdminState.edit_user_balance)
async def edit_balance_finish(message: types.Message, state: FSMContext):

    data = await state.get_data()

    await users_col.update_one(
        {"user_id": data["user_id"]},
        {"$inc": {"balance": int(message.text)}}
    )

    await message.answer("Balans o'zgartirildi")

    await state.clear()
@dp.message(F.text == "📢 Xabar yuborish")
async def broadcast_start(message: types.Message, state: FSMContext):

    await message.answer("Yuboriladigan xabarni yozing")

    await state.set_state(AdminState.broadcast_msg)


@dp.message(AdminState.broadcast_msg)
async def broadcast_send(message: types.Message, state: FSMContext):

    users = await users_col.find().to_list(None)

    for u in users:

        try:
            await bot.send_message(u["user_id"], message.text)
        except:
            pass

    await message.answer("Xabar yuborildi")

    await state.clear()
@dp.message(F.text == "🎁 Bonuslar")
async def daily_bonus(message: types.Message):

    user = await users_col.find_one({"user_id": message.from_user.id})

    today = datetime.now().strftime("%Y-%m-%d")

    if user.get("last_daily") == today:

        await message.answer("Bugungi bonusni oldingiz")

        return

    bonus = 1000

    await users_col.update_one(
        {"user_id": message.from_user.id},
        {
            "$inc": {"balance": bonus},
            "$set": {"last_daily": today}
        }
    )

    await message.answer(f"Siz {bonus} so'm bonus oldingiz")

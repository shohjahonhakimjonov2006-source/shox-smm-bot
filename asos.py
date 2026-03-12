import logging
import asyncio
import aiohttp
import motor.motor_asyncio
import os
import sys
from datetime import datetime

# AIOGRAM importlari (StatesGroup mana shu yerda bo'lishi shart)
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup  # <-- Mana shu qator xatoni tuzatadi
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton

# LOGLARNI SOZLASH
logging.basicConfig(level=logging.INFO, stream=sys.stdout)

# --- SOZLAMALAR ---
API_TOKEN = '8678413684:AAGTwgkxubtg47-eCSyhwZv2tQR0gvu0iHo'
ADMIN_ID = 7861165622
SMM_API_KEY = '00c9d8e11e3935fe8861533a792fd2fe'
SMM_API_URL = 'https://smmapi.safobuilder.uz/shox_smmbot/api/v2'

# --- MONGODB ---
MONGO_URL = "mongodb+srv://Zoirbek2003:Zoirbek2003@zoirbek2003.paka8jf.mongodb.net/?retryWrites=true&w=majority&appName=ZOirbek2003"
client = motor.motor_asyncio.AsyncIOMotorClient(MONGO_URL)
db = client.smm_pro_database
users_col = db.users
services_col = db.services
orders_col = db.orders

# --- HOLATLAR (STATES) ---
# Endi StatesGroup xatosi chiqmaydi
class OrderState(StatesGroup):
    entering_link = State()
    entering_quantity = State()

class AdminState(StatesGroup):
    waiting_for_user_id = State()
    waiting_for_amount = State()
    m_name = State()
    m_price = State()
    m_id = State()
    m_cat = State()

bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# ... qolgan kod qismlari (funksiyalar) shu yerdan davom etadi ...

from motor.motor_asyncio import AsyncIOMotorClient
from .config import MONGO_URL

client = AsyncIOMocli = AsyncIOMotorClient(MONGO_URL)
db = client["smm_ultra"]

users = db["users"]
orders = db["orders"]
services = db["services"]

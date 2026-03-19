import aiohttp
from .config import API_URL, API_KEY

async def create_order(service_id, link, qty):
    async with aiohttp.ClientSession() as session:
        data = {
            "key": API_KEY,
            "action": "add",
            "service": service_id,
            "link": link,
            "quantity": qty
        }
        async with session.post(API_URL, data=data) as r:
            return await r.json()

async def order_status(order_id):
    async with aiohttp.ClientSession() as session:
        data = {
            "key": API_KEY,
            "action": "status",
            "order": order_id
        }
        async with session.post(API_URL, data=data) as r:
            return await r.json()

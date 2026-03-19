from aiogram.fsm.state import State, StatesGroup

class OrderState(StatesGroup):
    link = State()
    qty = State()

class PayState(StatesGroup):
    amount = State()
    receipt = State()

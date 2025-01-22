from aiogram.fsm.state import State, StatesGroup

class Profile(StatesGroup):
    weight = State()
    height = State()
    activity_minutes = State()
    city = State()
    age = State()

class Food(StatesGroup):
    food_name = State()
    food_quantity = State()
    food_calories = State()

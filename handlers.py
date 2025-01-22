import json

from aiogram import Router
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
import aiohttp
from states import Profile, Food
from config import WEATHER_API_KEY

router = Router()

users = {}

workouts_calories = {
    "бег": 10,
    "велосипед": 30,
    "йога": 15,
    "танцы": 25,
    "теннис": 25,
    "плавание": 30,
    "кроссфит": 35
}

# Обработчик команды /start
@router.message(Command("start"))
async def cmd_start(message: Message):
    await message.reply("Добро пожаловать! Это бот для трекинга вашего здоровья.\nВведите /help для списка команд.")

# Обработчик команды /help
@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.reply(
        "Доступные команды:\n"
        "/start - Начало работы\n"
        "/set_profile - Настройка профиля\n"
        "/log_water - Логирование воды\n"
        "/log_food - Логирование еды\n"
        "/log_workout - Логирование тренировок\n"
        "/check_progress - Прогресс по воде и калориям"
    )

@router.message(Command("set_profile"))
async def start_form(message: Message, state: FSMContext):
    await message.reply("Введите ваш вес (в кг):")
    await state.set_state(Profile.weight)

@router.message(Profile.weight)
async def process_weight(message: Message, state: FSMContext):
    await state.update_data(weight=message.text)
    await message.reply("Введите ваш рост (в см):")
    await state.set_state(Profile.height)

@router.message(Profile.height)
async def process_height(message: Message, state: FSMContext):
    await state.update_data(height=message.text)
    await message.reply("Сколько вам лет?")
    await state.set_state(Profile.age)

@router.message(Profile.age)
async def process_age(message: Message, state: FSMContext):
    await state.update_data(age=message.text)
    await message.reply("Сколько минут активности у вас в день?")
    await state.set_state(Profile.activity_minutes)

@router.message(Profile.activity_minutes)
async def process_activity_minutes(message: Message, state: FSMContext):
    await state.update_data(activity_minutes=message.text)
    await message.reply("В каком городе вы находитесь?")
    await state.set_state(Profile.city)

async def get_temperature(session, city, api_key):
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={api_key}&units=metric"
    async with session.get(url) as response:
        data = await response.json()
        if data['cod'] == 200:
            return data['main']['temp']
        else:
            raise ValueError(str(data))

@router.message(Profile.city)
async def process_city(message: Message, state: FSMContext):
    await state.update_data(city=message.text)
    data = await state.get_data()
    weight = int(data.get("weight"))
    height = int(data.get("height"))
    activity_minutes = int(data.get("activity_minutes"))
    age = int(data.get("age"))
    city = data.get("city")
    water_goal = weight * 30
    
    async with aiohttp.ClientSession() as session:
        try:
            current_temperature = await get_temperature(session, city, WEATHER_API_KEY)
            if current_temperature > 25:
                water_goal += 500
        except Exception as e:
            print("Ошибка при получении температуры", e)
            await message.reply(f"Ошибка при получении температуры, норма подсчитана без учета температуры")
    water_goal += 500 * (activity_minutes // 30)
    calories_goal = weight * 10 + height * 6.25 + age * 5

    users[message.from_user.id] = {
        "weight": weight,
        "height": height,
        "age": age,
        "activity_minutes": activity_minutes,
        "city": city,
        "calories_goal": calories_goal,
        "water_goal": water_goal
    }
    await message.reply(f"Ваш профиль:\n"
                        f"Вес: {weight} кг\n"
                        f"Рост: {height} см\n"
                        f"Возраст: {age} лет\n"
                        f"Активность: {activity_minutes} минут\n"
                        f"Город: {city}\n"
                        f"Целевой уровень калорий: {calories_goal:.0f} ккал\n"
                        f"Целевое потребление воды: {water_goal:.0f} мл")
    await state.clear()

@router.message(Command("log_water"))
async def log_water(message: Message):
    try:
        amount = float(message.text.split()[1])
        if message.from_user.id not in users:
            await message.reply("Пользователь не найден, настройте профиль с помощью команды /set_profile")
            return
        if "logged_water" not in users[message.from_user.id]:
            users[message.from_user.id]["logged_water"] = 0
        users[message.from_user.id]["logged_water"] += amount
        water_remained = users[message.from_user.id]["water_goal"] - users[message.from_user.id]["logged_water"]
        message_text = f"Записано потребление воды: {amount:.0f} мл\n"  
        if water_remained > 0:
            message_text += f"Осталось воды: {water_remained:.0f} мл"
        else:
            message_text += f"Вы достигли целевого уровня потребления воды"
        await message.reply(message_text)
    except (IndexError, ValueError):
        await message.reply("Пожалуйста, укажите количество воды в литрах после команды.\nНапример: /log_water 200")

async def get_food_calories(session, product_name):
    url = f"https://world.openfoodfacts.org/cgi/search.pl?action=process&search_terms={product_name}&json=true"
    async with session.get(url) as response:
        data = await response.json()
        products = data.get('products', [])
        if products:
            first_product = products[0]
            return first_product.get('nutriments', {}).get('energy-kcal_100g', 0)
        return None

@router.message(Command("log_food"))
async def log_food(message: Message, state: FSMContext):
    try:
        food_name = message.text.split()[1]
        if message.from_user.id not in users:
            await message.reply("Пользователь не найден, настройте профиль с помощью команды /set_profile")
            return
        await state.update_data(food_name=food_name)
        
        async with aiohttp.ClientSession() as session:
            food_calories = await get_food_calories(session, food_name)
            if food_calories is not None and food_calories > 0:
                await state.update_data(food_calories=food_calories)
                await message.reply(f"{food_name} - {food_calories} ккал на 100 г. Сколько грамм вы съели?")
                await state.set_state(Food.food_quantity)
            else:
                await message.reply("Продукт не найден, попробуйте другое название")
    except (IndexError, ValueError):
        await message.reply("Пожалуйста, укажите название продукта после команды.\nНапример: /log_food яблоко")

@router.message(Food.food_quantity)
async def process_food_quantity(message: Message, state: FSMContext):
    try:
        food_quantity = float(message.text)
        if food_quantity <= 0:
            await message.reply("Количество продукта должно быть больше 0")
            return
        await state.update_data(food_quantity=food_quantity)
        data = await state.get_data()
        food_name = data.get("food_name")
        food_quantity = data.get("food_quantity")
        food_calories = data.get("food_calories")
        total_calories = food_calories * food_quantity / 100
        if message.from_user.id not in users:
            await message.reply("Пользователь не найден, настройте профиль с помощью команды /set_profile")
            return
        if "logged_food" not in users[message.from_user.id]:
            users[message.from_user.id]["logged_food"] = 0
        users[message.from_user.id]["logged_food"] += total_calories

        await message.reply(f"Записано: {total_calories:.0f} ккал")
        await state.clear()
    except ValueError:
        await message.reply("Пожалуйста, введите числовое значение количества продукта в граммах.")

@router.message(Command("log_workout"))
async def log_workout(message: Message):
    workout_args = message.text.split()[1:]
    if len(workout_args) != 2:
        await message.reply("Пожалуйста, укажите название упражнения и количество минут после команды.\nНапример: /log_workout бег 30")
        return
    workout_name = workout_args[0].lower()
    workout_minutes = int(workout_args[1])
    if workout_name not in workouts_calories:
        await message.reply("Упражнение не найдено, попробуйте другое название")
        return
    calories_burned = workouts_calories[workout_name] * workout_minutes
    if message.from_user.id not in users:
        await message.reply("Пользователь не найден, настройте профиль с помощью команды /set_profile")
        return
    if "burned_calories" not in users[message.from_user.id]:
        users[message.from_user.id]["burned_calories"] = 0
    users[message.from_user.id]["burned_calories"] += calories_burned
    additional_water = 200 * (workout_minutes // 30)
    message_text = f"{workout_name} {workout_minutes} минут - {calories_burned:.0f} ккал."
    if additional_water > 0:
        message_text += f" Дополнительно: выпейте {additional_water:.0f} мл воды"
    await message.reply(message_text)

@router.message(Command("check_progress"))
async def check_progress(message: Message):
    if message.from_user.id not in users:
        await message.reply("Пользователь не найден, настройте профиль с помощью команды /set_profile")
        return

    user_data = users[message.from_user.id]
    water_consumed = user_data.get("logged_water", 0)
    water_goal = user_data.get("water_goal", 0)
    water_remaining = max(0, water_goal - water_consumed)

    calories_consumed = user_data.get("logged_food", 0)
    calories_goal = user_data.get("calories_goal", 0)
    calories_burned = user_data.get("burned_calories", 0)
    calories_balance = calories_consumed - calories_burned

    progress_message = (
        "Прогресс:\n\n"
        f"Вода:\n"
        f"- Выпито: {water_consumed:.0f} мл из {water_goal:.0f} мл.\n"
        f"- Осталось: {water_remaining:.0f} мл.\n\n"
        f"Калории:\n"
        f"- Потреблено: {calories_consumed:.0f} ккал из {calories_goal:.0f} ккал.\n"
        f"- Сожжено: {calories_burned:.0f} ккал.\n"
        f"- Баланс: {calories_balance:.0f} ккал."
    )

    await message.reply(progress_message)

def setup_handlers(dp):
    dp.include_router(router)

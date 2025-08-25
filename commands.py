from aiogram.filters import Command
from aiogram import types
from config import dp, cursor, conn
from keyboard import main_keyboard


# Команда /start
@dp.message(Command("start"))
async def start_command(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    full_name = message.from_user.full_name

    # Проверяем есть ли пользователь в базе
    cursor.execute("SELECT * FROM subscriptions WHERE user_id = ?", (user_id,))
    user = cursor.fetchone()

    if not user:
        # Добавляем нового пользователя
        cursor.execute(
            "INSERT INTO subscriptions (user_id, username, full_name) VALUES (?, ?, ?)",
            (user_id, username, full_name)
        )
        conn.commit()

    await message.answer(
        "👋 Добро пожаловать!.\n\n"
        "💰Участи в информационном канале по стоматологии - 8 000 руб в месяц, для стуентов и ординаторов - 5000 руб в месяц",
        reply_markup=main_keyboard()
    )

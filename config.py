import sqlite3
from aiogram import Bot, Dispatcher
from yookassa import Configuration
import os
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Конфигурация бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
ADMIN_ID = os.getenv("ADMIN_ID", "@vladimir_potyaev")  # ID администратора для уведомлений
SUBSCRIPTION_PRICE = 299.00  # Цена подписки в рублях

# Настройка YooKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY


# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()



# Подключение к базе данных
conn = sqlite3.connect('subscriptions.db')
cursor = conn.cursor()


# Создание таблицы для подписок
cursor.execute('''
CREATE TABLE IF NOT EXISTS subscriptions (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    full_name TEXT,
    payment_id TEXT, 
    start_date TEXT,
    end_date TEXT,
    status TEXT DEFAULT 'inactive'
)
''')
conn.commit()


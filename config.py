from aiogram import Bot, Dispatcher
from yookassa import Configuration
import os
from dotenv import load_dotenv

load_dotenv()

# Конфигурация бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
ADMIN_ID = os.getenv("ADMIN_ID", "@vladimir_potyaev")  # ID администратора для уведомлений
SUBSCRIPTION_PRICE = (5000, 8000)  # Цена подписки в рублях
# база
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

# Настройка YooKassa
Configuration.account_id = YOOKASSA_SHOP_ID
Configuration.secret_key = YOOKASSA_SECRET_KEY

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL подключения для asyncpg
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

from aiogram import Bot, Dispatcher
from yookassa import Configuration
import os
from dotenv import load_dotenv

load_dotenv()

SUBSCRIPTION_PRICE = (5000.00, 8000.00, 100.00)

# Конфигурация бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_WEBHOOK_URL = os.getenv('YOOKASSA_WEBHOOK_URL', 'https://yourdomain.com/yookassa-webhook')

# база
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")

URL = "https://t.me/+Etm_DDqjYI81OGVi"
USERNAME_CHANNEL = '-1003210745015'
ADMIN_IDS = [384110333, 987654321, 555666777]

# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL подключения для asyncpg
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

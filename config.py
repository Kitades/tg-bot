from aiogram import Bot, Dispatcher
import os
from dotenv import load_dotenv

load_dotenv()

SUBSCRIPTION_PRICE = (2.00, 8900.00)
ADMIN_IDS = [91211500, 384110333]
# ADMIN_IDS = [384110333]

# Конфигурация бота
BOT_TOKEN = os.getenv("BOT_TOKEN")
YOOKASSA_SHOP_ID = os.getenv("YOOKASSA_SHOP_ID")
YOOKASSA_SECRET_KEY = os.getenv("YOOKASSA_SECRET_KEY")
YOOKASSA_WEBHOOK_URL = os.getenv('YOOKASSA_WEBHOOK_URL')

# база
DB_HOST = os.getenv("DB_HOST")
DB_PORT = os.getenv("DB_PORT")
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")


WEBHOOK_URL = os.getenv("WEBHOOK_URL")
WEBAPP_HOST = os.getenv("WEBAPP_HOST")
WEBAPP_PORT = int(os.getenv("WEBAPP_PORT"))

URL = os.getenv("URL")
USERNAME_CHANNEL = os.getenv("USERNAME_CHANNEL")
RETURN_URL = os.getenv("RETURN_URL")
URL_BOT = os.getenv("URL_BOT")

# URL = "https://t.me/+P8gqDEd-zENlZTYy"
# USERNAME_CHANNEL = '-1002908820618'


# Инициализация бота и диспетчера
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# URL подключения для asyncpg
DATABASE_URL = f"postgresql+asyncpg://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"
DATABASE_URL_SYNC = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/{DB_NAME}"

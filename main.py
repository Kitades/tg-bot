import asyncio
import logging

from checksub import check_subscriptions, send_daily_report
from commands import router
from config import dp, bot
from database.session import create_tables, check_connection

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main():
    await check_connection()
    await create_tables()
    dp.include_router(router)

    asyncio.create_task(check_subscriptions())
    asyncio.create_task(send_daily_report())

    print("✅ Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

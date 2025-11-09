import asyncio
from checksub import check_subscriptions, send_daily_report
from commands import router
from config import dp, bot
from database.session import create_tables, check_connection
from servises.free_scheduler import FreePostScheduler


async def main():
    await check_connection()
    await create_tables()
    dp.include_router(router)

    free_scheduler = FreePostScheduler(bot)

    asyncio.create_task(check_subscriptions())
    asyncio.create_task(send_daily_report())
    asyncio.create_task(free_scheduler.start_free_posting())

    print("✅ Бот запущен")
    try:
        await dp.start_polling(bot)
    finally:
        free_scheduler.stop()
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())

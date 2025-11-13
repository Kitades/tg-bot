import asyncio

from aiogram.webhook.aiohttp_server import setup_application
from aiohttp import web

from checksub import check_subscriptions, send_daily_report
from commands import router
from config import dp, bot, WEBAPP_HOST, WEBAPP_PORT

from log.logger import get_logger
from log.logging_config import setup_logging
from payment.webhook_handler import webhook_handler
from servises.free_scheduler import FreePostScheduler

setup_logging()
logger = get_logger(__name__)


async def main():
    try:
        logger.info("Запуск бота с автоплатежами...")

        # await check_connection()
        # await create_tables()

        dp.include_router(router)
        logger.info("Роутеры подключены")
        app = web.Application()


        app.router.add_post('/yookassa_webhook', webhook_handler.handle_webhook)
        logger.info("Вебхук для ЮКассы настроен")

        setup_application(app, dp, bot=bot)
        logger.info(f"Сервер запущен на {WEBAPP_HOST}:{WEBAPP_PORT}")

        await web._run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)

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
    except Exception as e:
        print(f"{e}")


if __name__ == "__main__":
    asyncio.run(main())

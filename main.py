import asyncio
import logging

from aiogram.webhook.aiohttp_server import setup_application
from aiohttp import web

from checksub import check_subscriptions, send_daily_report
from commands import router
from config import dp, bot, WEBAPP_HOST, WEBAPP_PORT, WEBHOOK_URL

from log.logger import get_logger
from log.logging_config import setup_logging
from payment.webhook_handler import webhook_handler
from servises.free_scheduler import FreePostScheduler

setup_logging()
logger = get_logger(__name__)


async def main():
    try:
        logger.info("Запуск гибридного бота (web-сервер + polling)...")

        # Подключаем роутеры
        dp.include_router(router)
        logger.info("Роутеры подключены")

        # Создаем web-приложение для вебхуков ЮКассы
        app = web.Application()
        app.router.add_post('/yookassa_webhook', webhook_handler.handle_webhook)
        app.router.add_get('/yookassa_webhook', webhook_handler.handle_webhook_test)
        logger.info("Вебхук для ЮКассы настроен")

        # Добавляем health-check
        async def health_check(request):
            return web.json_response({"status": "ok", "service": "yookassa-bot"})

        app.router.add_get('/health', health_check)
        app.router.add_get('/status', health_check)

        # Инициализируем планировщики
        free_scheduler = FreePostScheduler(bot)

        # Запускаем фоновые задачи
        asyncio.create_task(check_subscriptions())
        asyncio.create_task(send_daily_report())
        asyncio.create_task(free_scheduler.start_free_posting())

        # Запускаем web-сервер в фоне
        async def run_web_server():
            runner = web.AppRunner(app)
            await runner.setup()
            site = web.TCPSite(runner, WEBAPP_HOST, WEBAPP_PORT)
            await site.start()
            logger.info(f"Web-сервер запущен на {WEBAPP_HOST}:{WEBAPP_PORT}")

        asyncio.create_task(run_web_server())

        logger.info("Бот запущен в режиме polling + web-сервер")
        logger.info(f"Вебхук URL: {WEBHOOK_URL}")

        # Запускаем polling (основной поток)
        await dp.start_polling(bot)

    except Exception as e:
        logger.error(f"❌ Критическая ошибка: {e}", exc_info=True)
        raise
    finally:
        # Корректное завершение
        if 'free_scheduler' in locals():
            free_scheduler.stop()
        await bot.session.close()


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    asyncio.run(main())

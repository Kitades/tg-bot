import logging
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler

from sqlalchemy import select, text
from sqlalchemy.orm import joinedload
import asyncio

from config import ADMIN_IDS, USERNAME_CHANNEL
from database.models import Subscription, User
from database.session import AsyncSessionLocal
from config import bot
from helpers import notify_admins, get_admin_ids
from log.logger import get_logger
from log.logging_config import setup_logging
from servises.telegram_service import TelegramService

setup_logging()
logger = get_logger(__name__)

background_logger = logging.getLogger('background_tasks')
background_logger.setLevel(logging.INFO)

# Логи в файл
file_handler = RotatingFileHandler(
    'logs/background.log',
    maxBytes=10 * 1024 * 1024,
    backupCount=3,
    encoding='utf-8'
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
))
background_logger.addHandler(file_handler)


async def check_subscriptions():
    logger = logging.getLogger('background_tasks')
    logger.info("Запуск проверки подписок...")
    """Проверка и деактивация просроченных подписок"""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                # 1. Проверка подключения к базе
                result = await session.execute(text("SELECT 1"))
                print(f"✅ Проверка базы: {result.scalar()}")

                # 2. Деактивация просроченных подписок
                current_time = datetime.utcnow()
                expired_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date <= current_time)
                )
                expired_subscriptions = expired_result.scalars().all()

                for subscription in expired_subscriptions:
                    user_result = await session.execute(
                        select(User).where(User.id == subscription.user_id)
                    )
                    user = user_result.scalar_one_or_none()
                    if user:
                        try:
                            await bot.send_message(
                                user.telegram_id,
                                "❌ <b>Ваша подписка закончилась</b>\n\n"
                                "Доступ к эксклюзивному контенту приостановлен.\n"
                                "Для возобновления доступа приобретите новую подписку.",
                                parse_mode='HTML'
                            )
                            logger.info(f"📧 Уведомление отправлено пользователю {user.telegram_id}")
                        except Exception as e:
                            logger.error(f"❌ Ошибка отправки уведомления: {e}")

                    subscription.status = 'expired'
                    subscription.updated_at = datetime.utcnow()

                    try:
                        success = await TelegramService.remove_user_from_channel(
                            bot, user.telegram_id, USERNAME_CHANNEL)

                    except Exception as e:
                        logger.error(f"{e}")
                        success = False
                        await TelegramService.unban_from_channel(bot, user.telegram_id, USERNAME_CHANNEL)
                    if success:
                        logger.info(f"🔴 Подписка {subscription.id} деактивирована (просрочена)")
                    else:
                        logger.info(f"🔴 У {user.telegram_id} , не удалось удалить подписку")

                    # Получаем пользователя для отправки уведомления

                # Коммитим изменения в базе
                if expired_subscriptions:
                    await session.commit()
                    logger.info(f"✅ Деактивировано {len(expired_subscriptions)} подписок")

        except Exception as e:
            logger.error(f"Ошибка в check_subscriptions: {e}")

        await asyncio.sleep(24 * 3600)  # Проверяем каждый день


async def send_daily_report():
    """Ежедневный отчет по подпискам"""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                current_time = datetime.utcnow()

                active_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date > current_time)
                )
                active_subscriptions = active_result.scalars().all()
                active_count = len(active_subscriptions)

                expiring_result = await session.execute(
                    select(Subscription)
                    .options(joinedload(Subscription.user))
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date <= current_time + timedelta(days=1))
                    .where(Subscription.end_date > current_time)
                )
                expiring_subscriptions = expiring_result.scalars().all()

                data = []
                for subscription in expiring_subscriptions:
                    if subscription.user:  # Проверяем, что пользователь загружен
                        telegram_id = subscription.user.telegram_id
                        username = subscription.user.username
                        data.append(f"У пользователя {username} c id {telegram_id} заканчивается подписка")

                if get_admin_ids():
                    report_text = (
                        f"📊 <b>Ежедневный отчет по подпискам</b>\n\n"
                        f"📅 Дата: {current_time.strftime('%d.%m.%Y %H:%M')}\n"
                        f"✅ Активных подписок: {active_count}\n"
                        f"⚠️ Истекает в течение 1 дня: {data}\n"
                    )

                    success_count, fail_count = await notify_admins(bot, report_text, parse_mode='HTML')
                    logger.info(f"📊 Отчет отправлен: {success_count} успешно, {fail_count} с ошибкой")

        except Exception as e:
            logger.error(f"❌ Ошибка в send_daily_report: {e}")

        await asyncio.sleep(24 * 3600)


async def check_expiring_subscriptions():
    """Проверка подписок, которые скоро истекут (за 1-2 дня)"""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                current_time = datetime.utcnow()

                expiring_soon_result = await session.execute(
                    select(Subscription)
                    .join(User, Subscription.user_id == User.id)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date <= current_time + timedelta(days=2))
                    .where(Subscription.end_date > current_time + timedelta(days=1))
                )
                expiring_soon_subs = expiring_soon_result.scalars().all()

                for subscription in expiring_soon_subs:
                    try:
                        await bot.send_message(
                            subscription.user.telegram_id,
                            "⚠️ <b>Ваша подписка скоро закончится!</b>\n\n"
                            f"📅 Окончание: {subscription.end_date.strftime('%d.%m.%Y')}\n"
                            f"⏳ Осталось: {(subscription.end_date - current_time).days} дней\n\n"
                            "Не забудьте продлить подписку для непрерывного доступа к контенту.",
                            parse_mode='HTML'
                        )
                        print(f"📧 Напоминание отправлено пользователю {subscription.user.telegram_id}")
                    except Exception as e:
                        print(f"❌ Ошибка отправки напоминания: {e}")

        except Exception as e:
            print(f"❌ Ошибка в check_expiring_subscriptions: {e}")

        await asyncio.sleep(12 * 3600)


async def start_background_tasks():
    """Запуск всех фоновых задач"""
    asyncio.create_task(check_subscriptions())
    asyncio.create_task(send_daily_report())
    asyncio.create_task(check_expiring_subscriptions())
    print("✅ Фоновые задачи запущены")

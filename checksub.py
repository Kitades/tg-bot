from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.sql.functions import current_time

from config import bot, ADMIN_ID
from database.models import Subscription
from database.session import AsyncSessionLocal, get_db_session
import asyncio


async def check_subscriptions():
    """Упрощенная проверка подписок"""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Простая проверка что база работает
                result = await session.execute(text("SELECT 1"))
                print(f"✅ Проверка базы: {result.scalar()}")

        except Exception as e:
            print(f"❌ Ошибка подключения к базе: {e}")

            # 2. Деактивация просроченных подписок надо доработать
            expired_result = await session.execute(
                select(Subscription)
                .where(Subscription.status == 'active')
                .where(Subscription.end_date <= current_time)
            )
            expired_subscriptions = expired_result.scalars().all()

            for subscription in expired_subscriptions:
                subscription.status = 'expired'
                subscription.updated_at = datetime.utcnow()
                print(f"🔴 Подписка {subscription.id} деактивирована (просрочена)")

                # Отправляем уведомление о окончании подписки
                try:
                    await bot.send_message(
                        subscription.user.telegram_id,
                        "❌ <b>Ваша подписка закончилась</b>\n\n"
                        "Доступ к эксклюзивному контенту приостановлен.\n"
                        "Для возобновления доступа приобретите новую подписку.",
                        parse_mode='HTML'
                    )
                except Exception as e:
                    print(f"❌ Ошибка отправки уведомления об окончании: {e}")

        await asyncio.sleep(24 * 3600)  # Проверяем каждый день


async def send_daily_report():
    """Упрощенный ежедневный отчет"""
    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Просто проверяем что база доступна
                result = await session.execute(text("SELECT COUNT(*) FROM information_schema.tables"))
                table_count = result.scalar()
                print(f"📊 В базе {table_count} таблиц")

        except Exception as e:
            print(f"❌ Ошибка отчета: {e}")

        await asyncio.sleep(24 * 3600)  # Раз в день


async def send_daily_report():
    """Ежедневный отчет по подпискам"""
    while True:
        try:
            async with get_db_session() as session:
                current_time = datetime.utcnow()

                # Статистика активных подписок
                active_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date > current_time)
                )
                active_count = len(active_result.scalars().all())

                # Статистика истекающих подписок
                expiring_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date <= current_time + timedelta(days=3))
                    .where(Subscription.end_date > current_time)
                )
                expiring_count = len(expiring_result.scalars().all())

                # Отправляем отчет админу
                if ADMIN_ID:
                    report_text = (
                        f"📊 <b>Ежедневный отчет по подпискам</b>\n\n"
                        f"📅 Дата: {current_time.strftime('%d.%m.%Y')}\n"
                        f"✅ Активных подписок: {active_count}\n"
                        f"⚠️ Истекает в течение 3 дней: {expiring_count}\n"
                        f"🔄 Автопродление: {len([s for s in expiring_result.scalars().all() if s.auto_renew])}"
                    )

                    try:
                        await bot.send_message(ADMIN_ID, report_text, parse_mode='HTML')
                        print("📊 Отчет отправлен администратору")
                    except Exception as e:
                        print(f"❌ Ошибка отправки отчета: {e}")

        except Exception as e:
            print(f"❌ Ошибка в send_daily_report: {e}")

        await asyncio.sleep(24 * 3600)


async def start_background_tasks():
    """Запуск всех фоновых задач"""
    asyncio.create_task(check_subscriptions())
    asyncio.create_task(send_daily_report())
    print("✅ Фоновые задачи запущены")

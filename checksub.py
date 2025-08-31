from datetime import datetime, timedelta
from sqlalchemy import select, text
from sqlalchemy.sql import func
import asyncio

from config import ADMIN_ID
from database.models import Subscription, User
from database.session import AsyncSessionLocal, get_db_session
from config import bot  # Или правильный импорт вашего бота


async def check_subscriptions():
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
                    subscription.status = 'expired'
                    subscription.updated_at = datetime.utcnow()
                    print(f"🔴 Подписка {subscription.id} деактивирована (просрочена)")

                    # Получаем пользователя для отправки уведомления
                    user_result = await session.execute(
                        select(User).where(User.id == subscription.user_id)
                    )
                    user = user_result.scalar_one_or_none()

                    if user:
                        # Отправляем уведомление о окончании подписки
                        try:
                            await bot.send_message(
                                user.telegram_id,  # Используем telegram_id вместо user.id
                                "❌ <b>Ваша подписка закончилась</b>\n\n"
                                "Доступ к эксклюзивному контенту приостановлен.\n"
                                "Для возобновления доступа приобретите новую подписку.",
                                parse_mode='HTML'
                            )
                            print(f"📧 Уведомление отправлено пользователю {user.telegram_id}")
                        except Exception as e:
                            print(f"❌ Ошибка отправки уведомления: {e}")

                # Коммитим изменения в базе
                if expired_subscriptions:
                    await session.commit()
                    print(f"✅ Деактивировано {len(expired_subscriptions)} подписок")

        except Exception as e:
            print(f"❌ Ошибка в check_subscriptions: {e}")

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
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date <= current_time + timedelta(days=3))
                    .where(Subscription.end_date > current_time)
                )
                expiring_subscriptions = expiring_result.scalars().all()
                expiring_count = len(expiring_subscriptions)

                auto_renew_count = 0
                for sub in expiring_subscriptions:
                    if hasattr(sub, 'auto_renew') and sub.auto_renew:
                        auto_renew_count += 1

                if ADMIN_ID:
                    report_text = (
                        f"📊 <b>Ежедневный отчет по подпискам</b>\n\n"
                        f"📅 Дата: {current_time.strftime('%d.%m.%Y %H:%M')}\n"
                        f"✅ Активных подписок: {active_count}\n"
                        f"⚠️ Истекает в течение 3 дней: {expiring_count}\n"
                        f"🔄 Автопродление: {auto_renew_count}"
                    )

                    try:
                        await bot.send_message(ADMIN_ID, report_text, parse_mode='HTML')
                        print("📊 Отчет отправлен администратору")
                    except Exception as e:
                        print(f"❌ Ошибка отправки отчета: {e}")

        except Exception as e:
            print(f"❌ Ошибка в send_daily_report: {e}")

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
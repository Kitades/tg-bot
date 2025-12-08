import asyncio
import logging
from datetime import datetime, timedelta

from aiogram.types import Message
from aiogram.filters import Command
from aiogram import Router
from sqlalchemy import select, desc

from database.models import User, Subscription, InviteLink
from database.session import get_db_session

from helpers import is_admin

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = Router()


@router.message(Command("all_subscriptions"))
async def show_all_subscriptions(message: Message):
    """Показывает все платные подписки (только для администраторов)"""
    user_id = message.from_user.id

    # Проверка прав администратора
    if not is_admin(user_id):
        logger.warning(f"Пользователь {user_id} попытался получить доступ к админ-команде")
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        async with get_db_session() as session:
            # Получаем все подписки с информацией о пользователях
            # JOIN с таблицей пользователей для получения telegram_id
            query = select(
                User.telegram_id,
                User.username,
                Subscription.plan_type,
                Subscription.plan_name,
                Subscription.start_date,
                Subscription.end_date,
                Subscription.status,
                Subscription.payment_status,
                Subscription.payment_id,
                Subscription.created_at,
                Subscription.updated_at
            ).join(
                User, User.id == Subscription.user_id
            ).order_by(
                desc(Subscription.created_at)  # Сначала новые
            )

            result = await session.execute(query)
            subscriptions = result.fetchall()

            if not subscriptions:
                await message.answer("📭 Нет оформленных подписок.")
                return

            # Разбиваем вывод на части (Telegram ограничение на длину сообщения)
            subscriptions_per_message = 10  # По 10 подписок в одном сообщении

            for i in range(0, len(subscriptions), subscriptions_per_message):
                batch = subscriptions[i:i + subscriptions_per_message]

                message_text = f"📋 <b>Все подписки (часть {i // subscriptions_per_message + 1})</b>\n\n"

                for idx, sub in enumerate(batch, 1):
                    telegram_id, username, plan_type, plan_name, start_date, end_date, status, payment_status, payment_id, created_at, updated_at = sub

                    # Форматируем даты
                    start_str = start_date.strftime("%d.%m.%Y") if start_date else "Не указана"
                    end_str = end_date.strftime("%d.%m.%Y") if end_date else "Не указана"
                    created_str = created_at.strftime("%d.%m.%Y %H:%M") if created_at else ""
                    updated_str = updated_at.strftime("%d.%m.%Y %H:%M") if updated_at else ""

                    # Статус подписки с эмодзи
                    status_emoji = {
                        'active': '✅',
                        'pending': '🟡',
                        'canceled': '❌',
                        'expired': '⏳'
                    }.get(status, '❓')

                    # Статус платежа с эмодзи
                    payment_emoji = {
                        'completed': '💳',
                        'pending': '⏳',
                        'failed': '❌',
                        'refunded': '↩️'
                    }.get(payment_status, '❓')

                    message_text += (
                        f"<b>{i + idx}. Пользователь @{username or 'нет username'}</b>\n"
                        f"   👤 Telegram ID: <code>{telegram_id}</code>\n"
                        f"   📋 Тип: <code>{plan_type}</code>\n"
                        f"   📝 Название: <b>{plan_name}</b>\n"
                        f"   📅 Начало: <code>{start_str}</code>\n"
                        f"   📅 Окончание: <code>{end_str}</code>\n"
                        f"   📊 Статус: {status_emoji} <code>{status}</code>\n"
                        f"   💰 Платеж: {payment_emoji} <code>{payment_status}</code>\n"
                        f"   📝 ID платежа: <code>{payment_id or 'нет'}</code>\n"
                        f"   🕐 Создана: <code>{created_str}</code>\n"
                        f"   🔄 Обновлена: <code>{updated_str}</code>\n\n"
                    )

                # Добавляем статистику
                message_text += f"<i>Всего подписок: {len(subscriptions)}</i>\n"
                message_text += f"<i>Активных: {sum(1 for s in subscriptions if s[5] == 'active')}</i>\n"
                message_text += f"<i>Ожидающих оплаты: {sum(1 for s in subscriptions if s[5] == 'pending')}</i>"

                await message.answer(message_text, parse_mode="HTML")

                # Пауза между сообщениями, чтобы не спамить
                if i + subscriptions_per_message < len(subscriptions):
                    await asyncio.sleep(0.5)

            logger.info(f"Админ {user_id} запросил список всех подписок. Выведено {len(subscriptions)} записей.")

    except Exception as e:
        logger.error(f"Ошибка при получении списка подписок: {str(e)}", exc_info=True)
        await message.answer("❌ Произошла ошибка при получении списка подписок.")


@router.message(Command("active_subscriptions"))
async def show_active_subscriptions(message: Message):
    """Показывает только активные подписки (только для администраторов)"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        async with get_db_session() as session:
            query = select(
                User.telegram_id,
                User.username,
                Subscription.plan_type,
                Subscription.plan_name,
                Subscription.start_date,
                Subscription.end_date,
                Subscription.status,
                Subscription.payment_status,
                Subscription.payment_id
            ).join(
                User, User.id == Subscription.user_id
            ).where(
                Subscription.status == 'active'
            ).order_by(
                desc(Subscription.created_at)
            )

            result = await session.execute(query)
            subscriptions = result.fetchall()

            if not subscriptions:
                await message.answer("📭 Нет активных подписок.")
                return

            message_text = "✅ <b>Активные подписки</b>\n\n"

            for idx, sub in enumerate(subscriptions, 1):
                telegram_id, username, plan_type, plan_name, start_date, end_date, status, payment_status, payment_id = sub

                start_str = start_date.strftime("%d.%m.%Y") if start_date else "Не указана"
                end_str = end_date.strftime("%d.%m.%Y") if end_date else "Не указана"

                # Рассчитываем сколько дней осталось
                days_left = "?"
                if end_date:
                    days_left = (end_date - datetime.utcnow()).days
                    days_left = str(days_left) if days_left > 0 else "0"

                message_text += (

                    f"<b>{idx}. Пользователь @{username or 'нет username'}</b>\n"
                    f"      id: {telegram_id}            "
                    f"   📋 Тип: <code>{plan_type}</code>\n"
                    f"   📝 Название: <b>{plan_name}</b>\n"
                    f"   📅 Начало: <code>{start_str}</code>\n"
                    f"   📅 Окончание: <code>{end_str}</code>\n"
                    f"   ⏳ Осталось дней: <code>{days_left}</code>\n"
                    f"   💳 Платеж: <code>{payment_status}</code>\n\n"
                )

            message_text += f"<i>Всего активных подписок: {len(subscriptions)}</i>"

            await message.answer(message_text, parse_mode="HTML")
            logger.info(f"Админ {user_id} запросил список активных подписок.")

    except Exception as e:
        logger.error(f"Ошибка при получении активных подписок: {str(e)}", exc_info=True)
        await message.answer("❌ Произошла ошибка при получении активных подписок.")


@router.message(Command("subscription_stats"))
async def show_subscription_stats(message: Message):
    """Показывает статистику по подпискам (только для администраторов)"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    try:
        async with get_db_session() as session:
            # Общая статистика
            total_query = select(Subscription)
            total_result = await session.execute(total_query)
            total_subs = total_result.fetchall()

            # Статистика по статусам
            status_stats = {}
            payment_stats = {}
            plan_type_stats = {}

            # Подсчитываем статистику
            for sub in total_subs:
                subscription = sub[0]  # Извлекаем объект Subscription

                # Статистика по статусам
                status_stats[subscription.status] = status_stats.get(subscription.status, 0) + 1

                # Статистика по платежам
                payment_stats[subscription.payment_status] = payment_stats.get(subscription.payment_status, 0) + 1

                # Статистика по типам планов
                plan_type_stats[subscription.plan_type] = plan_type_stats.get(subscription.plan_type, 0) + 1

            # Подписки за последние 30 дней
            month_ago = datetime.utcnow() - timedelta(days=30)
            recent_query = select(Subscription).where(Subscription.created_at >= month_ago)
            recent_result = await session.execute(recent_query)
            recent_subs = len(recent_result.fetchall())

            # Подписки, истекающие в ближайшие 7 дней
            week_later = datetime.utcnow() + timedelta(days=7)
            expiring_query = select(Subscription).where(
                Subscription.status == 'active',
                Subscription.end_date <= week_later,
                Subscription.end_date > datetime.utcnow()
            )
            expiring_result = await session.execute(expiring_query)
            expiring_subs = len(expiring_result.fetchall())

            # Формируем сообщение со статистикой
            message_text = "📊 <b>Статистика подписок</b>\n\n"

            message_text += f"📈 <b>Общая статистика:</b>\n"
            message_text += f"   • Всего подписок: <b>{len(total_subs)}</b>\n"
            message_text += f"   • За последние 30 дней: <b>{recent_subs}</b>\n"
            message_text += f"   • Истекают через 7 дней: <b>{expiring_subs}</b>\n\n"

            message_text += f"📋 <b>Статусы подписок:</b>\n"
            for status, count in status_stats.items():
                emoji = {'active': '✅', 'pending': '🟡', 'canceled': '❌', 'expired': '⏳'}.get(status, '❓')
                message_text += f"   • {emoji} {status}: <b>{count}</b>\n"

            message_text += f"\n💳 <b>Статусы платежей:</b>\n"
            for payment_status, count in payment_stats.items():
                emoji = {'completed': '💳', 'pending': '⏳', 'failed': '❌'}.get(payment_status, '❓')
                message_text += f"   • {emoji} {payment_status}: <b>{count}</b>\n"

            message_text += f"\n🎯 <b>Типы планов:</b>\n"
            for plan_type, count in plan_type_stats.items():
                message_text += f"   • {plan_type}: <b>{count}</b>\n"

            # Добавляем дату генерации отчета
            message_text += f"\n<i>Отчет сгенерирован: {datetime.utcnow().strftime('%d.%m.%Y %H:%M')}</i>"

            await message.answer(message_text, parse_mode="HTML")
            logger.info(f"Админ {user_id} запросил статистику по подпискам.")

    except Exception as e:
        logger.error(f"Ошибка при получении статистики: {str(e)}", exc_info=True)
        await message.answer("❌ Произошла ошибка при получении статистики.")


@router.message(Command("admin_help"))
async def admin_help(message: Message):
    """Помощь по административным командам"""
    user_id = message.from_user.id

    if not is_admin(user_id):
        await message.answer("❌ У вас нет прав для выполнения этой команды.")
        return

    help_text = """
🔧 <b>Административные команды</b>

📋 <b>Просмотр подписок:</b>
• /all_subscriptions - Все подписки
• /active_subscriptions - Только активные подписки
• /subscription_stats - Статистика по подпискам
• /invite_stats - Статистика по ссылкам

📊 <b>Управление:</b>
• /free_stats - Статистика бесплатной рассылки
• /list_free_posts - Показать все активные посты для бесплатной рассылки
• /delete_free_post - Удалить пост из бесплатной рассылки
• /add_free_post - Начать создание поста для бесплатной рассылки

💡 <b>Советы:</b>
• Используйте /admin_help для повторного просмотра команд
• Теги @username могут не работать, используйте telegram_id
"""

    await message.answer(help_text, parse_mode="HTML")


@router.message(Command("invite_stats"))
async def invite_stats(message: Message):
    """Статистика по ссылкам"""
    if not is_admin(message.from_user.id):
        return

    async with get_db_session() as session:
        # Общая статистика
        total_query = select(InviteLink)
        total_result = await session.execute(total_query)
        total = len(total_result.fetchall())

        used_query = select(InviteLink).where(InviteLink.is_used == True)
        used_result = await session.execute(used_query)
        used = len(used_result.fetchall())

        active_query = select(InviteLink).where(
            InviteLink.is_used == False,
            InviteLink.is_revoked == False,
            InviteLink.expires_at > datetime.utcnow()
        )
        active_result = await session.execute(active_query)
        active = len(active_result.fetchall())

        await message.answer(
            f"📊 <b>Статистика пригласительных ссылок:</b>\n\n"
            f"• Всего создано: <b>{total}</b>\n"
            f"• Использовано: <b>{used}</b>\n"
            f"• Активных: <b>{active}</b>\n"
            f"• Неиспользованных (истекших): <b>{total - used - active}</b>",
            parse_mode="HTML"
        )

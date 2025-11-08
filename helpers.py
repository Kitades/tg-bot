# helpers.py (расширенная версия)
from typing import List, Tuple
from aiogram import Bot

from config import ADMIN_IDS


def get_admin_ids() -> List[int]:
    """Получить список ID администраторов"""
    return ADMIN_IDS.copy()  # Возвращаем копию для безопасности


async def is_admin(user_id: int) -> bool:
    """Проверка, является ли пользователь администратором"""
    return user_id in get_admin_ids()


async def notify_admins(bot: Bot, message: str, parse_mode: str = "HTML",
                        reply_markup=None) -> Tuple[int, int]:
    success_count = 0
    fail_count = 0

    for admin_id in get_admin_ids():
        try:
            await bot.send_message(
                chat_id=admin_id,
                text=message,
                parse_mode=parse_mode,
                reply_markup=reply_markup
            )
            success_count += 1
        except Exception as e:
            print(f"❌ Ошибка отправки уведомления админу {admin_id}: {e}")
            fail_count += 1

    return success_count, fail_count


async def notify_admins_about_subscription(bot: Bot, user, subscription) -> Tuple[int, int]:
    message = (
        f"💸 <b>Новая подписка!</b>\n\n"
        f"👤 <b>Пользователь:</b> {user.full_name}\n"
        f"📧 <b>Username:</b> @{user.username or 'нет'}\n"
        f"🆔 <b>ID:</b> {user.telegram_id}\n"
        f"💳 <b>Тариф:</b> {subscription.plan_name}\n"
        f"💰 <b>Сумма:</b> {subscription.price:.2f}₽\n"
        f"📅 <b>Дата:</b> {subscription.created_at.strftime('%d.%m.%Y %H:%M')}"
    )

    return await notify_admins(bot, message, parse_mode="HTML")

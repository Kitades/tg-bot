from aiogram import types
from aiogram.filters import state

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from sqlalchemy import select

from config import SUBSCRIPTION_PRICE, USERNAME_CHANNEL
from database.models import Subscription, User
from database.session import get_db_session
from log import logger


welcome_text = (
    "👋 Приветсвуем вас в чате вступления в канал Потяева Владимира о стоматологии.\n"
    "Вас ждут еженедельные разборы консультаций, ортодонтических случаев, интересных комплексных случаев, "
    "разборы организации  клиники и взаимосвязи управления с медициной, "
    "регулярные обсуждения по живым вопросам!\n\n"
    "🎁 Вы автоматически подписаны на <b>бесплатную рассылку</b> - "
    "будете получать интересные посты каждый день в 14:00.\n\n"
    "💎 Чтобы получить доступ ко всему эксклюзивному контенту, "
    "оформите премиум подписку: \n\n"
)


async def main_keyboard(message, sub_info, has_active_sub: bool = False):
    async with get_db_session() as session:
        user_result = await session.execute(
            select(User).where(User.telegram_id == message.from_user.id)
        )
        user = user_result.scalar_one_or_none()

    user_email = user.email if user else "не указан"
    """Создает главную клавиатуру"""
    if has_active_sub:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="✏️ Изменить email", callback_data="change_email")],
            [InlineKeyboardButton(text=" Помощь", callback_data="help")]
        ])
        await message.answer(
            f"{welcome_text}"
            f"📧 Ваш email: <b>{user_email}</b>\n\n"
            f"💰 Участие в информационном канале по стоматологии - {SUBSCRIPTION_PRICE[1]} руб в месяц\n"
            f"🎓 Для студентов и ординаторов - {SUBSCRIPTION_PRICE[0]} руб в месяц"
            f"\n\n🎉 <b>У вас активная подписка до {sub_info['end_date']}</b>",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="✏️ Изменить email", callback_data="change_email")],
            [InlineKeyboardButton(text=" Помощь", callback_data="help")]
        ])
        await message.answer(
            f"{welcome_text}"
            f"📧 Ваш email: <b>{user_email}</b>\n\n"
            f"💰 Участие в информационном канале по стоматологии - {SUBSCRIPTION_PRICE[1]} руб в месяц\n"
            f"🎓 Для студентов и ординаторов - {SUBSCRIPTION_PRICE[0]} руб в месяц"
            "\n\n📋 Используйте кнопку '💳 Купить подписку' для доступа к контенту",
            parse_mode='HTML',
            reply_markup=keyboard
        )


async def back_main(callback, has_active_sub):
    if has_active_sub:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="✏️ Изменить email", callback_data="change_email")],
            [InlineKeyboardButton(text=" Помощь", callback_data="help")]
        ])
        await callback.message.answer(
            welcome_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="✏️ Изменить email", callback_data="change_email")],
            [InlineKeyboardButton(text=" Помощь", callback_data="help")]
        ])
        await callback.message.answer(
            welcome_text,
            parse_mode='HTML',
            reply_markup=keyboard
        )


async def show_tariff_selection(message):
    """Показывает выбор тарифов"""
    keyboard = [
        [
            types.InlineKeyboardButton(
                text=f"💼 Обычный - {SUBSCRIPTION_PRICE[1]} руб/мес",
                callback_data="tariff_regular"
            )
        ],
        [
            types.InlineKeyboardButton(
                text=f"🎓 Студенческий - {SUBSCRIPTION_PRICE[0]} руб/мес",
                callback_data="tariff_student"
            )
        ]
    ]
    markup = types.InlineKeyboardMarkup(inline_keyboard=keyboard)

    await message.answer(
        " Выберите тарифный план:\n\n"
        f"💼 <b>Обычный</b> - {SUBSCRIPTION_PRICE[1]} руб/мес\n"
        "• Полный доступ ко всем материалам\n"
        "• Автоматическое продление\n\n"
        f"🎓 <b>Студенческий</b> - {SUBSCRIPTION_PRICE[0]} руб/мес\n"
        "• Полный доступ ко всем материалам  \n"
        "• Специальная цена для студентов\n\n"
        "• Введите EMAIL для отправки чека\n\n"
        "• Автоматическое продление\n\n"
        "После оплаты доступ откроется автоматически!",
        reply_markup=markup,
        parse_mode="HTML"
    )


async def show_tariff_selection_by_callback(callback):
    """Показ тарифов через CallbackQuery объект"""

    keyboard = [
        [InlineKeyboardButton(text=f"💼 Обычный - {SUBSCRIPTION_PRICE[1]} руб/мес", callback_data="tariff_regular")],
        [InlineKeyboardButton(text=f"🎓 Студенческий - {SUBSCRIPTION_PRICE[0]} руб/мес", callback_data="tariff_student")]
    ]
    markup = InlineKeyboardMarkup(inline_keyboard=keyboard)

    await callback.message.answer(
        "🎯 <b>Выберите тарифный план:</b>\n\n"
        f"💼 <b>Обычный</b> - {SUBSCRIPTION_PRICE[1]} руб/мес\n"
        "• Полный доступ ко всем материалам\n"
        "• Автоматическое продление\n\n"
        f"🎓 <b>Студенческий</b> - {SUBSCRIPTION_PRICE[0]} руб/мес\n"
        "• Полный доступ ко всем материалам\n"
        "• Специальная цена для студентов\n"
        "• Автоматическое продление\n\n"
        "После оплаты доступ откроется автоматически!",
        reply_markup=markup,
        parse_mode="HTML"
    )


async def _process_tariff_selection(callback, subscription, payment):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Проверить оплату",
                              callback_data=f"check_payment_{subscription.id}")],
        [InlineKeyboardButton(text="🔗 Перейти к оплате", url=payment['confirmation_url'])],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]
    ])

    await callback.message.answer(
        f"✅ Выбран тариф: {subscription.plan_name}\n"
        f"💳 Сумма к оплате: {subscription.price:.2f}₽\n\n"
        f"🔗 <a href='{payment['confirmation_url']}'>Ссылка для оплаты</a>\n\n",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def _show_cancel_confirmation(callback, subscription, days_left):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="✅ Да, отменить автоплатежи",
                callback_data="confirm_cancel_auto"
            )
        ],
        [
            InlineKeyboardButton(
                text="❌ Нет, оставить как есть",
                callback_data="back_to_main"
            )
        ]
    ])
    await callback.message.answer(
        f"⚠️ <b>Подтверждение отмены автоплатежей</b>\n\n"
        f"📋 Тариф: <b>{subscription.plan_name}</b>\n"
        f"💰 Стоимость: <b>{subscription.price} руб.</b>\n"
        f"📅 Подписка действует до: <b>{subscription.end_date.strftime('%d.%m.%Y')}</b>\n"
        f"⏳ Осталось дней: <b>{days_left}</b>\n\n"
        f"<b>После отмены автоплатежей:</b>\n"
        f"• Подписка не будет продлена автоматически\n"
        f"• Текущий доступ сохранится до {subscription.end_date.strftime('%d.%m.%Y')}\n"
        f"• Для продления нужно будет оформить подписку заново\n\n"
        f"<b>Вы уверены, что хотите отменить автоплатежи?</b>",
        parse_mode="HTML",
        reply_markup=keyboard
    )


async def _check_payment(callback: types.CallbackQuery, subscription: Subscription, group_url: str = None):
    """Обрабатывает успешную оплату"""
    try:
        # Добавляем пользователя в группу
        if group_url:
            try:
                await callback.bot.unban_chat_member(
                    chat_id=USERNAME_CHANNEL,
                    user_id=callback.from_user.id
                )
            except Exception as e:
                logger.warning(f"Ошибка добавления в группу: {str(e)}")

        message_text = (
            f"✅ <b>Подписка активирована!</b>\n\n"
            f"📋 Тариф: <b>{subscription.plan_name}</b>\n"
            f"💰 Стоимость: <b>{subscription.price} руб</b>\n"
            f"📅 Доступ до: <b>{subscription.end_date.strftime('%d.%m.%Y')}</b>\n"
            f"🔄 Автоплатеж: <b>{'Включен' if subscription.auto_renew else 'Отключен'}</b>\n\n"
        )
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔗 Получить ссылку в группу", callback_data="get_invite_link")]
        ])

        await callback.message.answer(message_text, parse_mode="HTML", reply_markup=keyboard)
        logger.info(f"Подписка {subscription.id} активирована для пользователя {callback.from_user.id}")

    except Exception as e:
        logger.error(f"Ошибка обработки успешной оплаты: {str(e)}", exc_info=True)


async def _content_handler(callback, group_url):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔗 Получить ссылку в группу", callback_data="get_invite_link")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

    await callback.message.answer(
        "📚 <b>Доступный контент:</b>\n\n"
        "• Эксклюзивные статьи по стоматологии\n"
        "• Видео-уроки и мастер-классы\n"
        "• Новости индустрии\n"
        "• Возможность задать вопросы экспертам\n\n"
        "Для доступа к материалам перейдите в наш канал:",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def _content_handler_false(callback):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="my_subscription")]
    ])
    await callback.message.answer(
        "❌ <b>Доступ ограничен</b>\n\n"
        "Для доступа к эксклюзивному контенту необходимо приобрести подписку.",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def my_subscription(callback, subscription, days_left, auto_renew_status):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Перейти к контенту", callback_data="content")],
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="❌ Отменить автоплатежи", callback_data="_show_cancel_confirmation")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

    await callback.message.answer(
        f"📊 <b>Ваша подписка</b>\n\n"
        f"💳 Тариф: {subscription.plan_name}\n"
        f"💰 Стоимость: {subscription.price:.2f}₽\n"
        f"📅 Начало: {subscription.start_date.strftime('%d.%m.%Y')}\n"
        f"📅 Окончание: {subscription.end_date.strftime('%d.%m.%Y')}\n"
        f"🔄 Автоплатеж: <b>{auto_renew_status}</b>\n"
        f"⏳ Осталось дней: {days_left}\n"
        f"📈 Статус: ✅ Активна",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def my_subscription_inactive(callback, inactive_sub):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="📋 Посмотреть тарифы", callback_data="prices")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])
    await callback.message.answer(
        f"📊 <b>История подписок</b>\n\n"
        f"💳 Тариф: {inactive_sub.plan_name}\n"
        f"💰 Стоимость: {inactive_sub.price:.2f}₽\n"
        f"📅 Была активна до: {inactive_sub.end_date.strftime('%d.%m.%Y')}\n"
        f"🔄 Статус: ❌ {inactive_sub.status}",
        parse_mode='HTML',
        reply_markup=keyboard
    )

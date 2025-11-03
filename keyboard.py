from aiogram import types

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from config import SUBSCRIPTION_PRICE


async def main_keyboard(message, sub_info, has_active_sub: bool = False):
    """Создает главную клавиатуру"""
    if has_active_sub:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])
        await message.answer(
            "👋 Приветсвуем вас в чате вступления в канал Потяева Владимира о стоматологи. "
            "Вас ждут еженедельные разборы консультаций, ортодонтических случаев, интересных комплексных случаев, "
            "разборы организации  клиники и взаимосвязи управления с медициной, "
            "регулярные обсуждения по живым вопросам!\n\n"
            f"💰 Участие в информационном канале по стоматологии - {SUBSCRIPTION_PRICE[1]} руб в месяц\n"
            f"🎓 Для студентов и ординаторов - {SUBSCRIPTION_PRICE[0]} руб в месяц"
            f"\n\n🎉 <b>У вас активная подписка до {sub_info['end_date']}</b>",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])
        await message.answer(
            "👋 Приветсвуем вас в чате вступления в канал Потяева Владимира о стоматологи. "
            "Вас ждут еженедельные разборы консультаций, ортодонтических случаев, интересных комплексных случаев, "
            "разборы организации  клиники и взаимосвязи управления с медициной, "
            "регулярные обсуждения по живым вопросам!\n\n"
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
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])
        await callback.message.answer(
            "👋 Приветсвуем вас в чате вступления в канал Потяева Владимира о стоматологи. "
            "Вас ждут еженедельные разборы консультаций, ортодонтических случаев, интересных комплексных случаев, "
            "разборы организации  клиники и взаимосвязи управления с медициной, "
            "регулярные обсуждения по живым вопросам!\n\n",
            parse_mode='HTML',
            reply_markup=keyboard
        )
    else:
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])
        await callback.message.answer(
            "👋 Приветсвуем вас в чате вступления в канал Потяева Владимира о стоматологи. "
            "Вас ждут еженедельные разборы консультаций, ортодонтических случаев, интересных комплексных случаев, "
            "разборы организации  клиники и взаимосвязи управления с медициной, "
            "регулярные обсуждения по живым вопросам!\n\n",
            parse_mode='HTML',
            reply_markup=keyboard
        )


async def show_tariff_selection(callback: types.CallbackQuery):
    """Показывает выбор тарифов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💳 Обычный - {SUBSCRIPTION_PRICE[1]}₽", callback_data="tariff_regular"),
            InlineKeyboardButton(text=f"🎓 Студент - {SUBSCRIPTION_PRICE[0]}₽", callback_data="tariff_student")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]
    ])

    await callback.message.answer(
        "🎯 <b>Выберите тариф:</b>\n\n"
        f"💳 <b>Обычный</b> - {SUBSCRIPTION_PRICE[1]}₽/месяц\n"
        "• Полный доступ к контенту\n\n"
        f"🎓 <b>Студенческий</b> - {SUBSCRIPTION_PRICE[0]}₽/месяц\n"
        "• Требуется подтверждение статуса\n"
        "• Полный доступ к контенту",
        parse_mode='HTML',
        reply_markup=keyboard
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
        f"🔗 <a href='{payment['confirmation_url']}'>Ссылка для оплаты</a>\n\n"
        "После оплаты нажмите '✅ Проверить оплату'",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def _check_payment(callback, subscription, URL):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=f"{URL}")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="my_subscription")]
    ])

    await callback.message.answer(
        f"🎉 <b>Подписка активирована!</b>\n\n"
        f"📅 Действует до: {subscription.end_date.strftime('%d.%m.%Y')}\n"
        f"💳 Тариф: {subscription.plan_name}\n"
        f"💰 Сумма: {subscription.price:.2f}₽\n\n"
        f"Теперь вам доступен эксклюзивный контент!",
        parse_mode='HTML',
        reply_markup=keyboard
    )


async def _content_handler(callback, URL):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Перейти в канал", url=f"{URL}")],
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


async def my_subscription(callback, subscription, days_left):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 Перейти к контенту", callback_data="content")],
        [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy_subscription")],
        [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
    ])

    await callback.message.answer(
        f"📊 <b>Ваша подписка</b>\n\n"
        f"💳 Тариф: {subscription.plan_name}\n"
        f"💰 Стоимость: {subscription.price:.2f}₽\n"
        f"📅 Начало: {subscription.start_date.strftime('%d.%m.%Y')}\n"
        f"📅 Окончание: {subscription.end_date.strftime('%d.%m.%Y')}\n"
        f"⏳ Осталось дней: {days_left}\n"
        f"🔄 Статус: ✅ Активна",
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


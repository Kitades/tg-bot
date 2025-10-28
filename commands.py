from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from sqlalchemy import select

from config import ADMIN_ID, SUBSCRIPTION_PRICE, URL
from database.models import User, Subscription
from database.session import get_db_session
from keyboard import main_keyboard, show_tariff_selection
from payment import yookassa_service

router = Router()

PRICES = {
    'regular': SUBSCRIPTION_PRICE[1],  # Обычный
    'student': SUBSCRIPTION_PRICE[0]  # Студенческий
}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    telegram_user = message.from_user

    async with get_db_session() as session:
        try:
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_user.id)
            )
            user = result.scalar_one_or_none()

            if not user:
                user = User(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    full_name=f"{telegram_user.first_name or ''} {telegram_user.last_name or ''}".strip()
                )
                session.add(user)
                await session.commit()
                print(f"✅ Пользователь создан: {telegram_user.id}")
                await session.refresh(user)

            has_active_sub = await check_active_subscription(user.id)
            welcome_text = (
                "👋 Приветсвуем вас в чате вступления в канал Потяева Владимира о стоматологи. "
                "Вас ждут еженедельные разборы консультаций, ортодонтических случаев, интересных комплексных случаев, "
                "разборы организации  клиники и взаимосвязи управления с медициной, "
                "регулярные обсуждения по живым вопросам!\n\n"
                f"💰 Участие в информационном канале по стоматологии - {SUBSCRIPTION_PRICE[1]} руб в месяц\n"
                f"🎓 Для студентов и ординаторов - {SUBSCRIPTION_PRICE[0]} руб в месяц"
            )

            if has_active_sub:
                sub_info = await get_subscription_info(user.id)
                welcome_text += f"\n\n🎉 <b>У вас активная подписка до {sub_info['end_date']}</b>"
            else:
                welcome_text += "\n\n📋 Используйте кнопку '💳 Купить подписку' для доступа к контенту"

            await message.answer(
                welcome_text,
                parse_mode='HTML',
                reply_markup=await main_keyboard(has_active_sub)
            )

        except Exception as e:
            print(f"❌ Ошибка в /start: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")


async def check_active_subscription(user_id: int) -> bool:
    """Проверяет есть ли активная подписка"""
    async with get_db_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == 'active')
            .where(Subscription.end_date > datetime.utcnow())
        )
        return result.scalar_one_or_none() is not None


async def get_subscription_info(user_id: int) -> dict:
    """Получает информацию о подписке"""
    async with get_db_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == 'active')
            .where(Subscription.end_date > datetime.utcnow())
            .order_by(Subscription.created_at.desc())
        )
        sub = result.scalar_one_or_none()

        if sub:
            return {
                'plan_name': sub.plan_name,
                'end_date': sub.end_date.strftime('%d.%m.%Y'),
                'days_left': (sub.end_date - datetime.utcnow()).days
            }
        return {}


@router.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: types.CallbackQuery):
    """Обработка кнопки покупки подписки"""
    user_id = callback.from_user.id

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Сначала используйте /start")
                return

            if await check_active_subscription(user.id):
                sub_info = await get_subscription_info(user.id)
                await callback.message.answer(
                    f"⚠️ У вас уже есть активная подписка!\n\n"
                    f"📅 Действует до: {sub_info['end_date']}\n"
                    f"⏳ Осталось дней: {sub_info['days_left']}"
                )
                await callback.answer()
                return

            await show_tariff_selection(callback)
            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка покупки подписки: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def process_tariff_selection(callback: types.CallbackQuery):
    """Обработка выбора тарифа"""
    tariff_type = callback.data.replace("tariff_", "")
    user_id = callback.from_user.id

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден")
                return

            subscription = Subscription(
                user_id=user.id,
                plan_type=tariff_type,
                plan_name="Обычный" if tariff_type == "regular" else "Студенческий",
                price=PRICES[tariff_type],
                currency="RUB",
                status="pending",
                payment_status="pending"
            )
            session.add(subscription)
            await session.commit()
            await session.refresh(subscription)

            try:
                payment = await yookassa_service.create_payment(
                    subscription_id=subscription.id,
                    amount=subscription.price,
                    user_id=user.id,
                    description=f"Подписка: {subscription.plan_name}"
                )

                subscription.payment_id = payment['payment_id']
                await session.commit()

                await callback.message.answer(
                    f"✅ Выбран тариф: {subscription.plan_name}\n"
                    f"💳 Сумма к оплате: {subscription.price:.2f}₽\n\n"
                    f"🔗 <a href='{payment['confirmation_url']}'>Ссылка для оплаты</a>\n\n"
                    "После оплаты нажмите '✅ Проверить оплату'",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="✅ Проверить оплату",
                                              callback_data=f"check_payment_{subscription.id}")],
                        [InlineKeyboardButton(text="🔗 Перейти к оплате", url=payment['confirmation_url'])],
                        [InlineKeyboardButton(text="❌ Отмена", callback_data="back_to_main")]
                    ])
                )
            except Exception as e:
                print(f"❌ Ошибка создания платежа: {e}")
                await callback.message.answer("❌ Ошибка при создании платежа. Попробуйте позже.")
                await session.delete(subscription)
                await session.commit()

            await callback.answer()
        except Exception as e:
            print(f"❌ Ошибка выбора тарифа: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: types.CallbackQuery):
    """Проверка оплаты"""
    subscription_id = int(callback.data.replace("check_payment_", ""))
    user_id = callback.from_user.id

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден")
                return

            result = await session.execute(
                select(Subscription)
                .where(Subscription.id == subscription_id)
                .where(Subscription.user_id == user.id)
            )
            subscription = result.scalar_one_or_none()

            if not subscription:
                await callback.message.answer("❌ Подписка не найдена")
                await callback.answer()
                return

            if subscription.status == 'active':
                await callback.message.answer("✅ Подписка уже активирована!")
                await callback.answer()
                return

            if subscription.payment_id:
                try:
                    payment_info = await yookassa_service.check_payment(subscription.payment_id)

                    if payment_info['paid']:
                        # Активируем подписку
                        subscription.status = 'active'
                        subscription.payment_status = 'completed'
                        subscription.start_date = datetime.utcnow()
                        subscription.end_date = datetime.utcnow() + timedelta(days=30)
                        subscription.updated_at = datetime.utcnow()

                        await session.commit()

                        await callback.message.answer(
                            f"🎉 <b>Подписка активирована!</b>\n\n"
                            f"📅 Действует до: {subscription.end_date.strftime('%d.%m.%Y')}\n"
                            f"💳 Тариф: {subscription.plan_name}\n"
                            f"💰 Сумма: {subscription.price:.2f}₽\n\n"
                            f"Теперь вам доступен эксклюзивный контент!",
                            parse_mode='HTML',
                            reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                                [InlineKeyboardButton(text="📢 Перейти в канал", url=f"{URL}")],
                                [InlineKeyboardButton(text="◀️ Назад", callback_data="my_subscription")]
                            ])
                        )

                        if ADMIN_ID:
                            try:
                                await callback.bot.send_message(
                                    ADMIN_ID,
                                    f"💸 Новая подписка!\n"
                                    f"👤 Пользователь: {user.full_name}\n"
                                    f"📧 @{user.username or 'нет'}\n"
                                    f"🆔 ID: {user.id}\n"
                                    f"💳 Тариф: {subscription.plan_name}\n"
                                    f"💰 Сумма: {subscription.price:.2f}₽"
                                )
                            except Exception as e:
                                print(f"❌ Ошибка уведомления админу: {e}")

                    else:
                        await callback.message.answer(
                            f"⌛ Платеж в статусе: {payment_info['status']}\n"
                            "Попробуйте проверить позже или обратитесь в поддержку."
                        )

                except Exception as e:
                    print(f"❌ Ошибка проверки платежа: {e}")
                    await callback.message.answer("❌ Ошибка при проверке платежа. Попробуйте позже.")
            else:
                await callback.message.answer("❌ ID платежа не найден")

            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка проверки платежа: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()


@router.callback_query(F.data == "my_subscription")
async def my_subscription_handler(callback: types.CallbackQuery):
    """Обработчик кнопки 'Моя подписка'"""
    user_id = callback.from_user.id

    async with get_db_session() as session:
        try:

            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден. Используйте /start")
                return

            result = await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.id)
                .where(Subscription.status == 'active')
                .where(Subscription.end_date > datetime.utcnow())
                .order_by(Subscription.created_at.desc())
            )
            subscription = result.scalar_one_or_none()

            if subscription:

                days_left = (subscription.end_date - datetime.utcnow()).days

                message_text = (
                    f"📊 <b>Ваша подписка</b>\n\n"
                    f"💳 Тариф: {subscription.plan_name}\n"
                    f"💰 Стоимость: {subscription.price:.2f}₽\n"
                    f"📅 Начало: {subscription.start_date.strftime('%d.%m.%Y')}\n"
                    f"📅 Окончание: {subscription.end_date.strftime('%d.%m.%Y')}\n"
                    f"⏳ Осталось дней: {days_left}\n"
                    f"🔄 Статус: ✅ Активна"
                )

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="📚 Перейти к контенту", callback_data="content")],
                    [InlineKeyboardButton(text="🔄 Продлить подписку", callback_data="buy_subscription")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
                ])

            else:

                inactive_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.created_at.desc())
                )
                inactive_sub = inactive_result.scalar_one_or_none()

                if inactive_sub:
                    message_text = (
                        f"📊 <b>История подписок</b>\n\n"
                        f"💳 Тариф: {inactive_sub.plan_name}\n"
                        f"💰 Стоимость: {inactive_sub.price:.2f}₽\n"
                        f"📅 Была активна до: {inactive_sub.end_date.strftime('%d.%m.%Y')}\n"
                        f"🔄 Статус: ❌ {inactive_sub.status}"
                    )
                else:
                    message_text = "❌ У вас нет активных подписок"

                keyboard = InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
                    [InlineKeyboardButton(text="📋 Посмотреть тарифы", callback_data="prices")],
                    [InlineKeyboardButton(text="◀️ Назад", callback_data="back_to_main")]
                ])

            await callback.message.edit_text(
                message_text,
                parse_mode='HTML',
                reply_markup=keyboard
            )
            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка в my_subscription_handler: {e}")
            await callback.message.answer("❌ Произошла ошибка при получении информации о подписке")
            await callback.answer()


@router.callback_query(F.data == "back_to_main")
async def back_to_main_handler(callback: types.CallbackQuery):
    """Обработчик кнопки 'Назад' - возврат к главному меню"""
    user_id = callback.from_user.id

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if user:
                result = await session.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date > datetime.utcnow())
                )
                has_active_sub = result.scalar_one_or_none() is not None
            else:
                has_active_sub = False

            from keyboard import main_keyboard
            keyboard = await main_keyboard(has_active_sub)

            # Возвращаемся к главному сообщению
            await callback.message.edit_text(
                "👋 Добро пожаловать в главное меню!",
                reply_markup=keyboard
            )
            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка в back_to_main_handler: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()


@router.callback_query(F.data == "content")
async def content_handler(callback: types.CallbackQuery):
    """Обработчик кнопки 'Контент'"""
    user_id = callback.from_user.id

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if user:
                result = await session.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .where(Subscription.status == 'active')
                    .where(Subscription.end_date > datetime.utcnow())
                )
                has_active_sub = result.scalar_one_or_none() is not None
            else:
                has_active_sub = False

            if has_active_sub:
                await callback.message.answer(
                    "📚 <b>Доступный контент:</b>\n\n"
                    "• Эксклюзивные статьи по стоматологии\n"
                    "• Видео-уроки и мастер-классы\n"
                    "• Новости индустрии\n"
                    "• Возможность задать вопросы экспертам\n\n"
                    "Для доступа к материалам перейдите в наш канал:",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="📢 Перейти в канал", url=f"{URL}")],
                        [InlineKeyboardButton(text="◀️ Назад", callback_data="my_subscription")]
                    ])
                )
            else:
                await callback.message.answer(
                    "❌ <b>Доступ ограничен</b>\n\n"
                    "Для доступа к эксклюзивному контенту необходимо приобрести подписку.",
                    parse_mode='HTML',
                    reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                        [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
                        [InlineKeyboardButton(text="◀️ Назад", callback_data="my_subscription")]
                    ])
                )

            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка в content_handler: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()

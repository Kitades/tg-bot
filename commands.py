from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime, timedelta
from sqlalchemy import select

from config import ADMIN_ID, SUBSCRIPTION_PRICE, URL
from database.models import User, Subscription
from database.session import get_db_session
from keyboard import main_keyboard, show_tariff_selection, _process_tariff_selection, _check_payment, _content_handler, \
    _content_handler_false, back_main, my_subscription, my_subscription_inactive
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

            sub_info = await get_subscription_info(user.id)

            await main_keyboard(message, sub_info, has_active_sub)

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

                await _process_tariff_selection(callback, subscription, payment)

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

                        await _check_payment(callback, subscription, URL)

                        if ADMIN_ID:
                            try:
                                await callback.bot.send_message(
                                    ADMIN_ID,
                                    f"💸 Новая подписка!\n"
                                    f"👤 Пользователь: {user.full_name}\n"
                                    f"📧 @{user.username or 'нет'}\n"
                                    f"🆔 ID: {user.telegram_id}\n"
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
                await my_subscription(callback, subscription, days_left)
            else:
                inactive_result = await session.execute(
                    select(Subscription)
                    .where(Subscription.user_id == user.id)
                    .order_by(Subscription.created_at.desc())
                )
                inactive_sub = inactive_result.scalar_one_or_none()
                if inactive_sub:
                    await my_subscription_inactive(callback, inactive_sub)
                else:
                    await callback.message.answer("❌ У вас нет активных подписок")

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
                await back_main(callback, has_active_sub)
            else:
                has_active_sub = False
                await back_main(callback, has_active_sub)

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
                await _content_handler(callback, URL)
            else:
                await _content_handler_false(callback)

            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка в content_handler: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()

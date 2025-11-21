from aiogram import Router, types, F
from aiogram.filters import Command, StateFilter
from datetime import datetime

from aiogram.fsm import state
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder
from dateutil.relativedelta import relativedelta
from sqlalchemy import select, and_

from config import SUBSCRIPTION_PRICE, URL, ADMIN_IDS, USERNAME_CHANNEL
from database.models import User, Subscription, UserSettings, FreeDailyPost
from database.session import get_db_session
from helpers import is_admin
from keyboard import main_keyboard, show_tariff_selection, _process_tariff_selection, _content_handler, \
    _content_handler_false, back_main, _show_cancel_confirmation, my_subscription, my_subscription_inactive, \
    _check_payment, show_tariff_selection_callback
import logging

from payment.yookassa_service import YooKassaService
from servises.daily_poster import FreePostService
from states.subscription_states import FreePostCreation, SubscriptionStates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
router = Router()

PRICES = {
    'regular': SUBSCRIPTION_PRICE[1],  # Обычный
    'student': SUBSCRIPTION_PRICE[0]  # Студенческий
}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
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
                await session.flush()
                print(f"✅ Создан пользователь с ID: {user.id}")
            user_settings = await session.get(UserSettings, user.id)
            if not user_settings:
                user_settings = UserSettings(
                    user_id=user.id,
                    wants_free_posts=True
                )
                session.add(user_settings)
                print(f"✅ Созданы настройки для user_id: {user.id}")

            await session.commit()
            print(f"✅ Пользователь создан: {telegram_user.id}")
            await session.refresh(user)
            await session.refresh(user_settings)
            has_active_sub = await check_active_subscription(user.id)
            sub_info = await get_subscription_info(user.id)

            await main_keyboard(message, sub_info, has_active_sub)

        except Exception as e:
            print(f"❌ Ошибка в /start: {e}")
            await session.rollback()
            await message.answer("Произошла ошибка. Попробуйте позже.")


async def check_active_subscription(user_id: int) -> bool:
    """Проверяет есть ли активная подписка"""
    logger.debug(f"Проверка активной подписки для пользователя {user_id}")

    async with get_db_session() as session:
        result = await session.execute(
            select(Subscription)
            .where(Subscription.user_id == user_id)
            .where(Subscription.status == 'active')
            .where(Subscription.end_date > datetime.utcnow())
        )
        subscription = result.scalar_one_or_none()

        if subscription:
            logger.debug(f"Найдена активная подписка {subscription.id} для пользователя {user_id}")
        else:
            logger.debug(f"Активная подписка для пользователя {user_id} не найдена")

        return subscription is not None


async def get_subscription_info(user_id: int) -> dict:
    """Получает информацию о подписке"""
    logger.debug(f"Получение информации о подписке для пользователя {user_id}")

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
            days_left = (sub.end_date - datetime.utcnow()).days
            info = {
                'plan_name': sub.plan_name,
                'end_date': sub.end_date.strftime('%d.%m.%Y'),
                'days_left': days_left,
                'auto_renew': sub.auto_renew
            }
            logger.debug(f"Информация о подписке: {info}")
            return info
        return {}


def is_valid_email(email: str) -> bool:
    """Простая валидация email"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return re.match(pattern, email) is not None


@router.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: types.CallbackQuery):
    """Обработка кнопки покупки подписки"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал покупку подписки")

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_id} не найден в БД")
                await callback.answer("❌ Сначала используйте /start")
                return

            # Проверяем активную подписку
            if await check_active_subscription(user.id):
                sub_info = await get_subscription_info(user.id)
                message = (
                    f"⚠️ У вас уже есть активная подписка!\n\n"
                    f"📅 Действует до: {sub_info['end_date']}\n"
                    f"⏳ Осталось дней: {sub_info['days_left']}\n"
                    f"🔄 Автоплатеж: {'✅ Включен' if sub_info['auto_renew'] else '❌ Выключен'}"
                )
                await callback.message.answer(message)
                await callback.answer()
                return

            if not user.email:
                # Если email нет - запрашиваем его
                await callback.message.answer(
                    "📧 <b>Для оформления подписки нужен ваш email</b>\n\n"
                    "Он потребуется для отправки чека об оплате.\n"
                    "Пожалуйста, введите ваш email:",
                    parse_mode="HTML"
                )
                await state.set_state(SubscriptionStates.waiting_email)
                await state.update_data(user_id=user.id)

            else:
                await show_tariff_selection_callback(callback)

            await callback.answer()
            logger.info(f"Показан выбор тарифов для пользователя {user_id}")

        except Exception as e:
            logger.error(f"Ошибка покупки подписки: {str(e)}", exc_info=True)
            await callback.message.answer("❌ Произошла ошибка при обработке запроса")
            await callback.answer()


@router.message(SubscriptionStates.waiting_email)
async def process_user_email(message, state: FSMContext):
    """Обработка введенного email пользователя"""
    user_id = message.from_user.id
    email = message.text.strip()

    # Базовая валидация email
    if not is_valid_email(email):
        await message.answer(
            "❌ <b>Неверный формат email</b>\n\n"
            "Пожалуйста, введите корректный email адрес:\n"
            "<i>Пример: example@gmail.com</i>",
            parse_mode="HTML"
        )
        return

    try:
        # Сохраняем email в базу данных
        async with get_db_session() as session:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if user:
                user.email = email
                await session.commit()
                logger.info(f"Email сохранен для пользователя {user_id}: {email}")

            # Показываем выбор тарифа
            await show_tariff_selection(message)
            await state.clear()

    except Exception as e:
        logger.error(f"Ошибка сохранения email: {e}")
        await message.answer("❌ Произошла ошибка при сохранении email. Попробуйте позже.")
        await state.clear()


@router.callback_query(F.data == "change_email")
async def change_email(callback: CallbackQuery, state: FSMContext):
    """Изменение email пользователя"""
    await callback.message.answer(
        "📧 <b>Введите новый email:</b>\n\n"
        "Он будет использоваться для отправки чеков об оплате.",
        parse_mode="HTML"
    )
    await state.set_state(SubscriptionStates.waiting_email)
    await callback.answer()

@router.callback_query(F.data == "_show_cancel_confirmation")
async def show_cancel_confirmation(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} начал отмену подписки")
    async with get_db_session() as session:
        try:
            # Получаем пользователя
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                logger.warning(f"Пользователь {user_id} не найден в БД")
                await callback.answer("❌ Сначала используйте /start")
                return

            subscription_result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user.id,
                    Subscription.status == 'active',
                    Subscription.end_date > datetime.utcnow()
                ).order_by(Subscription.created_at.desc())
            )
            subscription = subscription_result.scalar_one_or_none()
            if not subscription:
                await callback.message.answer(
                    "❌ У вас нет активной подписки.\n\n"
                    "Если у вас есть вопросы, обратитесь в поддержку."
                )
                return
            if not subscription.auto_renew:
                await callback.message.answer(
                    "ℹ️ Автоплатежи уже отключены для вашей подписки.\n\n"
                    f"📅 Подписка действует до: {subscription.end_date.strftime('%d.%m.%Y')}\n"
                    "После этой даты доступ будет закрыт."
                )
                return

            days_left = (subscription.end_date - datetime.utcnow()).days

            await _show_cancel_confirmation(callback, subscription, days_left)

        except Exception as e:
            logger.error(f"Ошибка при показе подтверждения отмены: {str(e)}", exc_info=True)
            await callback.answer("❌ Произошла ошибка. Попробуйте позже.")


@router.callback_query(F.data == "confirm_cancel_auto")
async def confirm_cancel_auto_subscription(callback: CallbackQuery):
    """Подтверждение отмены авто-подписки"""
    user_id = callback.from_user.id
    logger.info(f"Пользователь {user_id} подтвердил отмену авто-подписки")

    async with get_db_session() as session:
        try:

            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.message.answer("❌ Пользователь не найден")
                await callback.answer()
                return

            success = await YooKassaService.cancel_auto_payments(user.id)

            if success:
                # Получаем обновленную информацию о подписке
                subscription_result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user.id,
                        Subscription.status == 'active'
                    ).order_by(Subscription.created_at.desc())
                )
                subscription = subscription_result.scalar_one_or_none()

                if subscription:
                    message_text = (
                        f"✅ <b>Автоплатежи отменены!</b>\n\n"
                        f"📋 Тариф: <b>{subscription.plan_name}</b>\n"
                        f"📅 Подписка действует до: <b>{subscription.end_date.strftime('%d.%m.%Y')}</b>\n"
                        f"🔄 Автоплатеж: <b>❌ Отключен</b>\n\n"
                        f"<i>После {subscription.end_date.strftime('%d.%m.%Y')} доступ к материалам будет закрыт.</i>\n"
                        f"Для продления оформите подписку заново."
                    )
                else:
                    message_text = "✅ Автоплатежи отменены!"

                await callback.message.edit_text(
                    message_text,
                    parse_mode="HTML"
                )

                logger.info(f"Автоплатежи успешно отменены для пользователя {user_id}")

            else:
                await callback.message.edit_text(
                    "❌ <b>Не удалось отменить автоплатежи</b>\n\n"
                    "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
                    parse_mode="HTML"
                )
                logger.error(f"Ошибка отмены автоплатежей для пользователя {user_id}")

        except Exception as e:
            logger.error(f"Ошибка при отмене авто-подписки: {str(e)}", exc_info=True)
            await callback.message.edit_text(
                "❌ <b>Произошла ошибка при отмене автоплатежей</b>\n\n"
                "Пожалуйста, попробуйте позже или обратитесь в поддержку.",
                parse_mode="HTML"
            )

    await callback.answer()


@router.callback_query(F.data.startswith("tariff_"))
async def process_tariff_selection(callback: types.CallbackQuery):
    """Обработка выбора тарифа"""
    tariff_type = callback.data.replace("tariff_", "")
    user_id = callback.from_user.id

    logger.info(f"Пользователь {user_id} выбрал тариф: {tariff_type}")

    if tariff_type not in PRICES:
        logger.warning(f"Неизвестный тип тарифа: {tariff_type}")
        await callback.answer("❌ Неизвестный тариф")
        return

    async with get_db_session() as session:
        try:
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден")
                return

            if not user.email:
                await callback.message.answer(
                    "❌ <b>Email не указан</b>\n\n"
                    "Пожалуйста, сначала укажите ваш email для получения чека.",
                    parse_mode="HTML"
                )
                await callback.answer()
                return

            # Определяем название плана
            plan_name = "Обычный" if tariff_type == "regular" else "Студенческий"
            price = PRICES[tariff_type]

            # Создаем запись о подписке
            subscription = Subscription(
                user_id=user.id,
                plan_type=tariff_type,
                plan_name=plan_name,
                price=price,
                currency="RUB",
                status="pending",
                payment_status="pending",
                auto_renew=True,  # Включаем автосписание по умолчанию
                next_payment_date=datetime.utcnow() + relativedelta(months=1)
            )
            session.add(subscription)
            await session.commit()
            await session.refresh(subscription)

            logger.info(f"Создана подписка {subscription.id} для пользователя {user_id}")

            try:
                # Создаем платеж в ЮKассе
                payment_url, payment_id = await YooKassaService.create_subscription(
                    user_id=user.id,
                    plan_data={
                        'plan_type': tariff_type,
                        'plan_name': plan_name,
                        'price': float(price)
                    },
                    email=user.email
                )

                # Обновляем подписку с payment_id
                subscription.payment_id = payment_id
                await session.commit()

                # Отправляем пользователю ссылку на оплату
                await _process_tariff_selection(callback, subscription, {
                    'confirmation_url': payment_url,
                    'id': payment_id
                })

                logger.info(f"Платеж создан для подписки {subscription.id}, payment_id: {payment_id}")

            except Exception as e:
                logger.error(f"Ошибка создания платежа: {str(e)}", exc_info=True)
                await callback.message.answer("❌ Ошибка при создании платежа. Попробуйте позже.")
                # Удаляем подписку если не удалось создать платеж
                await session.delete(subscription)
                await session.commit()

            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка выбора тарифа: {str(e)}", exc_info=True)
            await callback.message.answer("❌ Произошла ошибка при выборе тарифа")
            await callback.answer()


@router.callback_query(F.data.startswith("check_payment_"))
async def check_payment(callback: types.CallbackQuery):
    """Проверка оплаты, но теперь без обращения к YooKassa API — только статус в БД"""

    subscription_id = int(callback.data.replace("check_payment_", ""))
    user_id = callback.from_user.id
    logger.info(f"Проверка оплаты для подписки {subscription_id} пользователем {user_id}")

    async with get_db_session() as session:
        try:
            # Получаем пользователя
            user_result = await session.execute(
                select(User).where(User.telegram_id == user_id)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await callback.answer("❌ Пользователь не найден")
                return

            # Получаем подписку
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

            # 💡 Теперь всё решает статус в БД, который выставляет ВЕБХУК
            if subscription.status == "active":
                await _check_payment(callback, subscription, USERNAME_CHANNEL)
                await callback.answer()
                return

            if subscription.status in ["pending", "waiting_payment", None]:
                await callback.message.answer(
                    "⌛ Платеж еще не подтверждён.\n"
                    "Обычно это занимает несколько секунд.\n"
                    "Если оплата прошла — подождите немного."
                )
                await callback.answer()
                return

            if subscription.status == "canceled":
                await callback.message.answer(
                    "❌ Платеж был отменён.\nПопробуйте оформить подписку снова."
                )
                await callback.answer()
                return

            if subscription.status == "failed":
                await callback.message.answer(
                    "❌ Ошибка при оплате.\nПлатеж не прошёл."
                )
                await callback.answer()
                return

            await callback.message.answer(
                f"Статус подписки: {subscription.status}"
            )
            await callback.answer()

        except Exception as e:
            logger.error(f"Ошибка проверки платежа: {str(e)}\", exc_info=True")
            await callback.message.answer("❌ Произошла ошибка при проверке платежа")
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
                await my_subscription(callback, subscription, days_left, subscription.auto_renew)
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


@router.message(Command("free_subscribe"))
async def free_subscribe_handler(message: types.Message):
    """Подписаться на бесплатную рассылку"""
    telegram_user = message.from_user.id
    async with get_db_session() as session:
        try:

            user_result = await session.execute(
                select(User).where(User.telegram_id == telegram_user)
            )
            user = user_result.scalar_one_or_none()

            if not user:
                await message.answer("❌ Пользователь не найден. Используйте /start")
                return

                # Проверяем, есть ли у пользователя активная подписка
            current_time = datetime.utcnow()
            active_subscription = await session.execute(
                select(Subscription)
                .where(
                    and_(
                        Subscription.user_id == user.id,
                        Subscription.status == 'active',
                        Subscription.end_date > current_time
                    )
                )
            )
            active_subscription = active_subscription.scalar()

            if active_subscription:
                await message.answer(
                    "❌ У вас уже есть активная премиум подписка!\n"
                    "Бесплатная рассылка предназначена для пользователей без подписки."
                )
                return

            # Находим или создаем настройки пользователя
            user_settings = await session.get(UserSettings, user.id)
            if not user_settings:
                user_settings = UserSettings(
                    user_id=user.id,
                    wants_free_posts=True
                )
                session.add(user_settings)
            else:
                user_settings.wants_free_posts = True

            await session.commit()

            await message.answer(
                "✅ Вы подписались на бесплатную рассылку!\n"
                "Вы будете получать интересные посты каждый день в 14:00 утра.\n\n"
                "💎 Чтобы получить доступ ко всему контенту, оформите премиум подписку"
            )
        except Exception as e:
            print(f"❌ Ошибка в /free_subscribe: {e}")
            await session.rollback()
            await message.answer("Произошла ошибка. Попробуйте позже.")


@router.message(Command("free_unsubscribe"))
async def free_unsubscribe_handler(message: types.Message):
    """Отписаться от бесплатной рассылки"""
    user_id = message.from_user.id
    async with get_db_session() as session:
        try:
            user_settings = await session.get(UserSettings, user_id)
            if user_settings:
                user_settings.wants_free_posts = False
                await session.commit()

            await message.answer(
                "❌ Вы отписались от бесплатной рассылки.\n"
                "Чтобы снова подписаться, используйте /free_subscribe\n\n"
                "💎 Или оформите премиум подписку"
            )
        except Exception as e:
            print(f"❌ Ошибка в /free_unsubscribe: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")


@router.message(Command("free_stats"))
async def free_stats_handler(message: types.Message):
    """Статистика бесплатной рассылки (для админов)"""
    async with get_db_session() as session:
        try:

            if not await is_admin(message.from_user.id):
                await message.answer("У вас нет прав для этой команды")
                return

            # Количество пользователей без подписки
            users_without_sub = await FreePostService.get_users_without_subscription()

            # Количество пользователей с истекшей подпиской
            users_expired_sub = await FreePostService.get_users_with_expired_subscription()

            total_free_users = len(users_without_sub) + len(users_expired_sub)

            # Количество пользователей с активной подпиской
            current_time = datetime.utcnow()
            active_subs = await session.execute(
                select(Subscription)
                .where(
                    and_(
                        Subscription.status == 'active',
                        Subscription.end_date > current_time
                    )
                )
            )
            active_subs_count = len(active_subs.scalars().all())

            stats_text = (
                "📊 <b>Статистика рассылок</b>\n\n"
                f" <b>Пользователей с подпиской:</b> {active_subs_count}\n"
                f" <b>Пользователей без подписки:</b> {total_free_users}\n"
                f"   - Никогда не было подписки: {len(users_without_sub)}\n"
                f"   - Подписка истекла: {len(users_expired_sub)}\n\n"
                f" <b>Время бесплатной рассылки:</b> 14:00"
            )

            await message.answer(stats_text, parse_mode="HTML")

        except Exception as e:
            print(f"❌ Ошибка в /free_stats: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")


@router.callback_query(lambda c: c.data == "help")
async def quick_help_handler(callback: types.CallbackQuery):
    """Быстрая помощь через инлайн-кнопку"""
    admin_id = ADMIN_IDS[0]

    builder = InlineKeyboardBuilder()
    builder.row(
        types.InlineKeyboardButton(
            text="💬 Написать админу",
            url=f"tg://user?id={admin_id}"
        )
    )

    await callback.message.answer(
        " <b>Быстрая помощь</b>\n\n"
        "Нажмите кнопку ниже чтобы сразу написать администратору:",
        reply_markup=builder.as_markup(),
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(Command("get_file_id"))
async def get_file_id_handler(message: types.Message):
    """Получить file_id отправленного медиа"""
    if not await is_admin(message.from_user.id):
        await message.answer("У вас нет прав для этой команды")
        return

    file_info = None
    file_type = None

    if message.photo:
        file_info = message.photo[-1]
        file_type = "photo"
    elif message.document:
        file_info = message.document
        file_type = "document"

    if file_info:
        await message.answer(
            f"📁 <b>File ID получен!</b>\n\n"
            f"📊 Тип: {file_type}\n"
            f"🆔 File ID: <code>{file_info.file_id}</code>\n\n"
            f"💡 <b>Теперь используйте команду /add_free_post для создания поста</b>",
            parse_mode="HTML"
        )
    else:
        await message.answer(
            "Отправьте мне фото или документ, и я покажу их file_id."
        )


@router.message(Command("list_free_posts"))
async def list_free_posts_handler(message: types.Message):
    """Показать все активные посты для бесплатной рассылки"""
    async with get_db_session() as session:
        try:
            if not await is_admin(message.from_user.id):
                await message.answer("У вас нет прав для этой команды")
                return

            result = await session.execute(
                select(FreeDailyPost)
                .where(FreeDailyPost.is_active == True)
                .order_by(FreeDailyPost.created_at.desc())
            )
            posts = result.scalars().all()

            if not posts:
                await message.answer("📭 Нет активных постов для бесплатной рассылки")
                return

            text = "📋 <b>Активные посты для бесплатной рассылки:</b>\n\n"

            for i, post in enumerate(posts, 1):
                has_photo = "📷" if post.photo_file_id else "📝"
                text += (
                    f"{i}. {has_photo} <b>ID:</b> {post.id}\n"
                    f"   <b>Текст:</b> {post.content[:50]}...\n"
                    f"   <b>Время:</b> {post.scheduled_time}\n"
                    f"   <b>Создан:</b> {post.created_at.strftime('%d.%m.%Y %H:%M')}\n\n"
                )

            await message.answer(text, parse_mode="HTML")

        except Exception as e:
            print(f"❌ Ошибка в /list_free_posts: {e}")
            await message.answer("Произошла ошибка.")


@router.message(Command("delete_free_post"))
async def delete_free_post_handler(message: types.Message):
    """Удалить пост из бесплатной рассылки"""
    async with get_db_session() as session:
        try:
            if not await is_admin(message.from_user.id):
                await message.answer("У вас нет прав для этой команды")
                return

            args = message.text.split()
            if len(args) < 2:
                await message.answer(
                    "Использование: /delete_free_post <ID_поста>\n"
                    "Список постов: /list_free_posts"
                )
                return

            post_id = int(args[1])
            post = await session.get(FreeDailyPost, post_id)

            if not post:
                await message.answer("❌ Пост с таким ID не найден")
                return

            post.is_active = False
            await session.commit()

            await message.answer(f"✅ Пост ID {post_id} деактивирован")

        except ValueError:
            await message.answer("❌ Неверный формат ID. ID должен быть числом.")
        except Exception as e:
            print(f"❌ Ошибка в /delete_free_post: {e}")
            await message.answer("Произошла ошибка.")


@router.message(Command("add_free_post"))
async def start_free_post_creation(message: types.Message, state: FSMContext):
    """Начать создание поста для бесплатной рассылки"""
    try:
        if not await is_admin(message.from_user.id):
            await message.answer("❌ У вас нет прав для этой команды")
            return

        # Создаем клавиатуру для выбора
        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="📷 Добавить фото", callback_data="add_photo"),
            types.InlineKeyboardButton(text="📝 Только текст", callback_data="skip_photo")
        )
        builder.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation"))

        await message.answer(
            "📝 <b>Создание нового поста для бесплатной рассылки</b>\n\nВыберите тип поста:",
            reply_markup=builder.as_markup(),
            parse_mode="HTML"
        )
        await state.set_state(FreePostCreation.waiting_for_photo)

    except Exception as e:
        logger.error(f"❌ Ошибка в start_free_post_creation: {e}")
        await message.answer("❌ Произошла непредвиденная ошибка. Попробуйте позже.")


@router.callback_query(FreePostCreation.waiting_for_photo, F.data == "cancel_creation")
@router.callback_query(FreePostCreation.waiting_for_content, F.data == "cancel_creation")
@router.callback_query(FreePostCreation.confirming_post, F.data == "cancel_creation")
async def cancel_creation(callback: types.CallbackQuery, state: FSMContext):
    """Отмена создания поста из любого состояния"""
    try:
        await safe_edit_message(callback, "❌ Создание поста отменено.")
        await state.clear()
        await callback.answer()
    except Exception as e:
        logger.error(f"❌ Ошибка при отмене создания поста: {e}")
        try:
            await callback.message.answer("❌ Создание поста отменено.")
        except:
            pass
        await state.clear()
        await callback.answer()


async def safe_edit_message(callback: types.CallbackQuery, text: str, reply_markup=None, parse_mode=None):
    """
    Безопасное редактирование сообщения, работает с любым типом контента
    """
    try:
        # Пытаемся определить тип сообщения
        has_photo = callback.message.photo is not None and len(callback.message.photo) > 0
        has_text = callback.message.text is not None

        if has_photo:
            # Для сообщений с фото редактируем подпись
            await callback.message.edit_caption(
                caption=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        elif has_text:
            # Для текстовых сообщений редактируем текст
            await callback.message.edit_text(
                text=text,
                reply_markup=reply_markup,
                parse_mode=parse_mode
            )
        else:
            # Если непонятный тип, отправляем новое сообщение
            raise Exception("Неизвестный тип сообщения")

    except Exception as edit_error:
        logger.warning(f"⚠️ Не удалось отредактировать сообщение: {edit_error}")
        try:
            # Пытаемся отправить новое сообщение
            if has_photo:
                # Если было фото, отправляем текстовое сообщение
                await callback.message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
            else:
                # Иначе просто отправляем новое сообщение
                await callback.message.answer(
                    text,
                    reply_markup=reply_markup,
                    parse_mode=parse_mode
                )
        except Exception as answer_error:
            logger.error(f"❌ Не удалось отправить новое сообщение: {answer_error}")
            # Последняя попытка - просто текст
            try:
                await callback.message.answer("❌ Ошибка отображения. Продолжаем...")
            except:
                pass  # Если ничего не работает, просто продолжаем


@router.callback_query(FreePostCreation.waiting_for_photo, F.data.in_(["add_photo", "skip_photo"]))
async def process_photo_choice(callback: types.CallbackQuery, state: FSMContext):
    """Обработка выбора типа поста"""
    try:
        if callback.data == "skip_photo":
            await state.update_data(photo_file_id=None)
            await callback.message.edit_text(
                "📝 <b>Введите текст поста:</b>\n\nНапишите текст, который будет отправлен в бесплатной рассылке.",
                parse_mode="HTML"
            )
            await state.set_state(FreePostCreation.waiting_for_content)
        else:
            await callback.message.edit_text(
                "📷 <b>Отправьте фото для поста:</b>\n\nПришлите изображение, которое будет добавлено к посту.",
                parse_mode="HTML"
            )
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка в process_photo_choice: {e}")
        await callback.message.edit_text("❌ Произошла ошибка. Попробуйте снова.")
        await state.clear()


@router.message(FreePostCreation.waiting_for_photo, F.photo)
async def process_post_photo(message: types.Message, state: FSMContext):
    """Обработка фото для поста"""
    try:
        photo = message.photo[-1]
        file_id = photo.file_id

        await state.update_data(photo_file_id=file_id)

        await message.answer(
            "✅ <b>Фото получено!</b>\n\n📝 <b>Теперь введите текст поста:</b>",
            parse_mode="HTML"
        )
        await state.set_state(FreePostCreation.waiting_for_content)

    except Exception as e:
        logger.error(f"❌ Ошибка в process_post_photo: {e}")
        await message.answer("❌ Ошибка при обработке фото. Попробуйте еще раз.")


@router.message(FreePostCreation.waiting_for_content, F.text)
async def process_post_content(message: types.Message, state: FSMContext):
    """Обработка текста поста"""
    try:
        content = message.text.strip()

        if not content:
            await message.answer("❌ Текст поста не может быть пустым. Введите текст:")
            return

        await state.update_data(content=content)
        data = await state.get_data()
        await show_post_preview(message, data)
        await state.set_state(FreePostCreation.confirming_post)

    except Exception as e:
        logger.error(f"❌ Ошибка в process_post_content: {e}")
        await message.answer("❌ Ошибка при обработке текста. Попробуйте еще раз.")


async def show_post_preview(message: types.Message, data: dict):
    """Показать превью поста для подтверждения"""
    try:
        content = data.get('content', '')
        photo_file_id = data.get('photo_file_id')

        builder = InlineKeyboardBuilder()
        builder.row(
            types.InlineKeyboardButton(text="✅ Опубликовать", callback_data="publish_post"),
            types.InlineKeyboardButton(text="✏️ Изменить текст", callback_data="edit_content")
        )

        if photo_file_id:
            builder.row(
                types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation")
            )
        else:
            builder.row(types.InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_creation"))

        preview_text = f"👁 <b>Предпросмотр поста:</b>\n\n{content}\n\n{'📷 <i>Пост будет с фото</i>' if photo_file_id else '📝 <i>Текстовый пост</i>'}"

        if photo_file_id:
            await message.answer_photo(
                photo=photo_file_id,
                caption=preview_text,
                reply_markup=builder.as_markup(),
                parse_mode="HTML"
            )
        else:
            await message.answer(preview_text, reply_markup=builder.as_markup(), parse_mode="HTML")

    except Exception as e:
        logger.error(f"❌ Ошибка в show_post_preview: {e}")
        await message.answer("❌ Ошибка при создании превью. Попробуйте еще раз.")


@router.callback_query(FreePostCreation.confirming_post, F.data.in_(["publish_post", "edit_content", "edit_photo"]))
async def handle_confirmation_actions(callback: types.CallbackQuery, state: FSMContext):
    """Обработка действий подтверждения с правильным редактированием"""
    try:
        if callback.data == "publish_post":
            await publish_post(callback, state)
        elif callback.data == "edit_content":
            await safe_edit_message(
                callback,
                "📝 <b>Введите новый текст поста:</b>",
                parse_mode="HTML"
            )
            await state.set_state(FreePostCreation.waiting_for_content)
        elif callback.data == "edit_photo":
            await safe_edit_message(
                callback,
                "📷 <b>Отправьте новое фото для поста:</b>",
                parse_mode="HTML"
            )
            await state.set_state(FreePostCreation.waiting_for_photo)
        await callback.answer()

    except Exception as e:
        logger.error(f"❌ Ошибка в handle_confirmation_actions: {e}")
        # Если не удалось отредактировать, отправляем новое сообщение
        try:
            await callback.message.answer("❌ Произошла ошибка. Попробуйте снова.")
        except:
            pass  # Если и это не сработает, просто игнорируем
        await state.clear()


async def publish_post(callback: types.CallbackQuery, state: FSMContext):
    """Опубликовать пост"""
    async with get_db_session() as session:
        try:
            data = await state.get_data()
            content = data.get('content')
            photo_file_id = data.get('photo_file_id')

            if not content:
                await callback.message.edit_text("❌ Ошибка: текст поста отсутствует.")
                await state.clear()
                return

            new_post = FreeDailyPost(content=content, photo_file_id=photo_file_id)
            session.add(new_post)
            await session.commit()

            if photo_file_id:
                await callback.message.answer_photo(
                    photo=photo_file_id,
                    caption=f"✅ <b>Пост с фото опубликован!</b>\n\n{content}",
                    parse_mode="HTML"
                )
            else:
                await callback.message.answer(f"✅ <b>Текстовый пост опубликован!</b>\n\n{content}", parse_mode="HTML")

            await callback.message.delete()
            await state.clear()
            logger.info(f"✅ Новый пост опубликован (ID: {new_post.id})")

        except Exception as e:
            logger.error(f"❌ Ошибка публикации поста: {e}")
            await session.rollback()
            await callback.message.edit_text("❌ Ошибка при публикации поста. Попробуйте позже.")
            await state.clear()

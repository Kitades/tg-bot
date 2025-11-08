from aiogram import Router, types, F
from aiogram.filters import Command
from datetime import datetime, timedelta
from sqlalchemy import select, and_
from sqlalchemy.orm import Session

from config import SUBSCRIPTION_PRICE, URL
from database.models import User, Subscription, UserSettings, FreeDailyPost
from database.session import get_db_session
from helpers import is_admin, get_admin_ids, notify_admins_about_subscription
from keyboard import main_keyboard, show_tariff_selection, _process_tariff_selection, _check_payment, _content_handler, \
    _content_handler_false, back_main, my_subscription, my_subscription_inactive
from payment import yookassa_service
from servises.daily_poster import FreePostService

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

                user_settings = UserSettings(user_id=user.id, wants_free_posts=True)
                session.add(user_settings)

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

                        if get_admin_ids():
                            try:
                                await notify_admins_about_subscription(
                                    callback.bot,
                                    user,
                                    subscription
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


@router.message(Command("free_subscribe"))
async def free_subscribe_handler(message: types.Message):
    """Подписаться на бесплатную рассылку"""
    telegram_user = message.from_user
    async with get_db_session() as session:
        try:

            user_result = await session.execute(
                select(User).where(User.telegram_id == telegram_user.id)
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
                user_settings = UserSettings(user_id=user.id, wants_free_posts=True)
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


@router.message(Command("add_free_post"))
async def add_free_post_handler(message: types.Message):
    """Добавить пост для бесплатной рассылки (для админов)"""
    async with get_db_session() as session:
        try:
            if not await is_admin(message.from_user.id):
                await message.answer("У вас нет прав для этой команды")
                return

            post_text = message.text.replace('/add_free_post', '').strip()

            if not post_text:
                await message.answer("Использование: /add_free_post текст поста")
                return

            new_post = FreeDailyPost(content=post_text)
            session.add(new_post)
            await session.commit()

            await message.answer("✅ Бесплатный пост добавлен для рассылки!")
        except Exception as e:
            print(f"❌ Ошибка в /add_free_post: {e}")
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
                f"👥 <b>Пользователей с подпиской:</b> {active_subs_count}\n"
                f"🎁 <b>Пользователей без подписки:</b> {total_free_users}\n"
                f"   - Никогда не было подписки: {len(users_without_sub)}\n"
                f"   - Подписка истекла: {len(users_expired_sub)}\n\n"
                f"⏰ <b>Время бесплатной рассылки:</b> 14:00"
            )

            await message.answer(stats_text, parse_mode="HTML")

        except Exception as e:
            print(f"❌ Ошибка в /free_stats: {e}")
            await message.answer("Произошла ошибка. Попробуйте позже.")

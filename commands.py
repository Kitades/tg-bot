from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime, timedelta
from sqlalchemy import select

from config import ADMIN_ID, SUBSCRIPTION_PRICE
from database.models import User, Subscription
from database.session import get_db_session
from keyboard import main_keyboard, show_tariff_selection

router = Router()

# Цены подписок
PRICES = {
    'regular': 8000.00,
    'student': 5000.00
}


@router.message(Command("start"))
async def cmd_start(message: types.Message):
    """Обработчик команды /start"""
    telegram_user = message.from_user

    async with get_db_session() as session:
        try:
            # Ищем пользователя
            from sqlalchemy import select
            result = await session.execute(
                select(User).where(User.telegram_id == telegram_user.id)
            )
            user = result.first()

            if not user:
                # Создаем только если не существует
                user = User(
                    telegram_id=telegram_user.id,
                    username=telegram_user.username,
                    full_name=f"{telegram_user.first_name or ''} {telegram_user.last_name or ''}".strip()
                )
                session.add(user)
                await session.commit()
                print(f"✅ Пользователь создан: {telegram_user.id}")

            await session.commit()
            await session.refresh(user)

            has_active_sub = await check_active_subscription(user.user_id)
            welcome_text = f""

            await message.answer(
                "👋 Добро пожаловать!\n\n"
                f"💰 Участие в информационном канале по стоматологии - {SUBSCRIPTION_PRICE[1]} руб в месяц\n"
                f"🎓 Для студентов и ординаторов - {SUBSCRIPTION_PRICE[0]} руб в месяц",

            )
            if has_active_sub:
                sub_info = await get_subscription_info(user.user_id)
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

            if await check_active_subscription(user.user_id):
                sub_info = await get_subscription_info(user.user_id)
                await callback.message.answer(
                    f"⚠️ У вас уже есть активная подписка!\n\n"
                    f"📅 Действует до: {sub_info['end_date']}\n"
                    f"⏳ Осталось дней: {sub_info['days_left']}"
                )
                await callback.answer()
                return

            await show_tariff_selection(callback, user.user_id)
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
                user_id=user.user_id,
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

            # Здесь будет интеграция с платежной системой
            # payment_url = await create_payment(subscription.id, subscription.price)

            await callback.message.answer(
                f"✅ Выбран тариф: {'Обычный' if tariff_type == 'regular' else 'Студенческий'}\n"
                f"💳 Сумма к оплате: {PRICES[tariff_type]:.2f}₽\n\n"
                "🔗 Ссылка для оплаты: [будет здесь]\n\n"
                "После оплаты нажмите '✅ Проверить оплату'",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                    [InlineKeyboardButton(text="✅ Проверить оплату", callback_data="check_payment")],
                    [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
                ])
            )
            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка выбора тарифа: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()


@router.callback_query(F.data == "check_payment")
async def check_payment(callback: types.CallbackQuery):
    """Проверка оплаты"""
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

            # Ищем pending подписку
            result = await session.execute(
                select(Subscription)
                .where(Subscription.user_id == user.user_id)
                .where(Subscription.status == 'pending')
                .order_by(Subscription.created_at.desc())
            )
            subscription = result.scalar_one_or_none()

            if not subscription:
                await callback.message.answer("❌ Подписка не найдена")
                await callback.answer()
                return

            # Заглушка для проверки платежа
            payment_success = True  # await PaymentService.check_payment(subscription.payment_id)

            if payment_success:
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
                    parse_mode='HTML'
                )

                # Уведомление администратору
                if ADMIN_ID:
                    try:
                        await callback.bot.send_message(
                            ADMIN_ID,
                            f"💸 Новая подписка!\n"
                            f"👤 Пользователь: {user.full_name}\n"
                            f"📧 @{user.username or 'нет'}\n"
                            f"🆔 ID: {user.user_id}\n"
                            f"💳 Тариф: {subscription.plan_name}\n"
                            f"💰 Сумма: {subscription.price:.2f}₽"
                        )
                    except Exception as e:
                        print(f"❌ Ошибка уведомления админу: {e}")

            else:
                await callback.message.answer("⌛ Платеж еще не прошел. Попробуйте позже.")

            await callback.answer()

        except Exception as e:
            print(f"❌ Ошибка проверки платежа: {e}")
            await callback.message.answer("❌ Произошла ошибка")
            await callback.answer()

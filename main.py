import asyncio
import logging
from datetime import datetime, timedelta
from aiogram import types, F
from yookassa import Payment
from config import SUBSCRIPTION_PRICE, ADMIN_ID, cursor, conn, dp, bot
from keyboard import payment_keyboard

# Настройка логирования
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# Обработка кнопки "Купить подписку"
@dp.callback_query(F.data == "buy_subscription")
async def buy_subscription(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Проверяем активную подписку
    cursor.execute("SELECT end_date FROM subscriptions WHERE user_id = ?", (user_id,))
    subscription = cursor.fetchone()

    if subscription and subscription[0]:
        end_date = datetime.strptime(subscription[0], "%Y-%m-%d %H:%M:%S")
        if end_date > datetime.now():
            await callback.message.answer(
                f"⚠️ У вас уже есть активная подписка до {end_date.strftime('%d.%m.%Y')}"
            )
            return

    # Создаем платеж в YooKassa
    payment = Payment.create({
        "amount": {
            "value": str(SUBSCRIPTION_PRICE),
            "currency": "RUB"
        },
        "confirmation": {
            "type": "redirect",
            "return_url": "https://t.me/your_bot"
        },
        "capture": True,
        "description": f"Подписка на 1 месяц для пользователя {callback.from_user.id}",
        "metadata": {
            "user_id": user_id
        }
    })

    # Сохраняем ID платежа в базе
    cursor.execute(
        "UPDATE subscriptions SET payment_id = ? WHERE user_id = ?",
        (payment.id, user_id)
    )
    conn.commit()

    await callback.message.answer(
        "✅ Для оплаты подписки нажмите кнопку ниже:\n"
        f"Сумма: {SUBSCRIPTION_PRICE} руб.\n"
        "После оплаты нажмите 'Я оплатил'",
        reply_markup=payment_keyboard(payment.confirmation.confirmation_url)
    )
    await callback.answer()


# Проверка оплаты
@dp.callback_query(F.data == "check_payment")
async def check_payment(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    # Получаем ID платежа
    cursor.execute("SELECT payment_id FROM subscriptions WHERE user_id = ?", (user_id,))
    payment_id = cursor.fetchone()[0]

    if not payment_id:
        await callback.message.answer("❌ Платеж не найден. Попробуйте начать заново.")
        return

    # Проверяем статус платежа
    payment = Payment.find_one(payment_id)

    if payment.status == "succeeded":
        # Активируем подписку
        start_date = datetime.now()
        end_date = start_date + timedelta(days=30)

        cursor.execute(
            "UPDATE subscriptions SET start_date = ?, end_date = ?, status = ? WHERE user_id = ?",
            (start_date.strftime("%Y-%m-%d %H:%M:%S"),
             end_date.strftime("%Y-%m-%d %H:%M:%S"),
             "active",
             user_id)
        )
        conn.commit()

        await callback.message.answer(
            "🎉 Подписка активирована!\n"
            f"Действует до: {end_date.strftime('%d.%m.%Y')}\n\n"
            "Теперь вам доступен эксклюзивный контент!"
        )

        # Уведомление администратору
        if ADMIN_ID:
            await bot.send_message(
                ADMIN_ID,
                f"💸 Новая подписка!\n"
                f"Пользователь: @{callback.from_user.username}\n"
                f"ID: {user_id}\n"
                f"Сумма: {SUBSCRIPTION_PRICE} руб."
            )
    else:
        await callback.message.answer("⌛ Платеж еще не прошел. Попробуйте позже.")

    await callback.answer()


# Проверка активных подписок
async def check_subscriptions():
    while True:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # Находим подписки, которые истекают через 3 дня
        cursor.execute(
            "SELECT user_id, end_date FROM subscriptions WHERE end_date > ? AND end_date < ?",
            (now, (datetime.now() + timedelta(days=4)).strftime("%Y-%m-%d %H:%M:%S"))
        )
        expiring = cursor.fetchall()

        for user_id, end_date in expiring:
            end_date = datetime.strptime(end_date, "%Y-%m-%d %H:%M:%S")
            try:
                await bot.send_message(
                    user_id,
                    f"⚠️ Ваша подписка истекает {end_date.strftime('%d.%m.%Y')}\n"
                    "Продлите подписку, чтобы сохранить доступ!"
                )
            except Exception as e:
                logger.error(f"Ошибка отправки уведомления: {e}")

        # Деактивируем просроченные подписки
        cursor.execute(
            "UPDATE subscriptions SET status = 'inactive' WHERE end_date < ?",
            (now,)
        )
        conn.commit()

        # Ждем 24 часа до следующей проверки
        await asyncio.sleep(24 * 60 * 60)


# Вебхук для обработки платежей (дополнительно)
async def handle_webhook(request):
    # Для реального проекта нужно добавить обработку вебхуков от YooKassa
    pass


# Запуск бота
async def main():
    # Запускаем фоновую задачу проверки подписок
    asyncio.create_task(check_subscriptions())

    # Запускаем бота
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

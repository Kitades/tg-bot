import logging
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from aiogram.client.session import aiohttp
from yookassa import Payment, Configuration
from sqlalchemy import select, update
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_WEBHOOK_URL, URL, URL_BOT, RETURN_URL
from log.logger import get_logger, log_execution

from database.models import Subscription, WebhookEvent
from database.session import get_db_session

logger = logging.getLogger(__name__)
try:
    Configuration.account_id = YOOKASSA_SHOP_ID
    Configuration.secret_key = YOOKASSA_SECRET_KEY
    logger.info(f"✅ ЮKassa сконфигурирована. Shop ID: {YOOKASSA_SHOP_ID}")
except Exception as e:
    logger.error(f"❌ Ошибка инициализации ЮKassa: {e}")
    raise


class YooKassaService:
    def __init__(self):
        self.base_url = "https://api.yookassa.ru/v3"
        self.auth = aiohttp.BasicAuth(YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY)
        self.headers = {
            'Idempotence-Key': None,
            'Content-Type': 'application/json'
        }


    @staticmethod
    def _ensure_configured():
        """Дополнительная проверка конфигурации"""
        if not Configuration.account_id or not Configuration.secret_key:
            error_msg = "ЮKassa не сконфигурирована. Проверьте YOOKASSA_SHOP_ID и YOOKASSA_SECRET_KEY"
            logger.error(error_msg)
            raise Exception(error_msg)

    @staticmethod
    @log_execution(__name__)
    async def create_subscription(user_id: int, plan_data: dict, email: str = None):
        """Создание подписки с автосписанием"""
        try:
            YooKassaService._ensure_configured()
            logger.info(f"Создание автоподписки для пользователя {user_id}, план: {plan_data['plan_name']}")
            idempotence_key = str(uuid.uuid4())
            payment = Payment.create({
                "amount": {
                    "value": f"{plan_data['price']:.2f}",
                    "currency": "RUB"
                },
                "payment_method_data": {
                    "type": "bank_card"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{URL_BOT}"
                },
                "capture": True,
                "save_payment_method": True,  # Сохраняем метод оплаты для автоплатежей
                "description": f"Подписка: {plan_data['plan_name']}",
                "metadata": {
                    "user_id": user_id,
                    "plan_type": plan_data['plan_type'],
                    "type": "initial_subscription"
                },
                "receipt": {
                    "customer": {
                        "email": email  # или phone
                    },
                    "items": [
                        {
                            "description": "Подписка",
                            "amount": {
                                "value": f"{plan_data['price']:.2f}",
                                "currency": "RUB"
                            },
                            "quantity": 1,
                            "vat_code": 7,
                            "payment_mode": "full_prepayment",
                            "payment_subject": "service"
                        }
                    ]
                }
            }, idempotence_key)

            logger.info(f"Платеж создан: {payment.id}, статус: {payment.status}")
            return payment.confirmation.confirmation_url, payment.id

        except Exception as e:
            logger.error(f"Ошибка создания автоподписки для {user_id}: {str(e)}", exc_info=True)
            raise

    @staticmethod
    @log_execution(__name__)
    async def save_payment_method_from_webhook(payment_data: dict):
        """
        Вызывается вебхуком: сохраняет payment_method в Subscription и создаёт WebhookEvent.
        """
        try:
            payment_id = payment_data.get("id")
            metadata = payment_data.get("metadata", {})
            user_id = metadata.get("user_id")
            # Избегаем дубликатов: если событие уже обработано — выйдем
            async with get_db_session() as session:
                # проверка по WebhookEvent (индекс по payment_id есть)
                result = await session.execute(
                    select(WebhookEvent).where(WebhookEvent.payment_id == payment_id)
                )
                ev = result.scalar_one_or_none()
                if ev:
                    logger.info(f"Вебхук для платежа {payment_id} уже обработан")
                    return

                payment_method = payment_data.get("payment_method") or {}
                payment_method_id = payment_method.get("id")

                # Найдём подписку по payment_id или по metadata (если раньше сохранили)
                result = await session.execute(
                    select(Subscription).where(
                        (Subscription.payment_id == payment_id) | (Subscription.user_id == user_id)
                    )
                )
                subscription = result.scalar_one_or_none()

                now = datetime.utcnow()
                if subscription:
                    # Сохраняем payment_method_id и активируем подписку
                    next_payment_date = now + timedelta(days=30)
                    await session.execute(
                        update(Subscription)
                        .where(Subscription.id == subscription.id)
                        .values(
                            payment_method=payment_method_id,
                            status="active",
                            payment_status="completed",
                            start_date=now if subscription.start_date is None else subscription.start_date,
                            end_date=next_payment_date,
                            next_payment_date=next_payment_date,
                            metadata_json=str(payment_data),
                            updated_at=now,
                            auto_renew=True
                        )
                    )
                    logger.info(f"Подписка {subscription.id} обновлена payment_method={payment_method_id}")
                else:
                    # Если подписки нет — создаём минимальную запись (на всякий случай)
                    sub = Subscription(
                        user_id=user_id,
                        plan_type=metadata.get("plan_type", "regular"),
                        price=subscription.price,
                        plan_name=metadata.get("plan_name", "Обычный"),
                        currency=payment_data.get("amount", {}).get("currency", "RUB"),
                        status="active",
                        payment_status="completed",
                        payment_id=payment_id,
                        payment_method=payment_method_id,
                        auto_renew=True,
                        metadata_json=str(payment_data),
                        start_date=now,
                        end_date=now + timedelta(days=30),
                        next_payment_date=now + timedelta(days=30)
                    )
                    session.add(sub)
                    logger.info(f"Создана подписка для user={user_id}, sub_id={sub.id}")

                # Сохраняем обработанный вебхук (идемпотентность)
                new_ev = WebhookEvent(payment_id=payment_id, event_type=payment_data.get("status", "payment.succeeded"))
                session.add(new_ev)
                logger.info(f"WebHookEvent создан для payment {payment_id}")

        except Exception as e:
            logger.error(f"Ошибка при сохранении payment_method из вебхука: {e}", exc_info=True)
            raise

    @staticmethod
    @log_execution(__name__)
    async def process_auto_payment(user_id: int):
        """Обработка автоматического списания"""
        logger.info(f"Запуск автоплатежа для пользователя {user_id}")

        try:
            YooKassaService._ensure_configured()
            async with get_db_session() as session:
                # Ищем активную подписку с включенным автосписанием
                result = await session.execute(
                    select(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == 'active',
                        Subscription.auto_renew == True,
                        Subscription.payment_method.isnot(None)
                    )
                )
                subscription = result.scalar_one_or_none()

                if not subscription.payment_method:
                    error_msg = f"Нет активной подписки с методом оплаты для пользователя {user_id}"
                    logger.warning(error_msg)
                    raise Exception(error_msg)

                logger.debug(f"Найден метод оплаты: {subscription.payment_method}")

                # Создаем автоплатеж
                payment = Payment.create({
                    "amount": {
                        "value": f"{float(subscription.price):.2f}",
                        "currency": subscription.currency or "RUB"
                    },
                    "payment_method_id": subscription.payment_method,
                    "description": f"Автоматическое списание: {subscription.plan_name}",
                    "metadata": {
                        "user_id": user_id,
                        "type": "auto_payment",
                        "subscription_id": subscription.id
                    },
                    "receipt": {
                        "customer": {
                            "email": subscription.user.email
                        },
                        "items": [
                            {
                                "description": "Подписка",
                                "amount": {
                                    "value": f"{float(subscription.price):.2f}",
                                    "currency": subscription.currency or "RUB"
                                },
                                "quantity": 1,
                                "vat_code": 1,
                                "payment_mode": "full_prepayment",
                                "payment_subject": "service"
                            }
                        ]
                    }
                }, str(uuid.uuid4()))

                logger.info(f"Автоплатеж создан: {payment.id}, статус: {payment.status}")
                return payment.id, payment.status

        except Exception as e:
            logger.error(f"Ошибка автоплатежа для {user_id}: {str(e)}", exc_info=True)
            raise

    @staticmethod
    @log_execution(__name__)
    async def cancel_auto_payments(user_id: int):
        """Отмена всех автоплатежей для пользователя"""
        logger.info(f"Отмена автоплатежей для пользователя {user_id}")

        try:
            async with get_db_session() as session:
                # Отключаем автосписание в подписке
                result = await session.execute(
                    update(Subscription).where(
                        Subscription.user_id == user_id,
                        Subscription.status == 'active'
                    ).values(
                        auto_renew=False,
                        updated_at=datetime.utcnow()
                    )
                )

                if result.rowcount == 0:
                    logger.warning(f"Не найдено активных подписок для отмены у пользователя {user_id}")
                    return False

                logger.info(f"Автоплатежи отменены для пользователя {user_id}")
                return True

        except Exception as e:
            logger.error(f"Ошибка отмены автоплатежей для {user_id}: {str(e)}", exc_info=True)
            return False

    @staticmethod
    async def get_payment_method_id(payment_id: str):
        """Получаем ID привязанного метода оплаты"""
        try:
            YooKassaService._ensure_configured()
            payment = Payment.find_one(payment_id)
            return payment.payment_method.id if payment.payment_method else None
        except Exception as e:
            logger.error(f"Ошибка получения метода оплаты: {e}")
            return None

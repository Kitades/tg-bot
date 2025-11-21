import logging
import uuid
from datetime import datetime

from aiogram.client.session import aiohttp
from yookassa import Payment, Configuration
from sqlalchemy import select, update
from config import YOOKASSA_SHOP_ID, YOOKASSA_SECRET_KEY, YOOKASSA_WEBHOOK_URL, URL, URL_BOT, RETURN_URL
from log.logger import get_logger, log_execution

from database.models import Subscription
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
            payment_id = str(uuid.uuid4())
            payment = Payment.create({
                "amount": {
                    "value": f"{plan_data['price']:.2f}",
                    "currency": "RUB"
                },
                "payment_method_data": {
                    "type": "yoo_money"
                },
                "confirmation": {
                    "type": "redirect",
                    "return_url": f"{RETURN_URL}"
                },
                "capture": True,
                "save_payment_method": True,  # Сохраняем метод оплаты для автоплатежей
                "description": f"Подписка: {plan_data['plan_name']}",
                "metadata": {
                    "user_id": user_id,
                    "email": email or "",
                    "plan_type": plan_data['plan_type'],
                    "type": "initial_subscription"
                }
            }, payment_id)

            logger.info(f"Платеж создан: {payment.id}, статус: {payment.status}")
            return payment.confirmation.confirmation_url, payment.id

        except Exception as e:
            logger.error(f"Ошибка создания автоподписки для {user_id}: {str(e)}", exc_info=True)
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

                if not subscription:
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

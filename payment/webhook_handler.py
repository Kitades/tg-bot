import json
import hmac
import hashlib
from aiohttp import web
from datetime import datetime, timedelta

from config import YOOKASSA_SECRET_KEY, USERNAME_CHANNEL
from database.models import Subscription
from sqlalchemy import select, update
from decimal import Decimal

from log.logger import get_logger

from database.session import get_db_session

logger = get_logger(__name__)


class WebhookHandler:

    def __init__(self):
        self.secret_key = YOOKASSA_SECRET_KEY

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        digest = hmac.new(
            self.secret_key.encode(),
            body,
            hashlib.sha256
        ).hexdigest()

        is_valid = hmac.compare_digest(digest, signature)
        if not is_valid:
            logger.warning(f"Неверная подпись вебхука")

        return is_valid

    async def handle_webhook(self, request):
        try:
            body = await request.read()
            signature = request.headers.get('X-Webhook-Signature', '')

            logger.debug(f"Получен вебхук, подпись: {signature}")

            # if not self.verify_webhook(body, signature):
            #     logger.error("Неверная подпись вебхука")
            #     return web.Response(status=403, text="Invalid signature")

            data = json.loads(body.decode())
            event = data.get('event')
            payment_data = data.get('object', {})
            payment_id = payment_data.get('id')

            logger.info(f"Вебхук: {event} для платежа {payment_id}")

            if event == 'payment.succeeded':
                await self._handle_payment_succeeded(payment_data)
            elif event == 'payment.canceled':
                await self._handle_payment_canceled(payment_data)
            elif event == 'refund.succeeded':
                await self._handle_refund_succeeded(payment_data)
            else:
                logger.debug(f"Необрабатываемое событие: {event}")

            return web.Response(text="OK", status=200)

        except Exception as e:
            logger.error(f"Ошибка обработки вебхука: {str(e)}", exc_info=True)
            return web.Response(status=500, text="Internal error")

    async def handle_webhook_test(self, request):
        return web.Response(text="OK", status=200)

    async def _handle_payment_succeeded(self, payment_data: dict):
        """Обработка успешного платежа"""
        payment_id = payment_data.get('id')
        user_id = payment_data.get('metadata', {}).get('user_id')
        payment_type = payment_data.get('metadata', {}).get('type')
        plan_type = payment_data.get('metadata', {}).get('plan_type')
        amount = Decimal(payment_data.get('amount', {}).get('value', 0))

        logger.info(f"Успешный платеж {payment_id} для пользователя {user_id}, тип: {payment_type}")

        if not user_id:
            logger.warning(f"Нет user_id в платеже {payment_id}")
            return

        try:
            async with get_db_session() as session:
                if payment_type == 'auto_payment':
                    # Обработка автоплатежа - продлеваем подписку
                    subscription_id = payment_data.get('metadata', {}).get('subscription_id')
                    if subscription_id:
                        result = await session.execute(
                            select(Subscription).where(Subscription.id == subscription_id)
                        )
                        subscription = result.scalar_one_or_none()

                        if subscription:
                            new_end_date = datetime.utcnow() + timedelta(days=30)  # Продлеваем на 30 дней
                            await session.execute(
                                update(Subscription).where(
                                    Subscription.id == subscription_id
                                ).values(
                                    end_date=new_end_date,
                                    updated_at=datetime.utcnow()
                                )
                            )
                            logger.info(f"Подписка {subscription_id} продлена до {new_end_date}")

                    logger.info(f"Автоплатеж {payment_id} успешно обработан")

                else:
                    # Обычный платеж (первоначальная подписка)
                    result = await session.execute(
                        select(Subscription).where(Subscription.payment_id == payment_id)
                    )
                    subscription = result.scalar_one_or_none()

                    now = datetime.utcnow()
                    end_date = now + timedelta(days=30)
                    payment_method_id = payment_data.get('payment_method', {}).get('id')

                    plan_name = "Обычный"
                    if plan_type == 'student':
                        plan_name = "Студенческий"

                    if subscription:
                        # Обновляем существующую подписку
                        await session.execute(
                            update(Subscription).where(
                                Subscription.payment_id == payment_id
                            ).values(
                                status='active',
                                payment_status='completed',
                                payment_method=payment_method_id,
                                start_date=now,
                                end_date=end_date,
                                auto_renew=True,
                                metadata_json=json.dumps(payment_data),
                                updated_at=now
                            )
                        )
                        logger.info(f"Подписка обновлена для пользователя {user_id}")
                    else:
                        # Создаем новую подписку
                        subscription = Subscription(
                            user_id=user_id,
                            plan_type=plan_type or 'regular',
                            plan_name=plan_name,
                            price=amount,
                            currency='RUB',
                            status='active',
                            payment_status='completed',
                            payment_id=payment_id,
                            payment_method=payment_method_id,
                            auto_renew=True,
                            metadata_json=json.dumps(payment_data),
                            start_date=now,
                            end_date=end_date
                        )
                        session.add(subscription)
                        logger.info(f"Создана новая подписка для пользователя {user_id}")

                await self._add_user_to_group(user_id)

        except Exception as e:
            logger.error(f"Ошибка обработки успешного платежа {payment_id}: {str(e)}", exc_info=True)

    async def _handle_payment_canceled(self, payment_data: dict):
        """Обработка отмененного платежа"""
        payment_id = payment_data.get('id')
        user_id = payment_data.get('metadata', {}).get('user_id')
        payment_type = payment_data.get('metadata', {}).get('type')

        logger.warning(f"Платеж отменен: {payment_id}, пользователь: {user_id}, тип: {payment_type}")

        if not user_id:
            return

        try:
            async with get_db_session() as session:
                if payment_type == 'auto_payment':
                    logger.info(f"Автоплатеж {payment_id} отменен")

                else:
                    # Отменяем подписку для обычного платежа
                    await session.execute(
                        update(Subscription).where(
                            Subscription.payment_id == payment_id
                        ).values(
                            status='canceled',
                            payment_status='failed',
                            auto_renew=False,
                            updated_at=datetime.utcnow()
                        )
                    )
                    await self._remove_user_from_group(user_id)
                    logger.info(f"Подписка пользователя {user_id} отменена")

        except Exception as e:
            logger.error(f"Ошибка обработки отмененного платежа {payment_id}: {str(e)}", exc_info=True)

    async def _add_user_to_group(self, user_id: int):
        """Добавление пользователя в группу"""
        try:
            from main import bot
            await bot.unban_chat_member(
                chat_id=USERNAME_CHANNEL,
                user_id=user_id
            )
            await bot.send_message(
                chat_id=user_id,
                text="✅ Ваша подписка активирована! Добро пожаловать в закрытую группу!"
            )
            logger.info(f"Пользователь {user_id} добавлен в группу")
        except Exception as e:
            logger.error(f"Ошибка добавления пользователя {user_id} в группу: {str(e)}")

    async def _remove_user_from_group(self, user_id: int):
        """Удаление пользователя из группы"""
        try:
            from main import bot
            await bot.ban_chat_member(
                chat_id=USERNAME_CHANNEL,
                user_id=user_id
            )
            await bot.send_message(
                chat_id=user_id,
                text="❌ Ваша подписка была отменена. Доступ к группе закрыт."
            )
            logger.info(f"Пользователь {user_id} удален из группы")
        except Exception as e:
            logger.error(f"Ошибка удаления пользователя {user_id} из группы: {str(e)}")


webhook_handler = WebhookHandler()

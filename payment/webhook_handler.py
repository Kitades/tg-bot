import json
import hmac
import hashlib
from decimal import Decimal
from datetime import datetime

from aiohttp import web

from config import YOOKASSA_SECRET_KEY, USERNAME_CHANNEL
from log.logger import get_logger

from database.webhook_repository import WebhookRepository
from database.session import get_db_session
from database.models import Subscription

logger = get_logger(__name__)


class WebhookHandler:
    def __init__(self):
        self.secret_key = YOOKASSA_SECRET_KEY
        self.repo = WebhookRepository()

    def verify_webhook(self, body: bytes, signature: str) -> bool:
        """
        Проверяем подпись, ожидаем заголовок X-Webhook-Signature.
        """
        if not signature:
            logger.warning("Нет подписи X-Webhook-Signature")
            return False

        digest = hmac.new(self.secret_key.encode(), body, hashlib.sha256).hexdigest()
        is_valid = hmac.compare_digest(digest, signature)
        if not is_valid:
            logger.warning("Неверная подпись вебхука")
        return is_valid

    async def handle_webhook(self, request: web.Request):
        try:
            body = await request.read()
            signature = request.headers.get("X-Webhook-Signature", "")

            logger.debug(f"Получен вебхук, подпись: {signature}")

            if not self.verify_webhook(body, signature):
                logger.error("Неверная подпись вебхука")
                return web.Response(status=403, text="Invalid signature")

            payload = json.loads(body.decode("utf-8"))
            event = payload.get("event")
            obj = payload.get("object", {}) or {}
            # Для refunds объект может иметь поле payment_id (оригинальный платёж)
            payment_id = obj.get("id") or obj.get("payment_id")

            if not payment_id:
                logger.warning("Webhook без payment id")
                return web.Response(status=400, text="Missing payment id")

            # Попытка пометить обработанным (атомарно). Если уже есть — прекращаем обработку.
            marked = await self.repo.try_mark_processed(payment_id, event)
            if not marked:
                logger.info(f"Webhook {payment_id} уже обработан — пропускаем")
                return web.Response(status=200, text="Already processed")

            logger.info(f"Webhook received: event={event}, payment={payment_id}")

            # Роутинг событий
            if event == "payment.succeeded":
                await self._handle_payment_succeeded(obj)
            elif event == "payment.canceled":
                await self._handle_payment_canceled(obj)
            elif event == "refund.succeeded":
                await self._handle_refund_succeeded(obj)
            else:
                logger.info(f"Unhandled event type: {event}")

            return web.Response(status=200, text="OK")

        except Exception as e:
            logger.exception(f"Ошибка обработки вебхука: {e}")
            return web.Response(status=500, text="Internal error")

    # ----------------------------
    async def _handle_payment_succeeded(self, payment_data: dict):
        payment_id = payment_data.get("id")
        metadata = payment_data.get("metadata", {}) or {}
        user_id = metadata.get("user_id")
        payment_type = metadata.get("type")  # "initial_subscription" или "auto_payment"
        plan_type = metadata.get("plan_type")
        amount = Decimal((payment_data.get("amount") or {}).get("value") or "0")

        if not user_id:
            logger.warning(f"Payment {payment_id} missing user_id in metadata")
            return

        # Автоплатёж — продлеваем по subscription_id из metadata
        if payment_type == "auto_payment":
            subscription_id = metadata.get("subscription_id")
            if subscription_id:
                ok = await self.repo.extend_subscription_by_id(subscription_id, days=30)
                if ok:
                    logger.info(f"Subscription {subscription_id} extended by auto_payment (payment={payment_id})")
                    # Если нужно — можно извлечь user id и уведомить
                    result = await self.repo.get_subscription_by_id(subscription_id)
                    if result:
                        await self._add_user_to_group(result.user_id)
                else:
                    logger.warning(f"auto_payment: subscription {subscription_id} not found (payment={payment_id})")
            else:
                logger.warning(f"auto_payment without subscription_id (payment={payment_id})")
            return

        # Инициативный платеж — создаем новую подписку или активируем существующую платежную запись
        existing = await self.repo.get_subscription_by_payment(payment_id)
        if existing:
            await self.repo.activate_subscription(existing, payment_data)
            logger.info(f"Existing subscription (id={existing.id}) activated for payment {payment_id}")
            await self._add_user_to_group(existing.user_id)
        else:
            sub = await self.repo.create_subscription(user_id, plan_type, payment_id, amount, payment_data)
            logger.info(f"New subscription created id={sub.id} for user {user_id} (payment={payment_id})")
            await self._add_user_to_group(user_id)

    async def _handle_payment_canceled(self, payment_data: dict):
        payment_id = payment_data.get("id")
        if not payment_id:
            logger.warning("payment.canceled without id")
            return
        await self.repo.cancel_subscription_by_payment(payment_id)
        user_id = (payment_data.get("metadata") or {}).get("user_id")
        if user_id:
            await self._remove_user_from_group(user_id)
        logger.info(f"Payment canceled processed for {payment_id}")

    async def _handle_refund_succeeded(self, payment_data: dict):
        # refund object may include 'payment_id' referencing original payment
        original_payment = payment_data.get("payment_id") or (payment_data.get("object") or {}).get("payment_id")
        if not original_payment:
            logger.warning("refund.succeeded without payment_id")
            return
        await self.repo.refund_subscription_by_payment(original_payment)
        subscription = await self.repo.get_subscription_by_payment(original_payment)
        if subscription:
            await self._remove_user_from_group(subscription.user_id)
        logger.info(f"Refund processed for original payment {original_payment}")

    # ----------------------------
    async def _add_user_to_group(self, user_id: int):
        try:
            # lazy import main.bot to avoid circular imports
            from main import bot
            await bot.unban_chat_member(chat_id=USERNAME_CHANNEL, user_id=user_id)
            await bot.send_message(chat_id=user_id, text="✅ Ваша подписка активирована! Добро пожаловать в закрытую группу!")
            logger.info(f"User {user_id} added to group")
        except Exception as e:
            logger.exception(f"Error adding user {user_id} to group: {e}")

    async def _remove_user_from_group(self, user_id: int):
        try:
            from main import bot
            await bot.ban_chat_member(chat_id=USERNAME_CHANNEL, user_id=user_id)
            await bot.send_message(chat_id=user_id, text="❌ Ваша подписка была отменена. Доступ к группе закрыт.")
            logger.info(f"User {user_id} removed from group")
        except Exception as e:
            logger.exception(f"Error removing user {user_id} from group: {e}")


# экспорт экземпляра
webhook_handler = WebhookHandler()

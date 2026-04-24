import json

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from datetime import datetime, timedelta

from database.models import Subscription, WebhookEvent, User
from database.session import get_db_session


class WebhookRepository:

    async def try_mark_processed(self, payment_id: str, event_type: str) -> bool:
        """
        Пытаемся вставить запись в webhook_events.
        Если уникальный ключ уже занят — возвращаем False (уже обработан).
        """
        async with get_db_session() as session:
            try:
                session.add(WebhookEvent(payment_id=payment_id, event_type=event_type))
                await session.commit()
                return True
            except IntegrityError:
                await session.rollback()
                return False

    async def is_processed(self, payment_id: str) -> bool:
        async with get_db_session() as session:
            result = await session.execute(
                select(WebhookEvent).where(WebhookEvent.payment_id == payment_id)
            )
            return result.scalar_one_or_none() is not None

    # ------------------------
    # Получение подписки
    # ------------------------
    async def get_subscription_by_payment(self, payment_id: str):
        async with get_db_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.payment_id == payment_id)
            )
            return result.scalar_one_or_none()

    async def get_subscription_by_id(self, subscription_id: int):
        async with get_db_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            return result.scalar_one_or_none()

    async def get_active_subscription_for_user(self, user_id: int):
        async with get_db_session() as session:
            result = await session.execute(
                select(Subscription).where(
                    Subscription.user_id == user_id,
                    Subscription.status == "active"
                )
            )
            return result.scalar_one_or_none()

    async def create_subscription(self, user_id: int, plan_type: str, payment_id: str, amount,
                                  payment_data: dict):
        async with get_db_session() as session:
            now = datetime.utcnow()
            end = now + timedelta(days=30)

            plan_name = "Обычный"
            if plan_type == "student":
                plan_name = "Студенческий"

            sub = Subscription(
                user_id=user_id,
                plan_type=plan_type or "regular",
                plan_name=plan_name,
                price=amount,
                currency=(payment_data.get("amount", {}) or {}).get("currency", "RUB"),
                status="active",
                payment_status="completed",
                subscription_id=payment_data.get("id"),  # поле subscription_id в твоей модели (если нужно)
                payment_id=payment_id,
                payment_method=(payment_data.get("payment_method") or {}).get("id"),
                auto_renew=True,
                metadata_json=json.dumps(payment_data),
                start_date=now,
                end_date=end,
                updated_at=now
            )
            session.add(sub)
            await session.commit()
            await session.refresh(sub)
            return sub

    # ------------------------
    # Активировать/обновить существующую подписку (по payment_id)
    # ------------------------
    async def activate_subscription(self, subscription_obj: Subscription, payment_data: dict):
        async with get_db_session() as session:
            now = datetime.utcnow()
            await session.execute(
                update(Subscription).where(Subscription.id == subscription_obj.id).values(
                    status="active",
                    payment_status="completed",
                    payment_method=(payment_data.get("payment_method") or {}).get("id"),
                    start_date=now,
                    end_date=now + timedelta(days=30),
                    auto_renew=True,
                    metadata_json=json.dumps(payment_data),
                    updated_at=now
                )
            )
            await session.commit()

    # ------------------------
    # Продление подписки (автоплатёж)
    # ------------------------
    async def extend_subscription_by_id(self, subscription_id: int, days: int = 30) -> bool:
        async with get_db_session() as session:
            result = await session.execute(
                select(Subscription).where(Subscription.id == subscription_id)
            )
            sub = result.scalar_one_or_none()
            if not sub:
                return False

            current_end = sub.end_date or datetime.utcnow()
            new_end = current_end + timedelta(days=days)
            await session.execute(
                update(Subscription).where(Subscription.id == subscription_id).values(
                    end_date=new_end,
                    updated_at=datetime.utcnow()
                )
            )
            await session.commit()
            return True

    # ------------------------
    # Отмена подписки по payment_id (payment.canceled)
    # ------------------------
    async def cancel_subscription_by_payment(self, payment_id: str):
        async with get_db_session() as session:
            await session.execute(
                update(Subscription).where(Subscription.payment_id == payment_id).values(
                    status="canceled",
                    payment_status="failed",
                    auto_renew=False,
                    updated_at=datetime.utcnow()
                )
            )
            await session.commit()

    # ------------------------
    # Refund — отмечаем как refunded и отключаем автопродление
    # ------------------------
    async def refund_subscription_by_payment(self, payment_id: str):
        async with get_db_session() as session:
            await session.execute(
                update(Subscription).where(Subscription.payment_id == payment_id).values(
                    status="refunded",
                    payment_status="refunded",
                    auto_renew=False,
                    updated_at=datetime.utcnow()
                )
            )
            await session.commit()

    # ------------------------
    # Найти user по subscription (если нужно)
    # ------------------------
    async def get_user_by_subscription(self, subscription_id: int):
        async with get_db_session() as session:
            result = await session.execute(
                select(User).where(User.id == subscription_id)
            )
            return result.scalar_one_or_none()

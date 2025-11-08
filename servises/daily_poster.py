from datetime import datetime, timedelta
from aiogram import Bot
from aiogram.types import InputFile

from sqlalchemy.orm import Session
from sqlalchemy import select, and_, or_

from database.models import Subscription, User, UserSettings, FreeDailyPost
from database.session import get_db_session


class FreePostService:

    @staticmethod
    async def get_users_without_subscription() -> list:
        """Получить пользователей БЕЗ активной подписки"""
        current_time = datetime.utcnow()
        async with get_db_session() as session:
            # Подзапрос для пользователей с активными подписками
            subquery = select(Subscription.user_id).where(
                and_(
                    Subscription.status == 'active',
                    Subscription.end_date > current_time
                )
            ).scalar_subquery()

            # Основной запрос: пользователи без активной подписки И с включенной бесплатной рассылкой
            result = await session.execute(
                select(User)
                .join(UserSettings, User.id == UserSettings.user_id)
                .where(
                    and_(
                        User.id.not_in(subquery),  # Нет активной подписки
                        UserSettings.wants_free_posts == True  # Хочет бесплатную рассылку
                    )
                )
            )
        return result.scalars().all()

    @staticmethod
    async def get_users_with_expired_subscription() -> list:
        """Получить пользователей с истекшей подпиской"""
        current_time = datetime.utcnow()
        async with get_db_session() as session:
            # Пользователи у которых была подписка, но она истекла
            result = await session.execute(
                select(User)
                .join(Subscription, User.id == Subscription.user_id)
                .join(UserSettings, User.id == UserSettings.user_id)
                .where(
                    and_(
                        Subscription.status == 'active',
                        Subscription.end_date <= current_time,  # Подписка истекла
                        UserSettings.wants_free_posts == True
                    )
                )
                .distinct()
            )
        return result.scalars().all()

    @staticmethod
    async def get_today_free_post() -> FreeDailyPost:
        """Получить бесплатный пост на сегодня"""
        async with get_db_session() as session:
            result = await session.execute(
                select(FreeDailyPost)
                .where(FreeDailyPost.is_active == True)
                .order_by(FreeDailyPost.created_at.desc())
            )
            return result.scalar()

    @staticmethod
    async def send_free_post_to_user(bot, user: User, post: FreeDailyPost):
        """Отправить бесплатный пост пользователю"""
        try:
            message_text = (
                "📢 <b>БЕСПЛАТНЫЙ КОНТЕНТ</b>\n\n"
                f"{post.content}\n\n"
                "💎 <i>Хотите больше контента? Оформите премиум подписку!</i>"
            )

            if post.photo_path:
                photo = InputFile(post.photo_path)
                await bot.send_photo(
                    chat_id=user.telegram_id,
                    photo=photo,
                    caption=message_text,
                    parse_mode="HTML"
                )
            else:
                await bot.send_message(
                    chat_id=user.telegram_id,
                    text=message_text,
                    parse_mode="HTML"
                )
            return True

        except Exception as e:
            print(f"Ошибка отправки бесплатного поста пользователю {user.telegram_id}: {e}")
            return False

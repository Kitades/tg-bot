import logging
from datetime import datetime, timedelta
from aiogram import Bot
from sqlalchemy import select
from database.session import get_db_session
from database.models import InviteLink

logger = logging.getLogger(__name__)


class InviteService:

    @staticmethod
    async def create_one_time_invite(
            bot: Bot,
            chat_id: str,
            user_id: int,
            expire_hours: int = 24
    ):
        """
        Создает и сохраняет одноразовую ссылку
        Returns: (ссылка, hash_ссылки)
        """
        try:
            # Создаем ссылку через API Telegram
            expire_date = datetime.now() + timedelta(hours=expire_hours)

            invite = await bot.create_chat_invite_link(
                chat_id=chat_id,
                name=f"user_{user_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
                expire_date=expire_date,
                member_limit=1,
                creates_join_request=False
            )

            # Извлекаем hash из ссылки (последняя часть после /+)
            invite_hash = invite.invite_link.split('/')[-1]

            # Сохраняем в БД
            async with get_db_session() as session:
                invite_record = InviteLink(
                    user_id=user_id,
                    chat_id=str(chat_id),
                    invite_link=invite.invite_link,
                    invite_hash=invite_hash,
                    expires_at=expire_date
                )
                session.add(invite_record)
                await session.commit()
                await session.refresh(invite_record)

            logger.info(f"Создана одноразовая ссылка для пользователя {user_id}")
            return invite.invite_link, invite_hash

        except Exception as e:
            logger.error(f"Ошибка создания ссылки: {e}")
            raise

    @staticmethod
    async def mark_invite_as_used(invite_hash: str, user_id: int = None):
        """Помечает ссылку как использованную"""
        async with get_db_session() as session:
            result = await session.execute(
                select(InviteLink).where(InviteLink.invite_hash == invite_hash)
            )
            invite = result.scalar_one_or_none()

            if invite:
                invite.is_used = True
                invite.used_at = datetime.utcnow()
                if user_id:
                    invite.user_id = user_id
                await session.commit()
                logger.info(f"Ссылка {invite_hash} помечена как использованная")

    @staticmethod
    async def revoke_invite_link(bot: Bot, invite_hash: str):
        """Отзывает ссылку (делает недействительной)"""
        try:
            async with get_db_session() as session:
                result = await session.execute(
                    select(InviteLink).where(InviteLink.invite_hash == invite_hash)
                )
                invite = result.scalar_one_or_none()

                if invite and not invite.is_revoked:
                    # Отзываем через API Telegram
                    await bot.revoke_chat_invite_link(
                        chat_id=invite.chat_id,
                        invite_link=invite.invite_link
                    )

                    # Помечаем в БД
                    invite.is_revoked = True
                    await session.commit()
                    logger.info(f"Ссылка {invite_hash} отозвана")

        except Exception as e:
            logger.error(f"Ошибка отзыва ссылки: {e}")

    @staticmethod
    async def get_active_invites(user_id: int):
        """Получает активные ссылки пользователя"""
        async with get_db_session() as session:
            result = await session.execute(
                select(InviteLink).where(
                    InviteLink.user_id == user_id,
                    InviteLink.is_used == False,
                    InviteLink.is_revoked == False,
                    InviteLink.expires_at > datetime.utcnow()
                ).order_by(InviteLink.created_at.desc())
            )
            return result.scalars().all()

    @staticmethod
    async def cleanup_expired_invites(bot: Bot):
        """Очищает истекшие ссылки"""
        async with get_db_session() as session:
            result = await session.execute(
                select(InviteLink).where(
                    InviteLink.expires_at < datetime.utcnow(),
                    InviteLink.is_revoked == False
                )
            )
            expired_invites = result.scalars().all()

            for invite in expired_invites:
                try:
                    await bot.revoke_chat_invite_link(
                        chat_id=invite.chat_id,
                        invite_link=invite.invite_link
                    )
                    invite.is_revoked = True
                except:
                    pass

            await session.commit()
            logger.info(f"Очищено {len(expired_invites)} истекших ссылок")
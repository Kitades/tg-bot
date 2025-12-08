import logging

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import Command
from datetime import datetime, timedelta

from config import USERNAME_CHANNEL
from database.session import get_db_session
from database.models import User
from sqlalchemy import select

from servises.invite_service import InviteService

router = Router()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "get_invite_link")
async def get_invite_command(message: Message):
    """Получение одноразовой ссылки для пользователя с подпиской"""
    user_id = message.from_user.id

    async with get_db_session() as session:
        # Проверяем активную подписку
        result = await session.execute(
            select(User).where(User.telegram_id == user_id)
        )
        user = result.scalar_one_or_none()

        # if not user:
        #     await message.answer("❌ Сначала используйте /start")
        #     return

        # # Здесь проверка активной подписки
        # if not user.has_active_subscription:
        #     await message.answer("❌ У вас нет активной подписки")
        #     return

        # Проверяем, не в группе ли уже пользователь
        try:
            member = await message.bot.get_chat_member(USERNAME_CHANNEL, user_id)
            if member.status in ['member', 'administrator', 'creator']:
                await message.answer(
                    "✅ Вы уже состоите в закрытой группе!\n\n"
                    "Если у вас нет доступа, обратитесь к администратору."
                )
                return
        except:
            pass  # Пользователь не в группе

        try:
            # Создаем одноразовую ссылку
            invite_link, invite_hash = await InviteService.create_one_time_invite(
                bot=message.bot,
                chat_id=USERNAME_CHANNEL,
                user_id=user.id,
                expire_hours=24
            )

            await message.answer(
                f"🔗 <b>Ваша одноразовая ссылка для вступления:</b>\n\n"
                f"<code>{invite_link}</code>\n\n"
                f"📝 <b>Важно:</b>\n"
                f"• Ссылка действует 24 часа\n"
                f"• Можно использовать только один раз\n"
                f"• Не передавайте ссылку другим\n"
                f"• После использования ссылка станет недействительной\n\n"
                f"⚠️ <i>Если ссылка не сработает, напишите администратору</i>",
                parse_mode="HTML"
            )

        except Exception as e:
            logger.error(f"Ошибка создания ссылки: {e}")
            await message.answer("❌ Ошибка при создании ссылки. Попробуйте позже.")

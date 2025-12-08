import logging

from aiogram import Router
from aiogram.types import ChatMemberUpdated
from aiogram.filters import ChatMemberUpdatedFilter, JOIN_TRANSITION, LEAVE_TRANSITION

from config import USERNAME_CHANNEL

router = Router()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.chat_member(ChatMemberUpdatedFilter(JOIN_TRANSITION))
async def on_user_joined(event: ChatMemberUpdated):
    """Когда пользователь вступает в группу"""
    user_id = event.new_chat_member.user.id
    chat_id = event.chat.id

    if str(chat_id) == USERNAME_CHANNEL:
        try:
            await event.bot.send_message(
                chat_id=chat_id,
                text=f"👋 Добро пожаловать, {event.new_chat_member.user.mention}!"
            )

            # Отправляем приветственное сообщение в ЛС
            await event.bot.send_message(
                chat_id=user_id,
                text="🎉 Добро пожаловать в закрытую группу!\n\n"
                     "Теперь у вас есть доступ ко всем материалам."
            )

        except Exception as e:
            logger.error(f"Ошибка приветствия пользователя: {e}")


@router.chat_member(ChatMemberUpdatedFilter(LEAVE_TRANSITION))
async def on_user_left(event: ChatMemberUpdated):
    """Когда пользователь покидает группу"""
    user_id = event.new_chat_member.user.id
    chat_id = event.chat.id

    if str(chat_id) == USERNAME_CHANNEL:
        logger.info(f"Пользователь {user_id} покинул группу {chat_id}")
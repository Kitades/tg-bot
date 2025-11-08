from aiogram import Bot
from aiogram.types import ChatPermissions


class TelegramService:

    @staticmethod
    async def add_user_to_channel(bot: Bot, user_id: int, channel_id: str) -> bool:
        """Добавить пользователя в канал"""
        try:
            # Получаем информацию о пользователе
            user = await bot.get_chat(user_id)

            # Приглашаем пользователя в канал
            invite_link = await bot.create_chat_invite_link(
                chat_id=channel_id,
                member_limit=1
            )

            # Отправляем приглашение пользователю
            await bot.send_message(
                chat_id=user_id,
                text=f"Ваша подписка активирована! Присоединяйтесь к каналу: {invite_link.invite_link}"
            )

            return True

        except Exception as e:
            print(f"Ошибка при добавлении пользователя в канал: {e}")
            return False

    @staticmethod
    async def remove_user_from_channel(bot: Bot, telegram_id: int, channel_id: str) -> bool:
        """Удалить пользователя из канала"""
        try:
            await bot.ban_chat_member(
                chat_id=channel_id,
                user_id=telegram_id
            )

            await bot.unban_chat_member(
                chat_id=channel_id,
                user_id=telegram_id
            )

            return True

        except Exception as e:
            print(f"Ошибка при удалении пользователя из канала: {e}")
            return False

    @staticmethod
    async def unban_from_channel(bot: Bot, telegram_id: int, channel_id: str):
        await bot.unban_chat_member(
            chat_id=channel_id,
            user_id=telegram_id
        )

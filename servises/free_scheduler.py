import asyncio
from datetime import datetime, time
from aiogram import Bot
from servises.daily_poster import FreePostService


class FreePostScheduler:
    def __init__(self, bot: Bot):
        self.bot = bot
        self.is_running = False

    async def start_free_posting(self):
        """Запуск ежедневной бесплатной рассылки"""
        self.is_running = True
        while self.is_running:
            try:
                now = datetime.now()
                target_time = time(14, 00)  # 10:00 утра

                if now.time().hour == target_time.hour and now.time().minute == target_time.minute:
                    await self.send_free_posts()
                    await asyncio.sleep(61)
                else:
                    await asyncio.sleep(60)

            except Exception as e:
                print(f"Ошибка в планировщике бесплатной рассылки: {e}")
                await asyncio.sleep(60)

    async def send_free_posts(self):

        # Получаем пост на сегодня
        post = await FreePostService.get_today_free_post()
        if not post:
            print("Нет активного бесплатного поста для рассылки")
            return
        # Получаем пользователей без подписки
        users_without_sub = await FreePostService.get_users_without_subscription()
        # Также получаем пользователей с истекшей подпиской
        users_expired_sub = await FreePostService.get_users_with_expired_subscription()
        # Объединяем списки
        all_users = list(set(users_without_sub + users_expired_sub))
        print(f"Найдено {len(all_users)} пользователей для бесплатной рассылки")
        success_count = 0
        fail_count = 0

        for user in all_users:
            try:
                success = await FreePostService.send_free_post_to_user(self.bot, user, post)
                if success:
                    success_count += 1
                else:
                    fail_count += 1

                # Задержка чтобы не превысить лимиты Telegram
                await asyncio.sleep(0.1)

            except Exception as e:
                print(f"Ошибка при отправке бесплатного поста пользователю {user.telegram_id}: {e}")
                fail_count += 1

        print(f"Бесплатная рассылка завершена. Успешно: {success_count}, Не удалось: {fail_count}")

    def stop(self):
        """Остановить рассылку"""
        self.is_running = False

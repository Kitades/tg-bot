from aiogram import Router, F
from aiogram.types import CallbackQuery, Message, FSInputFile
from aiogram.filters import Command
import os
import logging

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "offer")
async def send_offer_pdf(callback: CallbackQuery):
    """Отправка PDF файла с офертой"""
    try:
        # Путь к PDF файлу
        pdf_path = "files/offer.pdf"

        # Проверяем существование файла
        if not os.path.exists(pdf_path):
            # Создаем папку если её нет
            os.makedirs(os.path.dirname(pdf_path), exist_ok=True)

            # Если файла нет - предлагаем скачать или создаем заглушку
            await callback.message.answer(
                "📄 <b>Оферта</b>\n\n"
                "Файл оферты временно недоступен.\n"
                "Свяжитесь с администратором для получения документа.",
                parse_mode="HTML"
            )
            await callback.answer()
            return

        # Отправляем PDF файл
        pdf_file = FSInputFile(pdf_path, filename="public_offer.pdf")

        await callback.bot.send_document(
            chat_id=callback.message.chat.id,
            document=pdf_file,
            caption="📄 <b>Публичная оферта</b>\n\n"
                    "Документ содержит условия предоставления услуг.\n"
                    "Рекомендуем ознакомиться перед оплатой подписки.",
            parse_mode="HTML"
        )

        await callback.answer("✅ Оферта отправлена")
        logger.info(f"Пользователь {callback.from_user.id} запросил оферту")

    except Exception as e:
        logger.error(f"Ошибка отправки оферты: {str(e)}", exc_info=True)
        await callback.message.answer(
            "❌ Произошла ошибка при отправке файла.\n"
            "Попробуйте позже или обратитесь в поддержку."
        )
        await callback.answer()

from aiogram import types

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from config import SUBSCRIPTION_PRICE



async def main_keyboard(has_active_sub: bool = False) -> InlineKeyboardMarkup:
    """Создает главную клавиатуру"""
    if has_active_sub:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📊 Моя подписка", callback_data="my_subscription")],
            [InlineKeyboardButton(text="📚 Контент", callback_data="content")],
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])
    else:
        return InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="💳 Купить подписку", callback_data="buy_subscription")],
            [InlineKeyboardButton(text="📋 Тарифы", callback_data="prices")],
            [InlineKeyboardButton(text="🆘 Помощь", callback_data="help")]
        ])


async def show_tariff_selection(callback: types.CallbackQuery, user_id: int):
    """Показывает выбор тарифов"""
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text=f"💳 Обычный - {SUBSCRIPTION_PRICE[1]}₽", callback_data="tariff_regular"),
            InlineKeyboardButton(text=f"🎓 Студент - {SUBSCRIPTION_PRICE[0]}₽", callback_data="tariff_student")
        ],
        [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel")]
    ])

    await callback.message.answer(
        "🎯 <b>Выберите тариф:</b>\n\n"
        f"💳 <b>Обычный</b> - {SUBSCRIPTION_PRICE[1]}₽/месяц\n"
        "• Полный доступ к контенту\n\n"
        f"🎓 <b>Студенческий</b> - {SUBSCRIPTION_PRICE[0]}₽/месяц\n"
        "• Требуется подтверждение статуса\n"
        "• Полный доступ к контенту",
        parse_mode='HTML',
        reply_markup=keyboard
    )

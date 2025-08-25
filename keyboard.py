from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.utils.keyboard import InlineKeyboardBuilder


# Клавиатуры
def main_keyboard():
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="💳 Купить подписку за 8000 руб",
        callback_data="buy_subscription")
    )
    builder.add(InlineKeyboardButton(
        text="💳 Купить подписку за 5000 руб",
        callback_data="buy_subscription")
    )
    builder.add(InlineKeyboardButton(
        text="ℹ️ О подписке",
        callback_data="about")
    )
    builder.add(InlineKeyboardButton(
        text="👨‍💻 Поддержка",
        url="https://t.me/vladimir_potyaev")
    )
    builder.adjust(1)
    return builder.as_markup()


def payment_keyboard(payment_url):
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(
        text="💳 Оплатить",
        url=payment_url)
    )
    builder.add(InlineKeyboardButton(
        text="✅ Я оплатил",
        callback_data="check_payment")
    )
    return builder.as_markup()

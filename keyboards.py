from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from config import settings
from texts import TARIFFS


def main_menu() -> InlineKeyboardMarkup:
    support_url = f"https://t.me/{settings.support_username.replace('@', '')}"
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Купить VPN", callback_data="buy")],
        [InlineKeyboardButton(text="🔑 Мой ключ", callback_data="my_key")],
        [InlineKeyboardButton(text="📲 Инструкция", callback_data="instruction")],
        [InlineKeyboardButton(text="💬 Поддержка", url=support_url)],
    ])


def tariffs_menu() -> InlineKeyboardMarkup:
    rows = []
    for tariff_id, tariff in TARIFFS.items():
        rows.append([
            InlineKeyboardButton(
                text=f"{tariff['title']} — {tariff['price']}",
                callback_data=f"tariff:{tariff_id}",
            )
        ])
    rows.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_menu(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✅ Выдать доступ", callback_data=f"approve:{order_id}"),
            InlineKeyboardButton(text="❌ Отклонить", callback_data=f"reject:{order_id}"),
        ]
    ])

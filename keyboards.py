from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.types import CopyTextButton

from config import settings
from texts import TARIFFS


def main_menu() -> InlineKeyboardMarkup:
    support = settings.support_username.replace("@", "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Купить VPN", callback_data="buy")],
        [InlineKeyboardButton(text="🔑 Мой ключ", callback_data="my_key")],
        [InlineKeyboardButton(text="📲 Инструкция", callback_data="instruction")],
        [InlineKeyboardButton(text="💬 Поддержка", url=f"https://t.me/{support}")],
    ])


def tariffs_menu(trial_available: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for tariff_id, tariff in TARIFFS.items():
        if tariff.get("is_trial") and not trial_available:
            continue

        rows.append([
            InlineKeyboardButton(
                text=f"{tariff['title']} — {tariff['price']}",
                callback_data=f"tariff:{tariff_id}",
            )
        ])

    rows.append([InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def key_menu(vpn_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Скопировать ключ",
                copy_text=CopyTextButton(text=vpn_link),
            )
        ],
        [InlineKeyboardButton(text="📲 Инструкция", callback_data="instruction")],
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")],
    ])


def back_to_main_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Главное меню", callback_data="back_main")]
    ])


def admin_user_menu(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Отключить доступ", callback_data=f"disable_user:{tg_id}")],
    ])

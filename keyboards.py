from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import settings
from texts import BTN_BUY, BTN_INSTRUCTION, BTN_MENU, BTN_MY_KEY, BTN_SUPPORT, TARIFFS


def main_reply_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text=BTN_BUY), KeyboardButton(text=BTN_MY_KEY)],
            [KeyboardButton(text=BTN_INSTRUCTION), KeyboardButton(text=BTN_SUPPORT)],
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def tariffs_inline_keyboard(trial_available: bool) -> InlineKeyboardMarkup:
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

    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def key_inline_keyboard(vpn_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text="📋 Скопировать ключ",
                copy_text=CopyTextButton(text=vpn_link),
            )
        ],
        [InlineKeyboardButton(text="📲 Инструкция", callback_data="instruction")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
    ])


def admin_user_inline_keyboard(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⛔ Отключить доступ", callback_data=f"disable_user:{tg_id}")],
    ])


def support_inline_keyboard() -> InlineKeyboardMarkup:
    support = settings.support_username.replace("@", "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать в поддержку", url=f"https://t.me/{support}")],
    ])

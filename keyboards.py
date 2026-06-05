from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from config import settings
from texts import BTN_ADMIN, BTN_BUY, BTN_INSTRUCTION, BTN_MENU, BTN_MY_KEY, BTN_SUPPORT, TARIFFS

COPY_TEXT_MAX_LENGTH = 256
ADMIN_USERS_PAGE_SIZE = 8


def is_subscription_link(vpn_link: str) -> bool:
    return vpn_link.startswith(("http://", "https://"))


def main_reply_keyboard(include_admin: bool = False) -> ReplyKeyboardMarkup:
    keyboard = [
        [KeyboardButton(text=BTN_BUY), KeyboardButton(text=BTN_MY_KEY)],
        [KeyboardButton(text=BTN_INSTRUCTION), KeyboardButton(text=BTN_SUPPORT)],
    ]
    if include_admin:
        keyboard.append([KeyboardButton(text=BTN_ADMIN)])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="Выберите действие",
    )


def main_menu_inline_keyboard(include_admin: bool = False) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(text=BTN_BUY, callback_data="menu:buy"),
            InlineKeyboardButton(text=BTN_MY_KEY, callback_data="menu:key"),
        ],
        [
            InlineKeyboardButton(text=BTN_INSTRUCTION, callback_data="instruction"),
            InlineKeyboardButton(text=BTN_SUPPORT, callback_data="support"),
        ],
    ]
    if include_admin:
        rows.append([InlineKeyboardButton(text=BTN_ADMIN, callback_data="admin:home")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


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
    is_subscription = is_subscription_link(vpn_link)
    rows: list[list[InlineKeyboardButton]] = []

    if len(vpn_link) <= COPY_TEXT_MAX_LENGTH:
        key_button = InlineKeyboardButton(
            text="📋 Скопировать ссылку" if is_subscription else "📋 Скопировать ключ",
            copy_text=CopyTextButton(text=vpn_link),
        )
    else:
        key_button = InlineKeyboardButton(
            text="📄 Показать ссылку" if is_subscription else "📄 Показать ключ",
            callback_data="show_key",
        )

    rows.append([key_button])
    if is_subscription:
        rows.append([InlineKeyboardButton(text="🌐 Открыть подписку", url=vpn_link)])
    rows.append([InlineKeyboardButton(text="📲 Инструкция", callback_data="instruction")])
    rows.append([InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")])

    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_inline_keyboard(tg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👤 Открыть карточку", callback_data=f"admin:user:{tg_id}:0")],
        [InlineKeyboardButton(text="⛔ Отключить доступ", callback_data=f"disable_user:{tg_id}")],
        [InlineKeyboardButton(text="✅ Включить доступ", callback_data=f"enable_user:{tg_id}")],
    ])


def admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="👥 Все пользователи", callback_data="admin:users:0")],
        [InlineKeyboardButton(text="📊 Статус сервера", callback_data="admin:server")],
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:home")],
    ])


def admin_server_status_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔄 Обновить", callback_data="admin:server")],
        [InlineKeyboardButton(text="🏠 Админ-меню", callback_data="admin:home")],
    ])


def admin_users_keyboard(users: list[tuple], page: int, total: int) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for user in users:
        tg_id, tg_username, _, expire_at, vpn_link, trial_used, _, _ = user
        name = f"@{tg_username}" if tg_username else f"ID {tg_id}"
        status = "🟢" if vpn_link and expire_at else "⚪"
        trial = " 🧪" if trial_used else ""
        rows.append([
            InlineKeyboardButton(
                text=f"{status} {name}{trial}",
                callback_data=f"admin:user:{tg_id}:{page}",
            )
        ])

    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="← Назад", callback_data=f"admin:users:{page - 1}"))
    if (page + 1) * ADMIN_USERS_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="Вперёд →", callback_data=f"admin:users:{page + 1}"))
    if nav:
        rows.append(nav)

    rows.append([InlineKeyboardButton(text="🏠 Админ-меню", callback_data="admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_manage_keyboard(tg_id: int, page: int = 0) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="🔄 Синхронизировать", callback_data=f"admin:sync:{tg_id}:{page}"),
        ],
        [
            InlineKeyboardButton(text="✅ Включить", callback_data=f"enable_user:{tg_id}:{page}"),
            InlineKeyboardButton(text="⛔ Отключить", callback_data=f"disable_user:{tg_id}:{page}"),
        ],
        [
            InlineKeyboardButton(text="🧪 1 день", callback_data=f"admin:issue:{tg_id}:trial_1d:{page}"),
            InlineKeyboardButton(text="🚀 30 дней", callback_data=f"admin:issue:{tg_id}:month_1:{page}"),
        ],
        [
            InlineKeyboardButton(text="🔥 90 дней", callback_data=f"admin:issue:{tg_id}:month_3:{page}"),
            InlineKeyboardButton(text="⭐ 180 дней", callback_data=f"admin:issue:{tg_id}:month_6:{page}"),
        ],
        [
            InlineKeyboardButton(text="👑 365 дней", callback_data=f"admin:issue:{tg_id}:year_1:{page}"),
        ],
        [InlineKeyboardButton(text="← К списку", callback_data=f"admin:users:{page}")],
    ])


def support_inline_keyboard() -> InlineKeyboardMarkup:
    support = settings.support_username.replace("@", "")
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Написать в поддержку", url=f"https://t.me/{support}")],
        [InlineKeyboardButton(text="🏠 Главное меню", callback_data="back_main")],
    ])

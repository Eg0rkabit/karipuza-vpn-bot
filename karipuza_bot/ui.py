from __future__ import annotations

import html
import time
from datetime import datetime

from aiogram.types import (
    CopyTextButton,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    WebAppInfo,
)

from .config import TARIFFS, Tariff
from .remnawave import Subscription

HAPP_ANDROID = "https://play.google.com/store/apps/details?id=com.happproxy"
HAPP_IOS = "https://apps.apple.com/us/app/happ-proxy-utility/id6504287215"
HAPP_WINDOWS = "https://github.com/Happ-proxy/happ-desktop/releases"


def kb(*rows: list[InlineKeyboardButton]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=list(rows))


def button(text: str, callback: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text=text, callback_data=callback)


def main_keyboard(
    is_admin: bool,
    mini_app_url: str = "",
    privacy_url: str = "",
    terms_url: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if mini_app_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🚀 Karipaza Froxy",
                    web_app=WebAppInfo(url=mini_app_url),
                )
            ]
        )
    rows.extend(
        [
            [button("⚡ Подключиться", "plans")],
            [
                button("🔑 Моя подписка", "subscription"),
                button("👤 Профиль", "profile"),
            ],
            [
                button("💳 Тарифы", "plans"),
                button("📲 Инструкция", "instruction"),
            ],
            [
                button("💬 Поддержка", "support"),
            ],
        ]
    )
    if privacy_url or terms_url:
        rows.append([button("📚 Соглашения", "documents")])
    if is_admin:
        rows.append([button("🛠 Админ-панель", "admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_text(first_name: str | None = None) -> str:
    greeting = f", {html.escape(first_name)}" if first_name else ""
    return (
        f"<b>Karipaza Froxy — защищённое подключение для ваших устройств</b>\n\n"
        f"👋 Добро пожаловать в Karipaza Froxy{greeting}!\n\n"
        "Karipaza Froxy помогает сохранить приватность, пользоваться интернетом "
        "стабильнее и подключаться без проблем.\n\n"
        "Наша гордость — твоя безопасность и удобство! 💫"
    )


def plans_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for tariff in TARIFFS:
        rows.append(
            [
                button(
                    f"{tariff.title} · {tariff.price_rub} ₽ · −{tariff.discount_percent}%",
                    f"plan:{tariff.code}",
                )
            ]
        )
    rows.append([button("Главное меню", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_text() -> str:
    return (
        "<b>Тарифы Karipaza Froxy</b>\n\n"
        "Без ограничений по трафику и до 5 личных устройств "
        "на одну подписку.\n\n"
        "Выберите срок:"
    )


def plan_text(tariff: Tariff) -> str:
    daily = tariff.price_rub / tariff.days
    return (
        f"<b>{html.escape(tariff.title)}</b>\n\n"
        f"Новая цена: <b>{tariff.price_rub} ₽</b> "
        f"<s>{tariff.previous_price_rub} ₽</s>\n"
        f"Скидка: <b>{tariff.discount_percent}%</b>\n"
        f"Срок: <b>{tariff.days} дней</b>\n"
        f"В день: <b>около {daily:.0f} ₽</b>\n"
        "Трафик: <b>без ограничений</b>\n"
        "Устройства: <b>до 5</b>\n\n"
        "После оплаты администратор проверит платёж, "
        "и бот автоматически выдаст подписку.\n\n"
        "Нажимая «Принять и оформить», вы подтверждаете, что ознакомились "
        "с Пользовательским соглашением и Политикой конфиденциальности."
    )


def plan_keyboard(
    tariff: Tariff,
    privacy_url: str = "",
    terms_url: str = "",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if privacy_url or terms_url:
        rows.append([button("📚 Соглашения", f"documents:plan:{tariff.code}")])
    rows.extend(
        [
            [button("✅ Принять и оформить", f"order:create:{tariff.code}")],
            [button("Назад к тарифам", "plans")],
            [button("Главное меню", "home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def documents_text() -> str:
    return (
        "<b>Соглашения Karipaza Froxy</b>\n\nВыберите документ, который хотите открыть:"
    )


def documents_keyboard(
    privacy_url: str = "",
    terms_url: str = "",
    back_callback: str = "home",
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if privacy_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="🔒 Политика конфиденциальности",
                    url=privacy_url,
                )
            ]
        )
    if terms_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📄 Пользовательское соглашение",
                    url=terms_url,
                )
            ]
        )
    rows.append([button("Назад", back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_text(order, payment_details: str) -> str:
    payment = (
        html.escape(payment_details)
        if payment_details
        else "Реквизиты пока не настроены. Напишите в поддержку."
    )
    return (
        f"<b>Заказ #{order['id']}</b>\n\n"
        f"Тариф: <b>{html.escape(order['title'])}</b>\n"
        f"К оплате: <b>{order['amount_rub']} ₽</b>\n\n"
        f"<b>Реквизиты</b>\n{payment}\n\n"
        "После оплаты нажмите «Я оплатил» и отправьте чек "
        "или сообщение с данными платежа."
    )


def order_keyboard(order_id: int, payment_ready: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if payment_ready:
        rows.append([button("Я оплатил", f"order:paid:{order_id}")])
    rows.extend(
        [
            [button("Поддержка", "support")],
            [button("Главное меню", "home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def format_date(timestamp: int) -> str:
    if not timestamp:
        return "не указано"
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


def format_size(value: int) -> str:
    size = float(value)
    for unit in ("Б", "КБ", "МБ", "ГБ", "ТБ"):
        if size < 1024 or unit == "ТБ":
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} ТБ"


def days_left(timestamp: int) -> int:
    return max(0, (timestamp - int(time.time()) + 86399) // 86400)


def subscription_text(subscription: Subscription | None, local_user=None) -> str:
    if subscription:
        status_map = {
            "ACTIVE": "активна",
            "DISABLED": "доступ на паузе",
            "LIMITED": "лимит исчерпан",
            "EXPIRED": "закончилась",
        }
        status = status_map.get(subscription.status, subscription.status.lower())
        note = (
            "Доступ сейчас на паузе. Подписка сохранена, но подключение временно выключено администратором."
            if subscription.status == "DISABLED"
            else "Нажмите кнопку ниже, чтобы добавить или обновить подписку в Happ."
        )
        return (
            "<b>Моя подписка</b>\n\n"
            f"Статус: <b>{html.escape(status)}</b>\n"
            f"Активна до: <b>{format_date(subscription.expire_at)}</b>\n"
            f"Осталось: <b>{days_left(subscription.expire_at)} дн.</b>\n"
            f"Использовано: <b>{format_size(subscription.traffic_used)}</b>\n\n"
            "Можно подключить: <b>до 5 личных устройств</b>\n\n"
            f"{note}"
        )

    if local_user and local_user["subscription_url"]:
        return (
            "<b>Моя подписка</b>\n\n"
            "Панель временно недоступна, показываю последние сохранённые данные.\n\n"
            f"Активна до: <b>{format_date(int(local_user['expire_at']))}</b>"
        )

    return (
        "<b>Подписки пока нет</b>\n\n"
        "Выберите тариф, оплатите его и дождитесь подтверждения администратора."
    )


def subscription_keyboard(
    subscription_url: str | None, has_subscription: bool
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if subscription_url:
        rows.append(
            [
                InlineKeyboardButton(
                    text="📋 Скопировать ссылку",
                    copy_text=CopyTextButton(text=subscription_url),
                )
            ]
        )
        rows.append([button("▣ QR-код", "subscription:qr")])
        rows.append([button("🔄 Обновить данные", "subscription")])
    rows.append(
        [
            button(
                "💳 Продлить подписку" if has_subscription else "💳 Выбрать тариф",
                "plans",
            )
        ]
    )
    rows.append([button("📲 Инструкция", "instruction")])
    rows.append([button("🏠 Главное меню", "home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def profile_text(
    first_name: str | None,
    username: str | None,
    subscription: Subscription | None,
    local_user=None,
) -> str:
    name = first_name or username or "не указано"
    username_text = f"@{username}" if username else "не указан"
    if subscription:
        status = {
            "ACTIVE": "активна",
            "DISABLED": "доступ на паузе",
            "LIMITED": "лимит исчерпан",
            "EXPIRED": "закончилась",
        }.get(subscription.status, subscription.status.lower())
        expire_at = format_date(subscription.expire_at)
        traffic = format_size(subscription.traffic_used)
    elif local_user and local_user["subscription_url"]:
        status = "последние сохранённые данные"
        expire_at = format_date(int(local_user["expire_at"]))
        traffic = format_size(int(local_user["traffic_used"] or 0))
    else:
        status = "подписки пока нет"
        expire_at = "не указано"
        traffic = "0 Б"

    return (
        "<b>Профиль Karipaza Froxy</b>\n\n"
        f"Имя: <b>{html.escape(str(name))}</b>\n"
        f"Username: <b>{html.escape(username_text)}</b>\n\n"
        f"Статус: <b>{html.escape(status)}</b>\n"
        f"Подписка до: <b>{expire_at}</b>\n"
        f"Использовано: <b>{traffic}</b>"
    )


def profile_keyboard(has_subscription: bool) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if has_subscription:
        rows.append([button("🔑 Моя подписка", "subscription")])
    rows.extend(
        [
            [button("💳 Тарифы", "plans")],
            [button("💬 Поддержка", "support")],
            [button("🏠 Главное меню", "home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def instruction_text() -> str:
    return (
        "<b>Как подключить Karipaza Froxy</b>\n\n"
        "1. Установите приложение Happ для своего устройства.\n"
        "2. Откройте в боте раздел «Моя подписка».\n"
        "3. Скопируйте ссылку или откройте QR-код.\n"
        "4. Добавьте подписку в Happ и нажмите кнопку подключения.\n\n"
        "Одну подписку можно добавить максимум на 5 личных устройств. "
        "Новые серверы и изменения "
        "появятся после обычного обновления профиля."
    )


def instruction_keyboard() -> InlineKeyboardMarkup:
    return kb(
        [InlineKeyboardButton(text="Android", url=HAPP_ANDROID)],
        [InlineKeyboardButton(text="iPhone / iPad", url=HAPP_IOS)],
        [InlineKeyboardButton(text="Windows / macOS / Linux", url=HAPP_WINDOWS)],
        [button("Моя подписка", "subscription")],
        [button("Главное меню", "home")],
    )


def support_text() -> str:
    return (
        "<b>Поддержка</b>\n\n"
        "Опишите проблему одним сообщением. Можно написать, "
        "на каком устройстве и через какую сеть не работает подключение.\n\n"
        "Ответ администратора придёт прямо в этот чат."
    )


def support_keyboard() -> InlineKeyboardMarkup:
    return kb(
        [button("Создать обращение", "support:new")],
        [button("Главное меню", "home")],
    )


def admin_home_text(stats: dict[str, int], vpn_ok: bool) -> str:
    return (
        "<b>Админ-панель</b>\n\n"
        f"Пользователей: <b>{stats['users']}</b>\n"
        f"Активных подписок: <b>{stats['active']}</b>\n"
        f"Платежей на проверке: <b>{stats['orders']}</b>\n"
        f"Открытых обращений: <b>{stats['tickets']}</b>\n"
        f"Remnawave: <b>{'работает' if vpn_ok else 'не настроен / недоступен'}</b>"
    )


def admin_home_keyboard() -> InlineKeyboardMarkup:
    return kb(
        [button("Платежи", "admin:orders")],
        [button("Поддержка", "admin:tickets")],
        [button("Пользователи", "admin:users:0")],
        [button("Обновить", "admin:home")],
        [button("Главное меню", "home")],
    )


def payment_review_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return kb(
        [
            button("Подтвердить", f"admin:order:approve:{order_id}"),
            button("Отклонить", f"admin:order:reject:{order_id}"),
        ],
        [button("Админ-панель", "admin:home")],
    )


def ticket_admin_keyboard(ticket_id: int) -> InlineKeyboardMarkup:
    return kb(
        [button("Ответить", f"admin:ticket:reply:{ticket_id}")],
        [button("Закрыть", f"admin:ticket:close:{ticket_id}")],
        [button("Админ-панель", "admin:home")],
    )


def admin_orders_text(orders) -> str:
    if not orders:
        return "<b>Платежи</b>\n\nНовых платежей на проверке нет."
    lines = ["<b>Платежи на проверке</b>", ""]
    for order in orders:
        name = order["first_name"] or order["username"] or f"ID {order['tg_id']}"
        lines.append(
            f"#{order['id']} · {html.escape(str(name))} · "
            f"{order['amount_rub']} ₽ · {html.escape(order['title'])}"
        )
    lines.append("\nОткройте нужный платёж:")
    return "\n".join(lines)


def admin_orders_keyboard(orders) -> InlineKeyboardMarkup:
    rows = [
        [
            button(
                f"Заказ #{order['id']} · {order['amount_rub']} ₽",
                f"admin:order:view:{order['id']}",
            )
        ]
        for order in orders
    ]
    rows.extend(
        [
            [button("Обновить", "admin:orders")],
            [button("Назад", "admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_order_text(order) -> str:
    name = order["first_name"] or "без имени"
    username = f"@{order['username']}" if order["username"] else "не указан"
    proof = (order["proof_text"] or "чек приложен отдельным сообщением")[:2500]
    return (
        f"<b>Заказ #{order['id']}</b>\n\n"
        f"Пользователь: <b>{html.escape(str(name))}</b>\n"
        f"Username: {html.escape(username)}\n"
        f"Telegram ID: <code>{order['tg_id']}</code>\n"
        f"Тариф: <b>{html.escape(order['title'])}</b>\n"
        f"Сумма: <b>{order['amount_rub']} ₽</b>\n"
        f"Статус: <b>{html.escape(order['status'])}</b>\n\n"
        f"Данные платежа: {html.escape(str(proof))}"
    )


def admin_tickets_text(tickets) -> str:
    if not tickets:
        return "<b>Поддержка</b>\n\nОткрытых обращений нет."
    lines = ["<b>Открытые обращения</b>", ""]
    for ticket in tickets:
        name = ticket["first_name"] or ticket["username"] or f"ID {ticket['tg_id']}"
        lines.append(f"#{ticket['id']} · {html.escape(str(name))}")
    return "\n".join(lines)


def admin_tickets_keyboard(tickets) -> InlineKeyboardMarkup:
    rows = [
        [button(f"Обращение #{ticket['id']}", f"admin:ticket:view:{ticket['id']}")]
        for ticket in tickets
    ]
    rows.extend(
        [
            [button("Обновить", "admin:tickets")],
            [button("Назад", "admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_ticket_text(ticket) -> str:
    name = ticket["first_name"] or "без имени"
    username = f"@{ticket['username']}" if ticket["username"] else "не указан"
    return (
        f"<b>Обращение #{ticket['id']}</b>\n\n"
        f"Пользователь: <b>{html.escape(str(name))}</b>\n"
        f"Username: {html.escape(username)}\n"
        f"Telegram ID: <code>{ticket['tg_id']}</code>\n"
        f"Статус: <b>{html.escape(ticket['status'])}</b>"
    )


def admin_users_text(users, page: int, total: int) -> str:
    if not users:
        return "<b>Пользователи</b>\n\nПользователей пока нет."
    lines = [f"<b>Пользователи</b> · всего {total}", ""]
    for user in users:
        name = user["first_name"] or user["username"] or f"ID {user['tg_id']}"
        status = "активна" if user["vpn_status"] == "ACTIVE" else "нет подписки"
        lines.append(f"{html.escape(str(name))} · {status}")
    lines.append(f"\nСтраница {page + 1}")
    return "\n".join(lines)


def admin_users_keyboard(
    users, page: int, total: int, page_size: int
) -> InlineKeyboardMarkup:
    rows = [
        [
            button(
                str(user["first_name"] or user["username"] or user["tg_id"])[:30],
                f"admin:user:{user['tg_id']}",
            )
        ]
        for user in users
    ]
    nav: list[InlineKeyboardButton] = []
    if page > 0:
        nav.append(button("Назад", f"admin:users:{page - 1}"))
    if (page + 1) * page_size < total:
        nav.append(button("Дальше", f"admin:users:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([button("Админ-панель", "admin:home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_user_text(user) -> str:
    username = f"@{user['username']}" if user["username"] else "не указан"
    status_map = {
        "ACTIVE": "активна",
        "DISABLED": "доступ на паузе",
        "LIMITED": "лимит исчерпан",
        "EXPIRED": "закончилась",
        "NONE": "нет подписки",
    }
    status = status_map.get(str(user["vpn_status"]), str(user["vpn_status"]))
    return (
        "<b>Пользователь</b>\n\n"
        f"Имя: <b>{html.escape(str(user['first_name'] or 'не указано'))}</b>\n"
        f"Username: {html.escape(username)}\n"
        f"Telegram ID: <code>{user['tg_id']}</code>\n"
        f"Статус доступа: <b>{html.escape(status)}</b>\n"
        f"Подписка до: <b>{format_date(int(user['expire_at']))}</b>\n"
        f"Использовано: <b>{format_size(int(user['traffic_used']))}</b>"
    )


def admin_user_keyboard(tg_id: int, has_subscription: bool) -> InlineKeyboardMarkup:
    rows = [[button("Добавить 30 дней", f"admin:user:grant:{tg_id}")]]
    if has_subscription:
        rows.append(
            [
                button("Включить", f"admin:user:enable:{tg_id}"),
                button("Отключить", f"admin:user:disable:{tg_id}"),
            ]
        )
    rows.extend(
        [
            [button("К списку", "admin:users:0")],
            [button("Админ-панель", "admin:home")],
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)

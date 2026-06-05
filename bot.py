import asyncio
import html
import logging
import os
import shutil
import socket
import time
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

import database as db
from config import settings, validate_settings
from keyboards import (
    ADMIN_USERS_PAGE_SIZE,
    admin_panel_keyboard,
    admin_server_status_keyboard,
    admin_user_manage_keyboard,
    admin_user_inline_keyboard,
    admin_users_keyboard,
    key_inline_keyboard,
    main_reply_keyboard,
    support_inline_keyboard,
    tariffs_inline_keyboard,
)
from marzban_api import (
    MarzbanError,
    create_or_update_user,
    disable_user,
    enable_user as enable_marzban_user,
    get_active_user,
    get_token,
    get_user_data,
)
from texts import (
    BTN_ADMIN,
    BTN_BUY,
    BTN_INSTRUCTION,
    BTN_MY_KEY,
    BTN_SUPPORT,
    INSTRUCTION_TEXT,
    TARIFFS,
    WELCOME_TEXT,
)

logging.basicConfig(level=logging.INFO)

ACTION_COOLDOWN_SECONDS = 0.8
HEAVY_ACTION_COOLDOWN_SECONDS = 4.0
GENERIC_ERROR_TEXT = "❌ Ошибка, обратитесь к админу."
SUBSCRIPTION_HELP_TEXT = (
    "Это ссылка подписки: её можно добавить в Hiddify один раз, "
    "а потом просто обновлять профиль."
)

user_action_at: dict[int, float] = {}
heavy_action_at: dict[int, float] = {}
active_key_requests: set[int] = set()

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def main_keyboard_for(user_id: int):
    return main_reply_keyboard(include_admin=is_admin(user_id))


def format_date(timestamp: int) -> str:
    if not timestamp:
        return "неизвестно"
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


def display_user(username: str | None, tg_id: int) -> str:
    if username:
        return f"@{username}"
    return f"ID {tg_id}"


def is_subscription_link(vpn_link: str) -> bool:
    return vpn_link.startswith(("http://", "https://"))


def format_size(size_bytes: int) -> str:
    value = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_duration(seconds: float) -> str:
    seconds = int(seconds)
    days, seconds = divmod(seconds, 86400)
    hours, seconds = divmod(seconds, 3600)
    minutes, _ = divmod(seconds, 60)

    parts: list[str] = []
    if days:
        parts.append(f"{days} д")
    if hours:
        parts.append(f"{hours} ч")
    if minutes or not parts:
        parts.append(f"{minutes} мин")
    return " ".join(parts)


def read_uptime() -> str:
    try:
        with open("/proc/uptime", encoding="utf-8") as file:
            uptime_seconds = float(file.read().split()[0])
        return format_duration(uptime_seconds)
    except Exception:
        return "неизвестно"


def read_memory_status() -> str:
    try:
        values: dict[str, int] = {}
        with open("/proc/meminfo", encoding="utf-8") as file:
            for line in file:
                key, raw_value = line.split(":", 1)
                values[key] = int(raw_value.strip().split()[0]) * 1024

        total = values["MemTotal"]
        available = values.get("MemAvailable", 0)
        used = max(0, total - available)
        percent = used / total * 100 if total else 0
        return f"{format_size(used)} / {format_size(total)} ({percent:.0f}%)"
    except Exception:
        return "неизвестно"


def read_disk_status() -> str:
    try:
        disk = shutil.disk_usage("/")
        percent = disk.used / disk.total * 100 if disk.total else 0
        return f"{format_size(disk.used)} / {format_size(disk.total)} ({percent:.0f}%)"
    except Exception:
        return "неизвестно"


def read_load_status() -> str:
    try:
        load_1, load_5, load_15 = os.getloadavg()
        return f"{load_1:.2f} / {load_5:.2f} / {load_15:.2f}"
    except Exception:
        return "неизвестно"


def resolve_host(host: str) -> tuple[list[str], str | None]:
    if not host:
        return [], "домен не задан"

    try:
        _, _, addresses = socket.gethostbyname_ex(host)
    except Exception as e:
        return [], str(e)

    return sorted(set(addresses)), None


async def marzban_status_text() -> str:
    try:
        await asyncio.wait_for(get_token(), timeout=8)
    except Exception as e:
        return f"❌ ошибка: <code>{short_error_text(e, 500)}</code>"

    return "✅ доступен"


async def dns_status_text() -> str:
    host = settings.subscription_check_host
    addresses, error = await asyncio.to_thread(resolve_host, host)
    if error:
        return f"❌ {html.escape(host)} не найден: <code>{html.escape(error)}</code>"

    expected_ip = settings.public_host
    addresses_text = ", ".join(addresses)
    if expected_ip and expected_ip not in addresses:
        return f"⚠️ {html.escape(host)} → <code>{html.escape(addresses_text)}</code>, ожидали <code>{html.escape(expected_ip)}</code>"

    return f"✅ {html.escape(host)} → <code>{html.escape(addresses_text)}</code>"


async def server_status_text() -> str:
    marzban_status, dns_status = await asyncio.gather(
        marzban_status_text(),
        dns_status_text(),
    )

    return (
        "📊 <b>Статус сервера</b>\n\n"
        f"Бот: <b>✅ работает</b>\n"
        f"Marzban: {marzban_status}\n"
        f"DNS подписки: {dns_status}\n\n"
        f"Uptime: <b>{read_uptime()}</b>\n"
        f"Нагрузка 1/5/15 мин: <b>{read_load_status()}</b>\n"
        f"RAM: <b>{read_memory_status()}</b>\n"
        f"Диск: <b>{read_disk_status()}</b>\n"
        f"Пользователей в базе: <b>{db.count_users()}</b>\n\n"
        f"Обновлено: <b>{datetime.now().strftime('%d.%m.%Y %H:%M')}</b>"
    )


def parse_callback_parts(data: str, expected: int) -> list[str]:
    parts = data.split(":")
    if len(parts) < expected:
        raise ValueError("Некорректные данные кнопки")
    return parts


def is_rate_limited(
    user_id: int,
    cooldown: float = ACTION_COOLDOWN_SECONDS,
    bucket: dict[int, float] | None = None,
) -> bool:
    if bucket is None:
        bucket = user_action_at

    now = time.monotonic()
    last_action_at = bucket.get(user_id, 0)
    if now - last_action_at < cooldown:
        return True

    bucket[user_id] = now
    return False


async def answer_if_rate_limited(
    callback: CallbackQuery,
    cooldown: float = ACTION_COOLDOWN_SECONDS,
    *,
    heavy: bool = False,
) -> bool:
    bucket = heavy_action_at if heavy else user_action_at
    if not is_rate_limited(callback.from_user.id, cooldown, bucket):
        return False

    await callback.answer("Подождите пару секунд.", show_alert=False)
    return True


async def message_is_rate_limited(message: Message, cooldown: float = ACTION_COOLDOWN_SECONDS) -> bool:
    return is_rate_limited(message.from_user.id, cooldown)


def short_error_text(error: Exception, limit: int = 2500) -> str:
    text = str(error) or error.__class__.__name__
    if len(text) > limit:
        text = text[:limit] + "..."
    return html.escape(text)


async def notify_admins_about_error(
    error: Exception,
    *,
    action: str,
    tg_id: int | None = None,
    username: str | None = None,
) -> None:
    user_line = ""
    if tg_id is not None:
        user_line = (
            f"\nПользователь: {display_user(username, tg_id)}\n"
            f"Telegram ID: <code>{tg_id}</code>\n"
        )

    text = (
        "⚠️ <b>Ошибка в боте</b>\n\n"
        f"Действие: <b>{html.escape(action)}</b>"
        f"{user_line}\n"
        f"Тип: <code>{html.escape(error.__class__.__name__)}</code>\n"
        f"Ошибка:\n<code>{short_error_text(error)}</code>"
    )

    for admin_id in settings.admin_ids:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            logging.exception("Failed to notify admin %s about error", admin_id)


async def edit_or_answer(message: Message, text: str, reply_markup=None) -> None:
    try:
        await message.edit_text(text, reply_markup=reply_markup)
    except TelegramBadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        await message.answer(text, reply_markup=reply_markup)


async def sync_active_user_from_marzban(tg_id: int, tg_username: str | None) -> bool:
    active_user = await get_active_user(tg_id)
    if not active_user:
        return False

    marzban_username, expire_at, vpn_link = active_user
    db.save_vpn_user(
        tg_id=tg_id,
        tg_username=tg_username,
        marzban_username=marzban_username,
        expire_at=expire_at,
        vpn_link=vpn_link,
        mark_trial_used=False,
    )
    return True


def admin_home_text() -> str:
    total = db.count_users()
    return (
        "🛠 <b>Админ-панель Karipuza VPN</b>\n\n"
        f"Пользователей в базе: <b>{total}</b>\n\n"
        "Выберите раздел:"
    )


def admin_users_text(page: int, total: int) -> str:
    pages = max(1, (total + ADMIN_USERS_PAGE_SIZE - 1) // ADMIN_USERS_PAGE_SIZE)
    return (
        "👥 <b>Пользователи</b>\n\n"
        f"Всего: <b>{total}</b>\n"
        f"Страница: <b>{page + 1}/{pages}</b>\n\n"
        "🟢 есть доступ в базе, ⚪ доступа в базе нет, 🧪 тест уже использован."
    )


async def admin_user_text(tg_id: int) -> str:
    user = db.get_user(tg_id)
    if not user:
        local_text = "Локально: <b>пользователь не найден в базе бота</b>"
        tg_username = None
        marzban_username = f"tg_{tg_id}"
        expire_at = 0
        vpn_link = None
        trial_used = False
    else:
        _, tg_username, marzban_username, expire_at, vpn_link, trial_used, created_at, updated_at = user
        local_text = (
            "Локально в боте:\n"
            f"• Ссылка доступа: <b>{'есть' if vpn_link else 'нет'}</b>\n"
            f"• Активен до: <b>{format_date(expire_at)}</b>\n"
            f"• Тест: <b>{'использован' if trial_used else 'не использован'}</b>\n"
            f"• Обновлён: <b>{format_date(updated_at)}</b>"
        )

    try:
        marzban_user = await get_user_data(tg_id)
    except MarzbanError as e:
        marzban_text = f"Marzban: <b>ошибка</b>\n<code>{html.escape(str(e))}</code>"
    else:
        if not marzban_user:
            marzban_text = "Marzban: <b>пользователь не найден</b>"
        else:
            remote_status = html.escape(str(marzban_user.get("status") or "unknown"))
            remote_expire = int(marzban_user.get("expire") or 0)
            remote_links = marzban_user.get("links") or []
            remote_subscription = marzban_user.get("subscription_url")
            marzban_text = (
                "Marzban:\n"
                f"• Username: <code>{html.escape(str(marzban_user.get('username') or marzban_username))}</code>\n"
                f"• Статус: <b>{remote_status}</b>\n"
                f"• Активен до: <b>{format_date(remote_expire)}</b>\n"
                f"• Подписка: <b>{'есть' if remote_subscription else 'нет'}</b>\n"
                f"• Ключи: <b>{'есть' if remote_links else 'нет'}</b>"
            )

    return (
        "👤 <b>Карточка пользователя</b>\n\n"
        f"Пользователь: <b>{display_user(tg_username, tg_id)}</b>\n"
        f"Telegram ID: <code>{tg_id}</code>\n"
        f"Marzban username: <code>{html.escape(str(marzban_username or f'tg_{tg_id}'))}</code>\n\n"
        f"{local_text}\n\n"
        f"{marzban_text}"
    )


async def send_main_menu(message: Message) -> None:
    await message.answer(WELCOME_TEXT, reply_markup=main_keyboard_for(message.from_user.id))


@dp.message(CommandStart())
async def start_handler(message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username)
    await send_main_menu(message)


@dp.message(Command("menu"))
async def menu_handler(message: Message):
    db.ensure_user(message.from_user.id, message.from_user.username)
    await send_main_menu(message)


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await message.answer(admin_home_text(), reply_markup=admin_panel_keyboard())


@dp.message(F.text == BTN_ADMIN)
async def admin_button_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.", reply_markup=main_keyboard_for(message.from_user.id))
        return

    await message.answer(admin_home_text(), reply_markup=admin_panel_keyboard())


@dp.message(Command("status"))
async def admin_status_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    await message.answer(await server_status_text(), reply_markup=admin_server_status_keyboard())


@dp.callback_query(F.data == "admin:home")
async def admin_home_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await edit_or_answer(callback.message, admin_home_text(), reply_markup=admin_panel_keyboard())
    await callback.answer()


@dp.callback_query(F.data == "admin:server")
async def admin_server_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    await callback.answer("Проверяю сервер...")
    await edit_or_answer(
        callback.message,
        await server_status_text(),
        reply_markup=admin_server_status_keyboard(),
    )


@dp.callback_query(F.data.startswith("admin:users:"))
async def admin_users_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = parse_callback_parts(callback.data, 3)
    page = max(0, int(parts[2]))
    total = db.count_users()
    users = db.list_users(
        limit=ADMIN_USERS_PAGE_SIZE,
        offset=page * ADMIN_USERS_PAGE_SIZE,
    )

    await edit_or_answer(
        callback.message,
        admin_users_text(page, total),
        reply_markup=admin_users_keyboard(users, page, total),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin:user:"))
async def admin_user_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = parse_callback_parts(callback.data, 4)
    tg_id = int(parts[2])
    page = int(parts[3])

    await edit_or_answer(
        callback.message,
        await admin_user_text(tg_id),
        reply_markup=admin_user_manage_keyboard(tg_id, page),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("admin:sync:"))
async def admin_sync_user_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = parse_callback_parts(callback.data, 4)
    tg_id = int(parts[2])
    page = int(parts[3])

    user = db.get_user(tg_id)
    tg_username = user[1] if user else None

    try:
        synced = await sync_active_user_from_marzban(tg_id, tg_username)
    except MarzbanError as e:
        await callback.answer("Ошибка синхронизации.", show_alert=True)
        await callback.message.answer(f"❌ Ошибка синхронизации:\n<code>{html.escape(str(e))}</code>")
        return

    if not synced:
        await callback.answer("Активный доступ в Marzban не найден.", show_alert=True)
    else:
        await callback.answer("Синхронизировано.")

    await edit_or_answer(
        callback.message,
        await admin_user_text(tg_id),
        reply_markup=admin_user_manage_keyboard(tg_id, page),
    )


@dp.callback_query(F.data.startswith("admin:issue:"))
async def admin_issue_user_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = parse_callback_parts(callback.data, 5)
    tg_id = int(parts[2])
    tariff_id = parts[3]
    page = int(parts[4])
    tariff = TARIFFS.get(tariff_id)

    if not tariff:
        await callback.answer("Тариф не найден.", show_alert=True)
        return

    user = db.get_user(tg_id)
    tg_username = user[1] if user else None

    await callback.answer("Выдаю доступ...")
    try:
        marzban_username, expire_at, vpn_link = await create_or_update_user(
            tg_id=tg_id,
            days=int(tariff["days"]),
            data_limit_gb=int(tariff["data_limit_gb"]),
        )
        db.save_vpn_user(
            tg_id=tg_id,
            tg_username=tg_username,
            marzban_username=marzban_username,
            expire_at=expire_at,
            vpn_link=vpn_link,
            mark_trial_used=bool(tariff.get("is_trial")),
        )
        db.create_purchase(
            tg_id=tg_id,
            tg_username=tg_username,
            tariff_id=f"admin_{tariff_id}",
            status="admin_issued",
        )
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка выдачи доступа:\n<code>{html.escape(str(e))}</code>")
        return

    await edit_or_answer(
        callback.message,
        await admin_user_text(tg_id),
        reply_markup=admin_user_manage_keyboard(tg_id, page),
    )


@dp.message(F.text == BTN_BUY)
async def buy_message_handler(message: Message):
    if await message_is_rate_limited(message):
        return

    db.ensure_user(message.from_user.id, message.from_user.username)

    trial_available = not db.has_used_trial(message.from_user.id)
    await message.answer(
        "Выберите тариф:",
        reply_markup=tariffs_inline_keyboard(trial_available=trial_available),
    )


@dp.message(F.text == BTN_MY_KEY)
async def my_key_message_handler(message: Message):
    if await message_is_rate_limited(message):
        return

    db.ensure_user(message.from_user.id, message.from_user.username)

    user = db.get_user(message.from_user.id)
    try:
        synced = await sync_active_user_from_marzban(
            message.from_user.id,
            message.from_user.username,
        )
    except MarzbanError as e:
        logging.exception("Failed to sync user %s from Marzban", message.from_user.id)
        await notify_admins_about_error(
            e,
            action="Синхронизация доступа через кнопку Мой ключ",
            tg_id=message.from_user.id,
            username=message.from_user.username,
        )
        synced = False

    if synced:
        user = db.get_user(message.from_user.id)

    if not user or not user[4]:
        await message.answer(
            "У вас пока нет активного VPN-доступа.\n\n"
            "Нажмите «🚀 Купить VPN», чтобы получить доступ. "
            "Если админ уже включил доступ вручную, попробуйте ещё раз через минуту.",
            reply_markup=main_keyboard_for(message.from_user.id),
        )
        return

    tg_id, tg_username, _, expire_at, vpn_link, _, _, _ = user
    subscription_help = f"\n\n{SUBSCRIPTION_HELP_TEXT}" if is_subscription_link(vpn_link) else ""

    await message.answer(
        f"🔑 <b>Мой ключ</b>\n\n"
        f"Пользователь: <b>{display_user(tg_username, tg_id)}</b>\n"
        f"Активен до: <b>{format_date(expire_at)}</b>\n\n"
        f"Нажмите кнопку ниже, чтобы получить ссылку подключения."
        f"{subscription_help}",
        reply_markup=key_inline_keyboard(vpn_link),
    )


@dp.message(F.text == BTN_INSTRUCTION)
async def instruction_message_handler(message: Message):
    if await message_is_rate_limited(message):
        return

    await message.answer(INSTRUCTION_TEXT, reply_markup=main_keyboard_for(message.from_user.id))


@dp.message(F.text == BTN_SUPPORT)
async def support_message_handler(message: Message):
    if await message_is_rate_limited(message):
        return

    await message.answer(
        "💬 Поддержка Karipuza VPN:",
        reply_markup=support_inline_keyboard(),
    )


@dp.callback_query(F.data == "back_main")
async def back_main_callback(callback: CallbackQuery):
    if await answer_if_rate_limited(callback):
        return

    await callback.message.answer(WELCOME_TEXT, reply_markup=main_keyboard_for(callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data == "instruction")
async def instruction_callback(callback: CallbackQuery):
    if await answer_if_rate_limited(callback):
        return

    await callback.message.answer(INSTRUCTION_TEXT, reply_markup=main_keyboard_for(callback.from_user.id))
    await callback.answer()


@dp.callback_query(F.data == "show_key")
async def show_key_callback(callback: CallbackQuery):
    if await answer_if_rate_limited(callback):
        return

    db.ensure_user(callback.from_user.id, callback.from_user.username)

    user = db.get_user(callback.from_user.id)
    try:
        synced = await sync_active_user_from_marzban(
            callback.from_user.id,
            callback.from_user.username,
        )
    except MarzbanError as e:
        logging.exception("Failed to sync user %s from Marzban", callback.from_user.id)
        await notify_admins_about_error(
            e,
            action="Синхронизация доступа через кнопку Показать ссылку",
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        synced = False

    if synced:
        user = db.get_user(callback.from_user.id)

    if not user or not user[4]:
        await callback.answer("Активный доступ не найден.", show_alert=True)
        return

    vpn_link = user[4]
    title = "Ваша VPN-подписка" if is_subscription_link(vpn_link) else "Ваш VPN-ключ"
    await callback.message.answer(
        f"📄 <b>{title}</b>\n\n"
        "Telegram не умеет скрыто копировать очень длинные ссылки, "
        "поэтому скопируйте строку ниже вручную:\n\n"
        f"<code>{html.escape(vpn_link)}</code>"
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tariff:"))
async def tariff_callback(callback: CallbackQuery):
    if callback.from_user.id in active_key_requests:
        await callback.answer("Доступ уже создаётся, подождите.", show_alert=True)
        return

    if await answer_if_rate_limited(callback, HEAVY_ACTION_COOLDOWN_SECONDS, heavy=True):
        return

    db.ensure_user(callback.from_user.id, callback.from_user.username)

    tariff_id = callback.data.split(":", 1)[1]
    tariff = TARIFFS.get(tariff_id)

    if not tariff:
        await callback.answer("Тариф не найден.", show_alert=True)
        return

    is_trial = bool(tariff.get("is_trial"))

    if is_trial and db.has_used_trial(callback.from_user.id):
        await callback.answer("Тестовый период уже использован.", show_alert=True)
        await callback.message.answer(
            "Тестовый период уже использован.\n\nВыберите обычный тариф:",
            reply_markup=tariffs_inline_keyboard(trial_available=False),
        )
        return

    active_key_requests.add(callback.from_user.id)
    try:
        await callback.answer("Готовлю доступ...")
        await callback.message.answer("⏳ Готовлю ваш VPN-доступ...")

        marzban_username, expire_at, vpn_link = await create_or_update_user(
            tg_id=callback.from_user.id,
            days=int(tariff["days"]),
            data_limit_gb=int(tariff["data_limit_gb"]),
        )

        db.save_vpn_user(
            tg_id=callback.from_user.id,
            tg_username=callback.from_user.username,
            marzban_username=marzban_username,
            expire_at=expire_at,
            vpn_link=vpn_link,
            mark_trial_used=is_trial,
        )

        db.create_purchase(
            tg_id=callback.from_user.id,
            tg_username=callback.from_user.username,
            tariff_id=tariff_id,
            status="auto_issued",
        )

        await callback.message.answer(
            f"✅ <b>Доступ активирован!</b>\n\n"
            f"Тариф: <b>{tariff['title']}</b>\n"
            f"Активен до: <b>{format_date(expire_at)}</b>\n\n"
            f"🔑 Нажмите кнопку ниже, чтобы получить ссылку подключения.\n"
            f"📲 Если не знаете, как подключиться — откройте инструкцию.",
            reply_markup=key_inline_keyboard(vpn_link),
        )

        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(
                    admin_id,
                    f"✅ <b>Автоматически выдан доступ</b>\n\n"
                    f"Пользователь: {display_user(callback.from_user.username, callback.from_user.id)}\n"
                    f"Telegram ID: <code>{callback.from_user.id}</code>\n"
                    f"Тариф: <b>{tariff['title']}</b>\n"
                    f"Активен до: <b>{format_date(expire_at)}</b>",
                    reply_markup=admin_user_inline_keyboard(callback.from_user.id),
                )
            except Exception:
                logging.exception("Failed to send admin notification to %s", admin_id)

    except MarzbanError as e:
        await notify_admins_about_error(
            e,
            action=f"Создание VPN-доступа, тариф {tariff['title']}",
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        await callback.message.answer(
            GENERIC_ERROR_TEXT,
            reply_markup=main_keyboard_for(callback.from_user.id),
        )
    except Exception as e:
        logging.exception("Unknown error while creating VPN key")
        await notify_admins_about_error(
            e,
            action=f"Неизвестная ошибка при создании VPN-доступа, тариф {tariff['title']}",
            tg_id=callback.from_user.id,
            username=callback.from_user.username,
        )
        await callback.message.answer(
            GENERIC_ERROR_TEXT,
            reply_markup=main_keyboard_for(callback.from_user.id),
        )
    finally:
        active_key_requests.discard(callback.from_user.id)


@dp.callback_query(F.data.startswith("disable_user:"))
async def disable_user_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    tg_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    try:
        await disable_user(tg_id)
        db.clear_user_key(tg_id)
        await edit_or_answer(
            callback.message,
            await admin_user_text(tg_id),
            reply_markup=admin_user_manage_keyboard(tg_id, page),
        )
        await callback.answer("Отключено.")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка отключения:\n<code>{e}</code>")
        await callback.answer("Ошибка.", show_alert=True)


@dp.callback_query(F.data.startswith("enable_user:"))
async def enable_user_callback(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа.", show_alert=True)
        return

    parts = callback.data.split(":")
    tg_id = int(parts[1])
    page = int(parts[2]) if len(parts) > 2 else 0

    try:
        marzban_username, expire_at, vpn_link = await enable_marzban_user(tg_id)
        user = db.get_user(tg_id)
        tg_username = user[1] if user else None
        db.save_vpn_user(
            tg_id=tg_id,
            tg_username=tg_username,
            marzban_username=marzban_username,
            expire_at=expire_at,
            vpn_link=vpn_link,
            mark_trial_used=False,
        )
        await edit_or_answer(
            callback.message,
            await admin_user_text(tg_id),
            reply_markup=admin_user_manage_keyboard(tg_id, page),
        )
        await callback.answer("Включено.")
    except Exception as e:
        await callback.message.answer(f"❌ Ошибка включения:\n<code>{e}</code>")
        await callback.answer("Ошибка.", show_alert=True)


@dp.callback_query()
async def unknown_callback(callback: CallbackQuery):
    logging.warning("Unknown callback data: %s", callback.data)
    await callback.answer("Кнопка устарела. Нажмите /start.", show_alert=True)


@dp.message()
async def unknown_message(message: Message):
    await message.answer(
        "Я не понял сообщение. Используйте меню снизу или команду /start.",
        reply_markup=main_keyboard_for(message.from_user.id),
    )


async def main():
    validate_settings()
    db.init_db()
    logging.info("Karipuza VPN Bot started")
    await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())


if __name__ == "__main__":
    asyncio.run(main())

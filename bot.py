import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

import database as db
from config import settings, validate_settings
from keyboards import after_key_menu, admin_user_menu, back_menu, main_menu, tariffs_menu
from marzban_api import MarzbanError, create_or_update_user, disable_user
from texts import INSTRUCTION_TEXT, TARIFFS, WELCOME_TEXT

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def format_date(timestamp: int) -> str:
    if not timestamp:
        return "неизвестно"
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


def display_user(username: str | None, tg_id: int) -> str:
    if username:
        return f"@{username}"
    return f"ID {tg_id}"


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu())


@dp.message(Command("menu"))
async def menu_handler(message: Message):
    await message.answer("Главное меню Karipuza VPN:", reply_markup=main_menu())


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    users = db.list_recent_users(10)
    if not users:
        await message.answer("🛠 <b>Админ-панель</b>\n\nПока пользователей нет.")
        return

    lines = ["🛠 <b>Админ-панель</b>", "", "Последние пользователи:"]
    for tg_id, tg_username, _, expire_at, trial_used in users:
        name = display_user(tg_username, tg_id)
        trial_text = "тест использован" if trial_used else "тест не использован"
        lines.append(f"• {name} — до {format_date(expire_at)} — {trial_text}")

    await message.answer("\n".join(lines))


@dp.callback_query(F.data == "back_main")
async def back_main_handler(callback: CallbackQuery):
    # Не edit_text, а новое сообщение. Так главное меню открывается стабильно,
    # даже если предыдущее сообщение нельзя редактировать.
    await callback.message.answer("Главное меню Karipuza VPN:", reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(F.data == "buy")
async def buy_handler(callback: CallbackQuery):
    trial_available = not db.has_used_trial(callback.from_user.id)
    await callback.message.edit_text(
        "Выберите тариф:",
        reply_markup=tariffs_menu(trial_available=trial_available),
    )
    await callback.answer()


@dp.callback_query(F.data.startswith("tariff:"))
async def tariff_handler(callback: CallbackQuery):
    tariff_id = callback.data.split(":", 1)[1]
    tariff = TARIFFS.get(tariff_id)

    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    is_trial = bool(tariff.get("is_trial"))

    if is_trial and db.has_used_trial(callback.from_user.id):
        await callback.answer("Тестовый период уже был использован.", show_alert=True)
        await callback.message.edit_text(
            "Тестовый период уже был использован.\n\n"
            "Выберите обычный тариф:",
            reply_markup=tariffs_menu(trial_available=False),
        )
        return

    await callback.message.edit_text("⏳ Создаю ваш VPN-ключ...")

    try:
        marzban_username, expire_at, vpn_link = await create_or_update_user(
            tg_id=callback.from_user.id,
            days=tariff["days"],
            data_limit_gb=tariff["data_limit_gb"],
        )

        if is_trial:
            db.mark_trial_used(callback.from_user.id)

        db.save_user(
            tg_id=callback.from_user.id,
            tg_username=callback.from_user.username,
            marzban_username=marzban_username,
            expire_at=expire_at,
            vpn_link=vpn_link,
            trial_used=True if is_trial else None,
        )

        db.create_purchase(
            tg_id=callback.from_user.id,
            tg_username=callback.from_user.username,
            tariff_id=tariff_id,
            status="auto_issued",
        )

        await callback.message.edit_text(
            f"✅ <b>Доступ активирован!</b>\n\n"
            f"Тариф: <b>{tariff['title']}</b>\n"
            f"Активен до: <b>{format_date(expire_at)}</b>\n\n"
            f"🔑 Нажмите кнопку ниже, чтобы скопировать ключ.\n"
            f"📲 Если не знаете, как подключиться — откройте инструкцию.",
            reply_markup=after_key_menu(vpn_link),
        )

        for admin_id in settings.admin_ids:
            await bot.send_message(
                admin_id,
                f"✅ <b>Автоматически выдан доступ</b>\n\n"
                f"Пользователь: {display_user(callback.from_user.username, callback.from_user.id)}\n"
                f"Telegram ID: <code>{callback.from_user.id}</code>\n"
                f"Тариф: <b>{tariff['title']}</b>\n"
                f"Активен до: <b>{format_date(expire_at)}</b>",
                reply_markup=admin_user_menu(callback.from_user.id),
            )

    except MarzbanError as e:
        await callback.message.edit_text(
            "❌ Не получилось создать ключ через Marzban.\n\n"
            f"<code>{e}</code>\n\n"
            "Проверьте, что Marzban запущен, логин/пароль верные, "
            "а MARZBAN_INBOUND_TAG совпадает с названием inbound.",
            reply_markup=main_menu(),
        )
    except Exception as e:
        await callback.message.edit_text(
            f"❌ Неизвестная ошибка:\n<code>{e}</code>",
            reply_markup=main_menu(),
        )

    await callback.answer()


@dp.callback_query(F.data == "my_key")
async def my_key_handler(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)

    if not user or not user[4]:
        await callback.message.edit_text(
            "У вас пока нет активного VPN-ключа.\n\n"
            "Нажмите «Купить VPN», чтобы получить доступ.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    tg_id, tg_username, _, expire_at, vpn_link, _, _, _ = user

    await callback.message.edit_text(
        f"🔑 <b>Мой ключ</b>\n\n"
        f"Пользователь: <b>{display_user(tg_username, tg_id)}</b>\n"
        f"Активен до: <b>{format_date(expire_at)}</b>\n\n"
        f"Нажмите кнопку ниже, чтобы скопировать ключ.",
        reply_markup=after_key_menu(vpn_link),
    )
    await callback.answer()


@dp.callback_query(F.data == "instruction")
async def instruction_handler(callback: CallbackQuery):
    try:
        await callback.message.edit_text(INSTRUCTION_TEXT, reply_markup=main_menu())
    except Exception:
        await callback.message.answer(INSTRUCTION_TEXT, reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(F.data.startswith("disable_user:"))
async def disable_user_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    tg_id = int(callback.data.split(":", 1)[1])

    try:
        await disable_user(tg_id)
        await callback.message.edit_text(f"⛔ Пользователь <code>{tg_id}</code> отключён.")
    except Exception as e:
        await callback.message.edit_text(f"❌ Ошибка отключения:\n<code>{e}</code>")

    await callback.answer()


async def main():
    validate_settings()
    db.init_db()
    print("Karipuza VPN Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

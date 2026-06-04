import asyncio
from datetime import datetime

from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

import database as db
from config import settings
from keyboards import admin_order_menu, main_menu, tariffs_menu
from marzban_api import MarzbanError, create_or_update_user
from texts import INSTRUCTION_TEXT, TARIFFS, WELCOME_TEXT

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML),
)
dp = Dispatcher()


def is_admin(user_id: int) -> bool:
    return user_id in settings.admin_ids


def format_date(timestamp: int) -> str:
    return datetime.fromtimestamp(timestamp).strftime("%d.%m.%Y")


@dp.message(CommandStart())
async def start_handler(message: Message):
    await message.answer(WELCOME_TEXT, reply_markup=main_menu())


@dp.message(Command("admin"))
async def admin_handler(message: Message):
    if not is_admin(message.from_user.id):
        await message.answer("Нет доступа.")
        return

    users = db.list_recent_users(10)
    if not users:
        await message.answer("Админ-панель\n\nПока пользователей нет.")
        return

    lines = ["🛠 <b>Админ-панель</b>", "", "Последние пользователи:"]
    for tg_id, tg_username, marzban_username, expire_at, _ in users:
        name = f"@{tg_username}" if tg_username else str(tg_id)
        lines.append(f"• {name} — {marzban_username} — до {format_date(expire_at)}")

    await message.answer("\n".join(lines))


@dp.callback_query(F.data == "back_main")
async def back_main_handler(callback: CallbackQuery):
    await callback.message.edit_text("Главное меню Karipuza VPN:", reply_markup=main_menu())
    await callback.answer()


@dp.callback_query(F.data == "buy")
async def buy_handler(callback: CallbackQuery):
    await callback.message.edit_text("Выберите тариф:", reply_markup=tariffs_menu())
    await callback.answer()


@dp.callback_query(F.data.startswith("tariff:"))
async def tariff_handler(callback: CallbackQuery):
    tariff_id = callback.data.split(":", 1)[1]
    tariff = TARIFFS.get(tariff_id)

    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    order_id = db.create_order(
        tg_id=callback.from_user.id,
        tg_username=callback.from_user.username,
        tariff_id=tariff_id,
    )

    await callback.message.edit_text(
        f"✅ Заявка создана.\n\n"
        f"Тариф: <b>{tariff['title']}</b>\n"
        f"Стоимость: <b>{tariff['price']}</b>\n\n"
        f"Сейчас оплата временно обрабатывается администратором.\n"
        f"После подтверждения бот автоматически выдаст VPN-ключ.",
        reply_markup=main_menu(),
    )

    username = callback.from_user.username
    user_line = f"@{username}" if username else "без username"

    for admin_id in settings.admin_ids:
        await bot.send_message(
            admin_id,
            f"🆕 <b>Новая заявка #{order_id}</b>\n\n"
            f"Пользователь: {user_line}\n"
            f"Telegram ID: <code>{callback.from_user.id}</code>\n"
            f"Тариф: <b>{tariff['title']}</b>\n"
            f"Цена: <b>{tariff['price']}</b>",
            reply_markup=admin_order_menu(order_id),
        )

    await callback.answer()


@dp.callback_query(F.data.startswith("approve:"))
async def approve_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":", 1)[1])
    order = db.get_order(order_id)

    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    _, tg_id, tg_username, tariff_id, status, _, _ = order

    if status != "pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return

    tariff = TARIFFS.get(tariff_id)
    if not tariff:
        await callback.answer("Тариф не найден", show_alert=True)
        return

    await callback.message.edit_text(f"⏳ Выдаю доступ по заявке #{order_id}...")

    try:
        marzban_username, expire_at, vpn_link = await create_or_update_user(
            tg_id=tg_id,
            days=tariff["days"],
            data_limit_gb=tariff["data_limit_gb"],
        )

        db.save_user(
            tg_id=tg_id,
            tg_username=tg_username,
            marzban_username=marzban_username,
            expire_at=expire_at,
            vpn_link=vpn_link,
        )
        db.update_order_status(order_id, "approved")

        await bot.send_message(
            tg_id,
            f"✅ <b>Доступ активирован!</b>\n\n"
            f"Тариф: <b>{tariff['title']}</b>\n"
            f"Активен до: <b>{format_date(expire_at)}</b>\n\n"
            f"🔑 <b>Ваш VPN-ключ:</b>\n"
            f"<code>{vpn_link}</code>\n\n"
            f"📲 Нажмите «Инструкция», если не знаете как подключиться.",
        )

        await callback.message.edit_text(
            f"✅ Заявка #{order_id} одобрена.\n"
            f"Пользователю выдан ключ."
        )

    except MarzbanError as e:
        await callback.message.edit_text(f"❌ Ошибка Marzban:\n<code>{e}</code>")
    except Exception as e:
        await callback.message.edit_text(f"❌ Неизвестная ошибка:\n<code>{e}</code>")

    await callback.answer()


@dp.callback_query(F.data.startswith("reject:"))
async def reject_handler(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return

    order_id = int(callback.data.split(":", 1)[1])
    order = db.get_order(order_id)

    if not order:
        await callback.answer("Заявка не найдена", show_alert=True)
        return

    _, tg_id, _, _, status, _, _ = order

    if status != "pending":
        await callback.answer("Заявка уже обработана", show_alert=True)
        return

    db.update_order_status(order_id, "rejected")

    await bot.send_message(
        tg_id,
        "❌ Заявка отклонена.\n\nЕсли это ошибка, напишите в поддержку."
    )
    await callback.message.edit_text(f"❌ Заявка #{order_id} отклонена.")
    await callback.answer()


@dp.callback_query(F.data == "my_key")
async def my_key_handler(callback: CallbackQuery):
    user = db.get_user(callback.from_user.id)

    if not user:
        await callback.message.edit_text(
            "У вас пока нет активного VPN-ключа.\n\n"
            "Нажмите «Купить VPN», чтобы получить доступ.",
            reply_markup=main_menu(),
        )
        await callback.answer()
        return

    _, _, marzban_username, expire_at, vpn_link, _, _ = user

    await callback.message.edit_text(
        f"🔑 <b>Ваш VPN-ключ</b>\n\n"
        f"Профиль: <b>{marzban_username}</b>\n"
        f"Активен до: <b>{format_date(expire_at)}</b>\n\n"
        f"<code>{vpn_link}</code>",
        reply_markup=main_menu(),
    )
    await callback.answer()


@dp.callback_query(F.data == "instruction")
async def instruction_handler(callback: CallbackQuery):
    await callback.message.edit_text(INSTRUCTION_TEXT, reply_markup=main_menu())
    await callback.answer()


async def main():
    db.init_db()
    print("Karipuza VPN Bot started")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

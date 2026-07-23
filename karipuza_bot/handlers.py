from __future__ import annotations

import html
import io
import logging
import traceback
from typing import Any

import qrcode
from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    ErrorEvent,
    Message,
)

from . import ui
from .config import Settings, TARIFFS_BY_CODE
from .database import Database
from .remnawave import RemnawaveClient, Subscription

LOGGER = logging.getLogger(__name__)
GENERIC_ERROR = "Произошла ошибка. Обратитесь в поддержку."
USERS_PAGE_SIZE = 8


def create_router(
    db: Database,
    remnawave: RemnawaveClient,
    settings: Settings,
) -> Router:
    router = Router(name="karipuza")

    def is_admin(tg_id: int) -> bool:
        return tg_id in settings.admin_ids

    def main_menu_keyboard(tg_id: int):
        return ui.main_keyboard(is_admin(tg_id), settings.mini_app_url)

    async def ensure_user(message_or_callback: Message | CallbackQuery) -> None:
        user = message_or_callback.from_user
        if not user:
            return
        await db.ensure_user(user.id, user.username, user.first_name)

    async def render(
        callback: CallbackQuery,
        text: str,
        keyboard,
    ) -> None:
        try:
            await callback.answer()
        except TelegramBadRequest:
            pass
        if isinstance(callback.message, Message):
            try:
                await callback.message.edit_text(text, reply_markup=keyboard)
                return
            except TelegramBadRequest as error:
                if "message is not modified" in str(error).lower():
                    return
                LOGGER.info("Cannot edit menu message, sending a new one: %s", error)
                await callback.message.answer(text, reply_markup=keyboard)

    async def notify_admins(
        bot: Bot,
        text: str,
        *,
        keyboard=None,
    ) -> None:
        for admin_id in settings.admin_ids:
            try:
                await bot.send_message(admin_id, text, reply_markup=keyboard)
            except Exception:
                LOGGER.exception("Failed to notify admin %s", admin_id)

    async def notify_error(bot: Bot, error: BaseException, context: str) -> None:
        details = "".join(
            traceback.format_exception(type(error), error, error.__traceback__)
        )
        text = (
            f"<b>Ошибка в боте</b>\n\n"
            f"Контекст: {html.escape(context)}\n"
            f"<pre>{html.escape(details[-3000:])}</pre>"
        )
        await notify_admins(bot, text)

    async def save_subscription(tg_id: int, subscription: Subscription) -> None:
        await db.save_subscription(
            tg_id,
            remnawave_uuid=subscription.uuid,
            subscription_url=subscription.subscription_url,
            status=subscription.status,
            expire_at=subscription.expire_at,
            traffic_used=subscription.traffic_used,
        )

    async def current_subscription(
        bot: Bot, tg_id: int
    ) -> tuple[Subscription | None, Any, bool]:
        local_user = await db.get_user(tg_id)
        if not remnawave.configured:
            return None, local_user, False
        try:
            subscription = await remnawave.get_by_telegram_id(tg_id)
            if subscription:
                await save_subscription(tg_id, subscription)
                local_user = await db.get_user(tg_id)
            return subscription, local_user, False
        except Exception as error:
            LOGGER.exception("Subscription sync failed for %s", tg_id)
            await notify_error(
                bot, error, f"синхронизация подписки пользователя {tg_id}"
            )
            return None, local_user, True

    async def require_admin(callback: CallbackQuery) -> bool:
        if callback.from_user and is_admin(callback.from_user.id):
            return True
        await callback.answer("Недостаточно прав.", show_alert=True)
        return False

    def message_payload(message: Message) -> tuple[str, str | None, str | None]:
        if message.photo:
            return "PHOTO", message.photo[-1].file_id, message.caption
        if message.document:
            return "DOCUMENT", message.document.file_id, message.caption
        if message.text:
            return "TEXT", None, message.text
        return "OTHER", None, message.caption

    @router.message(CommandStart())
    @router.message(Command("menu"))
    async def start(message: Message) -> None:
        await ensure_user(message)
        await db.clear_session(message.from_user.id)
        await message.answer(
            ui.main_text(message.from_user.first_name),
            reply_markup=main_menu_keyboard(message.from_user.id),
        )

    @router.message(Command("cancel"))
    async def cancel(message: Message) -> None:
        await db.clear_session(message.from_user.id)
        await message.answer(
            "Действие отменено.",
            reply_markup=main_menu_keyboard(message.from_user.id),
        )

    @router.message(Command("admin"))
    async def admin_command(message: Message, bot: Bot) -> None:
        await ensure_user(message)
        if not is_admin(message.from_user.id):
            await message.answer("Недостаточно прав.")
            return
        stats = await db.stats()
        vpn_ok = await remnawave.health() if remnawave.configured else False
        await message.answer(
            ui.admin_home_text(stats, vpn_ok),
            reply_markup=ui.admin_home_keyboard(),
        )

    @router.callback_query(F.data == "home")
    async def home(callback: CallbackQuery) -> None:
        await ensure_user(callback)
        await db.clear_session(callback.from_user.id)
        await render(
            callback,
            ui.main_text(callback.from_user.first_name),
            main_menu_keyboard(callback.from_user.id),
        )

    @router.callback_query(F.data == "plans")
    async def plans(callback: CallbackQuery) -> None:
        await ensure_user(callback)
        await render(callback, ui.plans_text(), ui.plans_keyboard())

    @router.callback_query(F.data == "profile")
    async def profile(callback: CallbackQuery, bot: Bot) -> None:
        await ensure_user(callback)
        remote, local, _failed = await current_subscription(bot, callback.from_user.id)
        url = (
            remote.subscription_url
            if remote
            else (local["subscription_url"] if local else None)
        )
        await render(
            callback,
            ui.profile_text(
                callback.from_user.id,
                callback.from_user.first_name,
                callback.from_user.username,
                remote,
                local,
            ),
            ui.profile_keyboard(bool(url)),
        )

    @router.callback_query(F.data.startswith("plan:"))
    async def plan(callback: CallbackQuery) -> None:
        code = (callback.data or "").split(":", 1)[1]
        tariff = TARIFFS_BY_CODE.get(code)
        if not tariff:
            await callback.answer("Тариф не найден.", show_alert=True)
            return
        await render(callback, ui.plan_text(tariff), ui.plan_keyboard(tariff))

    @router.callback_query(F.data.startswith("order:create:"))
    async def create_order(callback: CallbackQuery) -> None:
        await ensure_user(callback)
        code = (callback.data or "").split(":", 2)[2]
        tariff = TARIFFS_BY_CODE.get(code)
        if not tariff:
            await callback.answer("Тариф не найден.", show_alert=True)
            return
        order = await db.find_waiting_order(callback.from_user.id, tariff.code)
        if order:
            order_id = int(order["id"])
        else:
            order_id = await db.create_order(
                callback.from_user.id,
                tariff_code=tariff.code,
                title=tariff.title,
                duration_days=tariff.days,
                amount_rub=tariff.price_rub,
            )
            order = await db.get_order(order_id)
            await db.audit(
                "ORDER_CREATED",
                actor_tg_id=callback.from_user.id,
                entity_type="order",
                entity_id=order_id,
            )
        await render(
            callback,
            ui.order_text(order, settings.payment_details),
            ui.order_keyboard(order_id, bool(settings.payment_details)),
        )

    @router.callback_query(F.data.startswith("order:paid:"))
    async def order_paid(callback: CallbackQuery) -> None:
        order_id = int((callback.data or "").rsplit(":", 1)[1])
        order = await db.get_order(order_id)
        if (
            not order
            or order["tg_id"] != callback.from_user.id
            or order["status"] != "WAITING_PAYMENT"
        ):
            await callback.answer(
                "Этот заказ уже обработан или не найден.", show_alert=True
            )
            return
        await db.set_session(
            callback.from_user.id,
            "payment_proof",
            {"order_id": order_id},
        )
        await render(
            callback,
            f"<b>Заказ #{order_id}</b>\n\n"
            "Отправьте следующим сообщением чек, скриншот или текст "
            "с данными платежа.\n\nДля отмены: /cancel",
            ui.kb([ui.button("Отменить", "home")]),
        )

    @router.callback_query(F.data == "subscription")
    async def subscription(callback: CallbackQuery, bot: Bot) -> None:
        await ensure_user(callback)
        remote, local, failed = await current_subscription(bot, callback.from_user.id)
        if failed and not (local and local["subscription_url"]):
            await render(
                callback,
                "<b>Не удалось загрузить подписку</b>\n\n"
                "Попробуйте ещё раз через минуту или обратитесь в поддержку.",
                ui.kb(
                    [ui.button("Повторить", "subscription")],
                    [ui.button("Поддержка", "support")],
                    [ui.button("Главное меню", "home")],
                ),
            )
            return
        url = (
            remote.subscription_url
            if remote
            else (local["subscription_url"] if local else None)
        )
        has_subscription = bool(url)
        await render(
            callback,
            ui.subscription_text(remote, local),
            ui.subscription_keyboard(url, has_subscription),
        )

    @router.callback_query(F.data == "subscription:qr")
    async def subscription_qr(callback: CallbackQuery, bot: Bot) -> None:
        await callback.answer("Готовлю QR-код...")
        remote, local, failed = await current_subscription(bot, callback.from_user.id)
        url = (
            remote.subscription_url
            if remote
            else (local["subscription_url"] if local else None)
        )
        if not url:
            await bot.send_message(
                callback.from_user.id,
                GENERIC_ERROR if failed else "Активная подписка не найдена.",
                reply_markup=ui.kb(
                    [
                        ui.button(
                            "Поддержка" if failed else "Выбрать тариф",
                            "support" if failed else "plans",
                        )
                    ]
                ),
            )
            return
        image = qrcode.make(url)
        output = io.BytesIO()
        image.save(output, format="PNG")
        await bot.send_photo(
            callback.from_user.id,
            BufferedInputFile(output.getvalue(), filename="karipaza-froxy-subscription.png"),
            caption="QR-код подписки Karipaza Froxy",
        )

    @router.callback_query(F.data == "instruction")
    async def instruction(callback: CallbackQuery) -> None:
        await render(callback, ui.instruction_text(), ui.instruction_keyboard())

    @router.callback_query(F.data == "support")
    async def support(callback: CallbackQuery) -> None:
        await render(callback, ui.support_text(), ui.support_keyboard())

    @router.callback_query(F.data == "support:new")
    async def support_new(callback: CallbackQuery) -> None:
        await db.set_session(callback.from_user.id, "support_new")
        await render(
            callback,
            "<b>Новое обращение</b>\n\n"
            "Опишите проблему следующим сообщением. "
            "Чем точнее описание, тем быстрее получится помочь.\n\n"
            "Для отмены: /cancel",
            ui.kb([ui.button("Отменить", "home")]),
        )

    @router.callback_query(F.data == "admin:home")
    async def admin_home(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        stats = await db.stats()
        vpn_ok = await remnawave.health() if remnawave.configured else False
        await render(
            callback,
            ui.admin_home_text(stats, vpn_ok),
            ui.admin_home_keyboard(),
        )

    @router.callback_query(F.data == "admin:orders")
    async def admin_orders(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        orders = await db.list_orders(status="REVIEW")
        await render(
            callback,
            ui.admin_orders_text(orders),
            ui.admin_orders_keyboard(orders),
        )

    @router.callback_query(F.data.startswith("admin:order:view:"))
    async def admin_order_view(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        order_id = int((callback.data or "").rsplit(":", 1)[1])
        order = await db.get_order(order_id)
        if not order:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        await render(
            callback,
            ui.admin_order_text(order),
            ui.payment_review_keyboard(order_id),
        )

    @router.callback_query(F.data.startswith("admin:order:approve:"))
    async def admin_order_approve(callback: CallbackQuery, bot: Bot) -> None:
        if not await require_admin(callback):
            return
        await callback.answer("Создаю подписку...")
        order_id = int((callback.data or "").rsplit(":", 1)[1])
        order = await db.get_order(order_id)
        if not order:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        claimed = await db.transition_order_status(
            order_id,
            expected_status="REVIEW",
            new_status="PROCESSING",
            reviewed_by=callback.from_user.id,
        )
        if not claimed:
            await callback.answer(
                "Заказ уже взял другой администратор.", show_alert=True
            )
            return
        try:
            name = order["first_name"] or order["username"] or f"TG {order['tg_id']}"
            created = await remnawave.activate(
                tg_id=order["tg_id"],
                display_name=str(name),
                days=order["duration_days"],
            )
            await save_subscription(order["tg_id"], created)
            await db.set_order_status(
                order_id, "APPROVED", reviewed_by=callback.from_user.id
            )
            await db.audit(
                "ORDER_APPROVED",
                actor_tg_id=callback.from_user.id,
                entity_type="order",
                entity_id=order_id,
            )
            await bot.send_message(
                order["tg_id"],
                f"<b>Оплата подтверждена</b>\n\n"
                f"Подписка продлена на {order['duration_days']} дней. "
                "Откройте раздел «Моя подписка», чтобы подключиться.",
                reply_markup=ui.kb(
                    [ui.button("Моя подписка", "subscription")],
                    [ui.button("Главное меню", "home")],
                ),
            )
            await render(
                callback,
                f"<b>Заказ #{order_id} подтверждён</b>\n\n"
                "Подписка создана или продлена.",
                ui.admin_home_keyboard(),
            )
        except Exception:
            await db.transition_order_status(
                order_id,
                expected_status="PROCESSING",
                new_status="REVIEW",
            )
            raise

    @router.callback_query(F.data.startswith("admin:order:reject:"))
    async def admin_order_reject(callback: CallbackQuery, bot: Bot) -> None:
        if not await require_admin(callback):
            return
        order_id = int((callback.data or "").rsplit(":", 1)[1])
        order = await db.get_order(order_id)
        if not order:
            await callback.answer("Заказ не найден.", show_alert=True)
            return
        changed = await db.transition_order_status(
            order_id,
            expected_status="REVIEW",
            new_status="REJECTED",
            reviewed_by=callback.from_user.id,
        )
        if not changed:
            await callback.answer("Заказ уже обработан.", show_alert=True)
            return
        await db.audit(
            "ORDER_REJECTED",
            actor_tg_id=callback.from_user.id,
            entity_type="order",
            entity_id=order_id,
        )
        await bot.send_message(
            order["tg_id"],
            f"Платёж по заказу #{order_id} не удалось подтвердить. "
            "Пожалуйста, напишите в поддержку.",
            reply_markup=ui.support_keyboard(),
        )
        await render(
            callback,
            f"<b>Заказ #{order_id} отклонён</b>",
            ui.admin_home_keyboard(),
        )

    @router.callback_query(F.data == "admin:tickets")
    async def admin_tickets(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        tickets = await db.list_tickets()
        await render(
            callback,
            ui.admin_tickets_text(tickets),
            ui.admin_tickets_keyboard(tickets),
        )

    @router.callback_query(F.data.startswith("admin:ticket:view:"))
    async def admin_ticket_view(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        ticket_id = int((callback.data or "").rsplit(":", 1)[1])
        ticket = await db.get_ticket(ticket_id)
        if not ticket:
            await callback.answer("Обращение не найдено.", show_alert=True)
            return
        await render(
            callback,
            ui.admin_ticket_text(ticket),
            ui.ticket_admin_keyboard(ticket_id),
        )

    @router.callback_query(F.data.startswith("admin:ticket:reply:"))
    async def admin_ticket_reply(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        ticket_id = int((callback.data or "").rsplit(":", 1)[1])
        ticket = await db.get_ticket(ticket_id)
        if not ticket or ticket["status"] != "OPEN":
            await callback.answer("Обращение уже закрыто.", show_alert=True)
            return
        await db.set_session(
            callback.from_user.id,
            "admin_ticket_reply",
            {"ticket_id": ticket_id},
        )
        await render(
            callback,
            f"<b>Ответ на обращение #{ticket_id}</b>\n\n"
            "Отправьте текст ответа следующим сообщением.\n\nДля отмены: /cancel",
            ui.kb([ui.button("Отменить", "admin:tickets")]),
        )

    @router.callback_query(F.data.startswith("admin:ticket:close:"))
    async def admin_ticket_close(callback: CallbackQuery, bot: Bot) -> None:
        if not await require_admin(callback):
            return
        ticket_id = int((callback.data or "").rsplit(":", 1)[1])
        ticket = await db.get_ticket(ticket_id)
        if not ticket:
            await callback.answer("Обращение не найдено.", show_alert=True)
            return
        await db.close_ticket(ticket_id)
        await bot.send_message(
            ticket["tg_id"],
            f"Обращение #{ticket_id} закрыто. Если вопрос остался, "
            "можно создать новое обращение.",
            reply_markup=ui.support_keyboard(),
        )
        await render(
            callback,
            f"<b>Обращение #{ticket_id} закрыто</b>",
            ui.admin_home_keyboard(),
        )

    @router.callback_query(F.data.startswith("admin:users:"))
    async def admin_users(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        page = max(0, int((callback.data or "").rsplit(":", 1)[1]))
        total = await db.count_users()
        users = await db.list_users(USERS_PAGE_SIZE, page * USERS_PAGE_SIZE)
        await render(
            callback,
            ui.admin_users_text(users, page, total),
            ui.admin_users_keyboard(users, page, total, USERS_PAGE_SIZE),
        )

    @router.callback_query(F.data.regexp(r"^admin:user:\d+$"))
    async def admin_user_view(callback: CallbackQuery) -> None:
        if not await require_admin(callback):
            return
        tg_id = int((callback.data or "").rsplit(":", 1)[1])
        user = await db.get_user(tg_id)
        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return
        await render(
            callback,
            ui.admin_user_text(user),
            ui.admin_user_keyboard(tg_id, bool(user["remnawave_uuid"])),
        )

    @router.callback_query(F.data.startswith("admin:user:grant:"))
    async def admin_user_grant(callback: CallbackQuery, bot: Bot) -> None:
        if not await require_admin(callback):
            return
        await callback.answer("Добавляю 30 дней...")
        tg_id = int((callback.data or "").rsplit(":", 1)[1])
        user = await db.get_user(tg_id)
        if not user:
            await callback.answer("Пользователь не найден.", show_alert=True)
            return
        name = user["first_name"] or user["username"] or f"TG {tg_id}"
        created = await remnawave.activate(
            tg_id=tg_id,
            display_name=str(name),
            days=30,
        )
        await save_subscription(tg_id, created)
        await db.audit(
            "SUBSCRIPTION_GRANTED",
            actor_tg_id=callback.from_user.id,
            entity_type="user",
            entity_id=tg_id,
            details="30 days",
        )
        await bot.send_message(
            tg_id,
            "Администратор добавил 30 дней подписки.",
            reply_markup=ui.kb([ui.button("Моя подписка", "subscription")]),
        )
        user = await db.get_user(tg_id)
        await render(
            callback,
            ui.admin_user_text(user),
            ui.admin_user_keyboard(tg_id, True),
        )

    @router.callback_query(F.data.startswith("admin:user:disable:"))
    async def admin_user_disable(callback: CallbackQuery, bot: Bot) -> None:
        if not await require_admin(callback):
            return
        await callback.answer("Отключаю подписку...")
        tg_id = int((callback.data or "").rsplit(":", 1)[1])
        user = await db.get_user(tg_id)
        if not user or not user["remnawave_uuid"]:
            await callback.answer("У пользователя нет подписки.", show_alert=True)
            return
        updated = await remnawave.disable(user["remnawave_uuid"])
        await save_subscription(tg_id, updated)
        await bot.send_message(
            tg_id,
            "<b>Доступ поставлен на паузу</b>\n\n"
            "Подписка сохранена, но подключение временно выключено администратором. "
            "Если это неожиданно, напишите в поддержку.",
            reply_markup=ui.support_keyboard(),
        )
        user = await db.get_user(tg_id)
        await render(
            callback,
            ui.admin_user_text(user),
            ui.admin_user_keyboard(tg_id, True),
        )

    @router.callback_query(F.data.startswith("admin:user:enable:"))
    async def admin_user_enable(callback: CallbackQuery, bot: Bot) -> None:
        if not await require_admin(callback):
            return
        await callback.answer("Включаю подписку...")
        tg_id = int((callback.data or "").rsplit(":", 1)[1])
        user = await db.get_user(tg_id)
        if not user or not user["remnawave_uuid"]:
            await callback.answer("У пользователя нет подписки.", show_alert=True)
            return
        updated = await remnawave.enable(user["remnawave_uuid"])
        await save_subscription(tg_id, updated)
        await bot.send_message(
            tg_id,
            "<b>Доступ снова включён</b>\n\n"
            "Можно обновить подписку в Happ и подключаться как обычно.",
            reply_markup=ui.kb([ui.button("🔑 Моя подписка", "subscription")]),
        )
        user = await db.get_user(tg_id)
        await render(
            callback,
            ui.admin_user_text(user),
            ui.admin_user_keyboard(tg_id, True),
        )

    @router.message()
    async def session_message(message: Message, bot: Bot) -> None:
        await ensure_user(message)
        session = await db.get_session(message.from_user.id)
        if not session:
            await message.answer(
                "Используйте кнопки меню.",
                reply_markup=main_menu_keyboard(message.from_user.id),
            )
            return

        state, payload = session
        proof_type, file_id, text = message_payload(message)

        if state == "payment_proof":
            order_id = int(payload["order_id"])
            order = await db.get_order(order_id)
            if not order or order["tg_id"] != message.from_user.id:
                await db.clear_session(message.from_user.id)
                await message.answer(GENERIC_ERROR)
                return
            if proof_type == "OTHER":
                await message.answer("Отправьте скриншот, документ или текст.")
                return
            submitted = await db.submit_order_proof(
                order_id,
                proof_type=proof_type,
                proof_file_id=file_id,
                proof_text=text,
            )
            if not submitted:
                await db.clear_session(message.from_user.id)
                await message.answer("Этот заказ уже отправлен на проверку.")
                return
            await db.clear_session(message.from_user.id)
            order = await db.get_order(order_id)
            for admin_id in settings.admin_ids:
                try:
                    if proof_type in {"PHOTO", "DOCUMENT"}:
                        await bot.copy_message(
                            admin_id,
                            message.chat.id,
                            message.message_id,
                        )
                    await bot.send_message(
                        admin_id,
                        ui.admin_order_text(order),
                        reply_markup=ui.payment_review_keyboard(order_id),
                    )
                except Exception:
                    LOGGER.exception("Failed to send order %s to admin", order_id)
            await message.answer(
                "<b>Платёж отправлен на проверку</b>\n\n"
                "Когда администратор подтвердит оплату, бот пришлёт уведомление.",
                reply_markup=main_menu_keyboard(message.from_user.id),
            )
            return

        if state == "support_new":
            if not text:
                await message.answer("Опишите проблему текстом или добавьте подпись.")
                return
            ticket_id = await db.create_ticket(message.from_user.id, text)
            await db.clear_session(message.from_user.id)
            ticket = await db.get_ticket(ticket_id)
            for admin_id in settings.admin_ids:
                try:
                    if proof_type in {"PHOTO", "DOCUMENT"}:
                        await bot.copy_message(
                            admin_id,
                            message.chat.id,
                            message.message_id,
                        )
                    await bot.send_message(
                        admin_id,
                        ui.admin_ticket_text(ticket)
                        + f"\n\nСообщение:\n{html.escape(text[:3000])}",
                        reply_markup=ui.ticket_admin_keyboard(ticket_id),
                    )
                except Exception:
                    LOGGER.exception("Failed to send ticket %s to admin", ticket_id)
            await message.answer(
                f"<b>Обращение #{ticket_id} создано</b>\n\n"
                "Ответ администратора придёт в этот чат.",
                reply_markup=main_menu_keyboard(message.from_user.id),
            )
            return

        if state == "admin_ticket_reply":
            if not is_admin(message.from_user.id):
                await db.clear_session(message.from_user.id)
                await message.answer("Недостаточно прав.")
                return
            if not message.text:
                await message.answer("Ответ должен быть текстовым.")
                return
            if len(message.text) > 3500:
                await message.answer(
                    "Ответ слишком длинный. Сократите его до 3500 знаков."
                )
                return
            ticket_id = int(payload["ticket_id"])
            ticket = await db.get_ticket(ticket_id)
            if not ticket or ticket["status"] != "OPEN":
                await db.clear_session(message.from_user.id)
                await message.answer("Обращение уже закрыто.")
                return
            await db.add_ticket_message(
                ticket_id,
                sender_tg_id=message.from_user.id,
                sender_role="ADMIN",
                text=message.text,
            )
            await db.clear_session(message.from_user.id)
            await bot.send_message(
                ticket["tg_id"],
                f"<b>Ответ поддержки по обращению #{ticket_id}</b>\n\n"
                f"{html.escape(message.text)}",
                reply_markup=ui.support_keyboard(),
            )
            await message.answer(
                f"Ответ по обращению #{ticket_id} отправлен.",
                reply_markup=ui.admin_home_keyboard(),
            )
            return

        await db.clear_session(message.from_user.id)
        await message.answer(GENERIC_ERROR)

    @router.errors()
    async def error_handler(event: ErrorEvent, bot: Bot) -> bool:
        error = event.exception
        LOGGER.error(
            "Unhandled bot error",
            exc_info=(type(error), error, error.__traceback__),
        )
        update = event.update
        user_id = None
        try:
            if update.callback_query and update.callback_query.from_user:
                user_id = update.callback_query.from_user.id
                await update.callback_query.answer(GENERIC_ERROR, show_alert=True)
            elif update.message and update.message.from_user:
                user_id = update.message.from_user.id
                await update.message.answer(GENERIC_ERROR)
        except Exception:
            LOGGER.exception("Failed to send generic error to user")
        await notify_error(bot, error, f"пользователь {user_id or 'неизвестен'}")
        return True

    return router

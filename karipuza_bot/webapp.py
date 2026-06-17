from __future__ import annotations

import hashlib
import hmac
import html
import json
import logging
import time
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl

import aiohttp
from aiohttp import web

from .config import TARIFFS, TARIFFS_BY_CODE, Settings, settings, validate_settings
from .database import Database
from .remnawave import RemnawaveClient, Subscription
from .yookassa import YooKassaClient, YooKassaError

LOGGER = logging.getLogger(__name__)
STATIC_DIR = Path(__file__).with_name("web_static")
MAX_TEXT_LENGTH = 3500


@dataclass(frozen=True, slots=True)
class AuthUser:
    tg_id: int
    username: str | None
    first_name: str | None
    is_admin: bool


def row_to_dict(row: Any | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def days_left(timestamp: int) -> int:
    return max(0, (timestamp - int(time.time()) + 86399) // 86400)


def subscription_to_dict(subscription: Subscription | None) -> dict[str, Any] | None:
    if not subscription:
        return None
    return {
        "uuid": subscription.uuid,
        "username": subscription.username,
        "status": subscription.status,
        "subscriptionUrl": subscription.subscription_url,
        "expireAt": subscription.expire_at,
        "daysLeft": days_left(subscription.expire_at),
        "trafficUsed": subscription.traffic_used,
        "trafficLimit": subscription.traffic_limit,
        "isActive": subscription.is_active,
    }


def local_subscription_to_dict(user: Any | None) -> dict[str, Any] | None:
    if not user or not user["subscription_url"]:
        return None
    expire_at = int(user["expire_at"] or 0)
    return {
        "uuid": user["remnawave_uuid"],
        "username": f"tg_{user['tg_id']}",
        "status": user["vpn_status"],
        "subscriptionUrl": user["subscription_url"],
        "expireAt": expire_at,
        "daysLeft": days_left(expire_at),
        "trafficUsed": int(user["traffic_used"] or 0),
        "trafficLimit": 0,
        "isActive": user["vpn_status"] == "ACTIVE" and expire_at > int(time.time()),
        "cached": True,
    }


def safe_text(value: Any, limit: int = MAX_TEXT_LENGTH) -> str:
    text = str(value or "").strip()
    return text[:limit]


def payment_confirmation_url(payment: dict[str, Any] | None) -> str | None:
    confirmation = (payment or {}).get("confirmation")
    if not isinstance(confirmation, dict):
        return None
    url = confirmation.get("confirmation_url")
    return str(url) if url else None


def parse_init_data(raw: str, settings: Settings) -> AuthUser:
    values = dict(parse_qsl(raw, keep_blank_values=True, strict_parsing=False))
    received_hash = values.pop("hash", "")
    if not received_hash:
        raise web.HTTPUnauthorized(text="Missing Telegram hash")

    auth_date = int(values.get("auth_date", "0") or 0)
    if settings.webapp_auth_ttl_seconds > 0:
        age = int(time.time()) - auth_date
        if auth_date <= 0 or age > settings.webapp_auth_ttl_seconds:
            raise web.HTTPUnauthorized(text="Telegram auth data expired")

    data_check_string = "\n".join(f"{key}={values[key]}" for key in sorted(values))
    secret_key = hmac.new(
        b"WebAppData",
        settings.bot_token.encode(),
        hashlib.sha256,
    ).digest()
    calculated_hash = hmac.new(
        secret_key,
        data_check_string.encode(),
        hashlib.sha256,
    ).hexdigest()
    if not hmac.compare_digest(calculated_hash, received_hash):
        raise web.HTTPUnauthorized(text="Bad Telegram signature")

    try:
        user = json.loads(values["user"])
        tg_id = int(user["id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as error:
        raise web.HTTPUnauthorized(text="Bad Telegram user payload") from error

    return AuthUser(
        tg_id=tg_id,
        username=user.get("username"),
        first_name=user.get("first_name"),
        is_admin=tg_id in settings.admin_ids,
    )


def dev_auth(request: web.Request, settings: Settings) -> AuthUser | None:
    if not settings.webapp_dev_auth:
        return None
    if request.remote not in {"127.0.0.1", "::1", "localhost"}:
        return None
    raw_id = request.headers.get("X-Karipuza-Dev-User", "")
    try:
        tg_id = int(raw_id)
    except ValueError:
        tg_id = settings.admin_ids[0] if settings.admin_ids else 999999999
    return AuthUser(
        tg_id=tg_id,
        username="local_dev",
        first_name="Local",
        is_admin=tg_id in settings.admin_ids,
    )


async def require_auth(request: web.Request) -> AuthUser:
    app_settings: Settings = request.app["settings"]
    raw = request.headers.get("X-Telegram-Init-Data", "")
    if raw:
        auth = parse_init_data(raw, app_settings)
    else:
        auth = dev_auth(request, app_settings)
        if not auth:
            raise web.HTTPUnauthorized(text="Telegram auth required")

    db: Database = request.app["db"]
    await db.ensure_user(auth.tg_id, auth.username, auth.first_name)
    return auth


async def read_json(request: web.Request) -> dict[str, Any]:
    try:
        data = await request.json()
    except json.JSONDecodeError as error:
        raise web.HTTPBadRequest(text="Bad JSON") from error
    if not isinstance(data, dict):
        raise web.HTTPBadRequest(text="JSON object expected")
    return data


async def telegram_send(
    app: web.Application,
    chat_id: int,
    text: str,
    *,
    reply_markup: dict[str, Any] | None = None,
) -> None:
    token = app["settings"].bot_token
    if not token:
        return
    payload: dict[str, Any] = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup

    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                f"https://api.telegram.org/bot{token}/sendMessage",
                json=payload,
            ) as response:
                if response.status >= 300:
                    LOGGER.warning(
                        "Telegram sendMessage failed for %s: HTTP %s %s",
                        chat_id,
                        response.status,
                        (await response.text())[:500],
                    )
    except Exception:
        LOGGER.exception("Telegram sendMessage failed for %s", chat_id)


async def notify_admins(app: web.Application, text: str) -> None:
    for admin_id in app["settings"].admin_ids:
        await telegram_send(app, admin_id, text)


async def sync_subscription(
    request: web.Request,
    auth: AuthUser,
) -> tuple[Subscription | None, Any | None, bool]:
    db: Database = request.app["db"]
    remnawave: RemnawaveClient = request.app["remnawave"]
    local_user = await db.get_user(auth.tg_id)
    if not remnawave.configured:
        return None, local_user, False

    try:
        subscription = await remnawave.get_by_telegram_id(auth.tg_id)
    except Exception:
        LOGGER.exception("Mini App subscription sync failed for %s", auth.tg_id)
        await notify_admins(
            request.app,
            "<b>Ошибка Mini App</b>\n\n"
            f"Контекст: синхронизация подписки пользователя {auth.tg_id}\n"
            f"<pre>{html.escape(traceback.format_exc()[-2500:])}</pre>",
        )
        return None, local_user, True

    if subscription:
        await db.save_subscription(
            auth.tg_id,
            remnawave_uuid=subscription.uuid,
            subscription_url=subscription.subscription_url,
            status=subscription.status,
            expire_at=subscription.expire_at,
            traffic_used=subscription.traffic_used,
        )
        local_user = await db.get_user(auth.tg_id)
    return subscription, local_user, False


async def index(request: web.Request) -> web.StreamResponse:
    response = web.FileResponse(STATIC_DIR / "index.html")
    response.headers["Cache-Control"] = "no-cache, max-age=0, must-revalidate"
    return response


async def health(request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "karipuza-mini-app"})


async def api_me(request: web.Request) -> web.Response:
    auth = await require_auth(request)
    db: Database = request.app["db"]
    subscription, local_user, sync_error = await sync_subscription(request, auth)
    orders = [row_to_dict(row) for row in await db.list_user_orders(auth.tg_id, 6)]
    tickets = [row_to_dict(row) for row in await db.list_user_tickets(auth.tg_id, 5)]
    return web.json_response(
        {
            "user": {
                "tgId": auth.tg_id,
                "username": auth.username,
                "firstName": auth.first_name,
                "isAdmin": auth.is_admin,
            },
            "subscription": subscription_to_dict(subscription)
            or local_subscription_to_dict(local_user),
            "orders": orders,
            "tickets": tickets,
            "syncError": sync_error,
            "paymentDetails": request.app["settings"].payment_details,
            "payment": {
                "provider": "yookassa"
                if request.app["settings"].yookassa_ready
                else "manual",
                "yookassaReady": request.app["settings"].yookassa_ready,
                "returnUrl": request.app["settings"].yookassa_return_url,
            },
        }
    )


async def api_plans(request: web.Request) -> web.Response:
    await require_auth(request)
    return web.json_response(
        {
            "plans": [
                {
                    "code": tariff.code,
                    "title": tariff.title,
                    "days": tariff.days,
                    "priceRub": tariff.price_rub,
                    "badge": tariff.badge,
                }
                for tariff in TARIFFS
            ]
        }
    )


async def api_create_order(request: web.Request) -> web.Response:
    auth = await require_auth(request)
    data = await read_json(request)
    tariff = TARIFFS_BY_CODE.get(str(data.get("tariffCode", "")))
    if not tariff:
        raise web.HTTPBadRequest(text="Unknown tariff")

    db: Database = request.app["db"]
    order = await db.find_waiting_order(auth.tg_id, tariff.code)
    if order:
        created = False
    else:
        order_id = await db.create_order(
            auth.tg_id,
            tariff_code=tariff.code,
            title=tariff.title,
            duration_days=tariff.days,
            amount_rub=tariff.price_rub,
        )
        await db.audit(
            "WEBAPP_ORDER_CREATED",
            actor_tg_id=auth.tg_id,
            entity_type="order",
            entity_id=order_id,
        )
        order = await db.get_order(order_id)
        created = True

    payment: dict[str, Any] | None = None
    app_settings: Settings = request.app["settings"]
    if app_settings.yookassa_ready:
        if order["payment_url"] and order["payment_status"] != "succeeded":
            payment = {
                "provider": "yookassa",
                "paymentId": order["payment_id"],
                "status": order["payment_status"],
                "confirmationUrl": order["payment_url"],
            }
        else:
            yookassa: YooKassaClient = request.app["yookassa"]
            try:
                created_payment = await yookassa.create_payment(
                    order_id=int(order["id"]),
                    tg_id=auth.tg_id,
                    tariff_code=tariff.code,
                    title=tariff.title,
                    amount_rub=tariff.price_rub,
                )
            except YooKassaError as error:
                LOGGER.exception("YooKassa payment creation failed")
                await notify_admins(
                    request.app,
                    "<b>Ошибка ЮKassa</b>\n\n"
                    f"Не удалось создать платеж по заказу <b>#{order['id']}</b>.\n"
                    f"<pre>{html.escape(str(error))}</pre>",
                )
                raise web.HTTPBadGateway(
                    text="Ошибка оплаты, обратитесь к админу"
                ) from error

            confirmation_url = payment_confirmation_url(created_payment)
            if not confirmation_url:
                raise web.HTTPBadGateway(text="YooKassa did not return payment URL")

            await db.attach_order_payment(
                int(order["id"]),
                provider="yookassa",
                payment_id=str(created_payment["id"]),
                payment_url=confirmation_url,
                payment_status=str(created_payment.get("status") or ""),
            )
            order = await db.get_order(int(order["id"]))
            payment = {
                "provider": "yookassa",
                "paymentId": str(created_payment["id"]),
                "status": str(created_payment.get("status") or ""),
                "confirmationUrl": confirmation_url,
            }

    return web.json_response(
        {
            "order": row_to_dict(order),
            "created": created,
            "paymentDetails": request.app["settings"].payment_details,
            "payment": payment,
        },
        status=201 if created else 200,
    )


async def activate_paid_order(
    app: web.Application,
    order: Any,
    *,
    audit_action: str,
) -> Subscription:
    db: Database = app["db"]
    remnawave: RemnawaveClient = app["remnawave"]
    name = order["first_name"] or order["username"] or f"TG {order['tg_id']}"
    subscription = await remnawave.activate(
        tg_id=int(order["tg_id"]),
        display_name=str(name),
        days=int(order["duration_days"]),
    )
    await db.save_subscription(
        int(order["tg_id"]),
        remnawave_uuid=subscription.uuid,
        subscription_url=subscription.subscription_url,
        status=subscription.status,
        expire_at=subscription.expire_at,
        traffic_used=subscription.traffic_used,
    )
    await db.set_order_status(int(order["id"]), "APPROVED")
    await db.audit(
        audit_action,
        entity_type="order",
        entity_id=int(order["id"]),
        details=f"payment_id={order['payment_id'] or ''}",
    )
    await telegram_send(
        app,
        int(order["tg_id"]),
        "<b>Оплата прошла</b>\n\n"
        f"Подписка активирована на {order['duration_days']} дней. "
        "Откройте Mini App, скопируйте подписку и обновите профиль в Happ.",
    )
    return subscription


async def api_yookassa_webhook(request: web.Request) -> web.Response:
    yookassa: YooKassaClient = request.app["yookassa"]
    if not yookassa.configured:
        raise web.HTTPServiceUnavailable(text="YooKassa is not configured")

    data = await read_json(request)
    event = str(data.get("event") or "")
    payment_object = data.get("object")
    if not isinstance(payment_object, dict):
        raise web.HTTPBadRequest(text="Payment object is required")

    payment_id = str(payment_object.get("id") or "")
    if not payment_id:
        raise web.HTTPBadRequest(text="Payment id is required")

    verified_payment = await yookassa.get_payment(payment_id)
    verified_status = str(verified_payment.get("status") or "")
    metadata = verified_payment.get("metadata") or {}
    if not isinstance(metadata, dict):
        metadata = {}

    db: Database = request.app["db"]
    order = None
    raw_order_id = metadata.get("order_id")
    if raw_order_id:
        try:
            order = await db.get_order(int(raw_order_id))
        except (TypeError, ValueError):
            order = None
    if not order:
        order = await db.get_order_by_payment_id(payment_id)
    if not order:
        raise web.HTTPNotFound(text="Order not found")

    if not order["payment_id"]:
        await db.attach_order_payment(
            int(order["id"]),
            provider="yookassa",
            payment_id=payment_id,
            payment_url=payment_confirmation_url(verified_payment),
            payment_status=verified_status,
        )
        order = await db.get_order(int(order["id"]))

    if order["payment_id"] and order["payment_id"] != payment_id:
        raise web.HTTPBadRequest(text="Payment does not match order")

    await db.set_order_payment_status(int(order["id"]), payment_status=verified_status)

    if event != "payment.succeeded":
        return web.json_response({"ok": True, "ignored": True})
    if verified_status != "succeeded" or not verified_payment.get("paid"):
        return web.json_response({"ok": True, "waiting": True})

    expected_amount = f"{int(order['amount_rub']):.2f}"
    actual_amount = str((verified_payment.get("amount") or {}).get("value") or "")
    if actual_amount != expected_amount:
        await notify_admins(
            request.app,
            "<b>ЮKassa: сумма платежа не совпала</b>\n\n"
            f"Заказ: <b>#{order['id']}</b>\n"
            f"Ожидали: <b>{expected_amount} ₽</b>\n"
            f"Получили: <b>{html.escape(actual_amount)} ₽</b>\n"
            f"Payment ID: <code>{html.escape(payment_id)}</code>",
        )
        raise web.HTTPBadRequest(text="Payment amount mismatch")

    if order["status"] == "APPROVED":
        return web.json_response({"ok": True, "alreadyApproved": True})

    if order["status"] == "WAITING_PAYMENT":
        claimed = await db.transition_order_status(
            int(order["id"]),
            expected_status="WAITING_PAYMENT",
            new_status="PROCESSING",
        )
        if not claimed:
            order = await db.get_order(int(order["id"]))
    elif order["status"] != "PROCESSING":
        return web.json_response({"ok": True, "ignoredStatus": order["status"]})

    order = await db.get_order(int(order["id"]))
    subscription = await activate_paid_order(
        request.app,
        order,
        audit_action="YOOKASSA_PAYMENT_SUCCEEDED",
    )
    await notify_admins(
        request.app,
        "<b>ЮKassa: подписка выдана автоматически</b>\n\n"
        f"Заказ: <b>#{order['id']}</b>\n"
        f"Telegram ID: <code>{order['tg_id']}</code>\n"
        f"Тариф: <b>{html.escape(str(order['title']))}</b>",
    )
    return web.json_response(
        {
            "ok": True,
            "order": row_to_dict(await db.get_order(int(order["id"]))),
            "subscription": subscription_to_dict(subscription),
        }
    )


async def api_submit_order_proof(request: web.Request) -> web.Response:
    auth = await require_auth(request)
    order_id = int(request.match_info["order_id"])
    data = await read_json(request)
    proof_text = safe_text(data.get("text"))
    if not proof_text:
        raise web.HTTPBadRequest(text="Proof text is required")

    db: Database = request.app["db"]
    order = await db.get_order(order_id)
    if not order or int(order["tg_id"]) != auth.tg_id:
        raise web.HTTPNotFound(text="Order not found")
    submitted = await db.submit_order_proof(
        order_id,
        proof_type="TEXT",
        proof_file_id=None,
        proof_text=proof_text,
    )
    if not submitted:
        raise web.HTTPConflict(text="Order is already submitted")

    order = await db.get_order(order_id)
    user_name = auth.first_name or auth.username or f"TG {auth.tg_id}"
    await notify_admins(
        request.app,
        "<b>Новый платёж на проверку</b>\n\n"
        f"Заказ: <b>#{order_id}</b>\n"
        f"Пользователь: <b>{html.escape(str(user_name))}</b>\n"
        f"Telegram ID: <code>{auth.tg_id}</code>\n"
        f"Тариф: <b>{html.escape(str(order['title']))}</b>\n"
        f"Сумма: <b>{order['amount_rub']} ₽</b>\n\n"
        f"Данные платежа:\n{html.escape(proof_text)}",
    )
    return web.json_response({"ok": True, "order": row_to_dict(order)})


async def api_create_ticket(request: web.Request) -> web.Response:
    auth = await require_auth(request)
    data = await read_json(request)
    text = safe_text(data.get("text"))
    if not text:
        raise web.HTTPBadRequest(text="Message text is required")

    db: Database = request.app["db"]
    ticket_id = await db.create_ticket(auth.tg_id, text)
    ticket = await db.get_ticket(ticket_id)
    user_name = auth.first_name or auth.username or f"TG {auth.tg_id}"
    await notify_admins(
        request.app,
        "<b>Новое обращение в поддержку</b>\n\n"
        f"Обращение: <b>#{ticket_id}</b>\n"
        f"Пользователь: <b>{html.escape(str(user_name))}</b>\n"
        f"Telegram ID: <code>{auth.tg_id}</code>\n\n"
        f"{html.escape(text)}",
    )
    return web.json_response({"ok": True, "ticket": row_to_dict(ticket)}, status=201)


async def require_admin(request: web.Request) -> AuthUser:
    auth = await require_auth(request)
    if not auth.is_admin:
        raise web.HTTPForbidden(text="Admin only")
    return auth


async def api_admin_summary(request: web.Request) -> web.Response:
    await require_admin(request)
    db: Database = request.app["db"]
    remnawave: RemnawaveClient = request.app["remnawave"]
    stats = await db.stats()
    vpn_ok = await remnawave.health() if remnawave.configured else False
    return web.json_response({"stats": stats, "vpnOk": vpn_ok})


async def api_admin_users(request: web.Request) -> web.Response:
    await require_admin(request)
    db: Database = request.app["db"]
    users = [row_to_dict(row) for row in await db.list_users(limit=50)]
    total = await db.count_users()
    return web.json_response({"users": users, "total": total})


async def api_admin_orders(request: web.Request) -> web.Response:
    await require_admin(request)
    status = request.query.get("status") or None
    db: Database = request.app["db"]
    orders = [row_to_dict(row) for row in await db.list_orders(status=status, limit=50)]
    return web.json_response({"orders": orders})


async def api_admin_tickets(request: web.Request) -> web.Response:
    await require_admin(request)
    status = request.query.get("status") or "OPEN"
    db: Database = request.app["db"]
    tickets = []
    for ticket in await db.list_tickets(status=status, limit=50):
        item = row_to_dict(ticket) or {}
        messages = [
            row_to_dict(row)
            for row in await db.list_ticket_messages(int(ticket["id"]), limit=6)
        ]
        item["messages"] = list(reversed(messages))
        tickets.append(item)
    return web.json_response({"tickets": tickets})


async def api_admin_approve_order(request: web.Request) -> web.Response:
    auth = await require_admin(request)
    order_id = int(request.match_info["order_id"])
    db: Database = request.app["db"]
    remnawave: RemnawaveClient = request.app["remnawave"]
    order = await db.get_order(order_id)
    if not order:
        raise web.HTTPNotFound(text="Order not found")

    claimed = await db.transition_order_status(
        order_id,
        expected_status="REVIEW",
        new_status="PROCESSING",
        reviewed_by=auth.tg_id,
    )
    if not claimed:
        raise web.HTTPConflict(text="Order is already processed")

    try:
        name = order["first_name"] or order["username"] or f"TG {order['tg_id']}"
        subscription = await remnawave.activate(
            tg_id=int(order["tg_id"]),
            display_name=str(name),
            days=int(order["duration_days"]),
        )
        await db.save_subscription(
            int(order["tg_id"]),
            remnawave_uuid=subscription.uuid,
            subscription_url=subscription.subscription_url,
            status=subscription.status,
            expire_at=subscription.expire_at,
            traffic_used=subscription.traffic_used,
        )
        await db.set_order_status(order_id, "APPROVED", reviewed_by=auth.tg_id)
        await db.audit(
            "WEBAPP_ORDER_APPROVED",
            actor_tg_id=auth.tg_id,
            entity_type="order",
            entity_id=order_id,
        )
    except Exception:
        await db.transition_order_status(
            order_id,
            expected_status="PROCESSING",
            new_status="REVIEW",
        )
        raise

    await telegram_send(
        request.app,
        int(order["tg_id"]),
        "<b>Оплата подтверждена</b>\n\n"
        f"Подписка продлена на {order['duration_days']} дней. "
        "Откройте Mini App или раздел «Моя подписка», чтобы подключиться.",
    )
    return web.json_response(
        {
            "ok": True,
            "order": row_to_dict(await db.get_order(order_id)),
            "subscription": subscription_to_dict(subscription),
        }
    )


async def api_admin_reject_order(request: web.Request) -> web.Response:
    auth = await require_admin(request)
    order_id = int(request.match_info["order_id"])
    db: Database = request.app["db"]
    order = await db.get_order(order_id)
    if not order:
        raise web.HTTPNotFound(text="Order not found")

    changed = await db.transition_order_status(
        order_id,
        expected_status="REVIEW",
        new_status="REJECTED",
        reviewed_by=auth.tg_id,
    )
    if not changed:
        raise web.HTTPConflict(text="Order is already processed")
    await db.audit(
        "WEBAPP_ORDER_REJECTED",
        actor_tg_id=auth.tg_id,
        entity_type="order",
        entity_id=order_id,
    )
    await telegram_send(
        request.app,
        int(order["tg_id"]),
        f"Платёж по заказу #{order_id} не удалось подтвердить. Напишите в поддержку.",
    )
    return web.json_response(
        {"ok": True, "order": row_to_dict(await db.get_order(order_id))}
    )


async def api_admin_reply_ticket(request: web.Request) -> web.Response:
    auth = await require_admin(request)
    ticket_id = int(request.match_info["ticket_id"])
    data = await read_json(request)
    text = safe_text(data.get("text"))
    if not text:
        raise web.HTTPBadRequest(text="Reply text is required")

    db: Database = request.app["db"]
    ticket = await db.get_ticket(ticket_id)
    if not ticket or ticket["status"] != "OPEN":
        raise web.HTTPNotFound(text="Ticket not found")

    await db.add_ticket_message(
        ticket_id,
        sender_tg_id=auth.tg_id,
        sender_role="ADMIN",
        text=text,
    )
    await db.audit(
        "WEBAPP_TICKET_REPLIED",
        actor_tg_id=auth.tg_id,
        entity_type="ticket",
        entity_id=ticket_id,
    )
    await telegram_send(
        request.app,
        int(ticket["tg_id"]),
        f"<b>Ответ поддержки по обращению #{ticket_id}</b>\n\n{html.escape(text)}",
    )
    return web.json_response(
        {"ok": True, "ticket": row_to_dict(await db.get_ticket(ticket_id))}
    )


async def api_admin_close_ticket(request: web.Request) -> web.Response:
    auth = await require_admin(request)
    ticket_id = int(request.match_info["ticket_id"])
    db: Database = request.app["db"]
    ticket = await db.get_ticket(ticket_id)
    if not ticket:
        raise web.HTTPNotFound(text="Ticket not found")

    await db.close_ticket(ticket_id)
    await db.audit(
        "WEBAPP_TICKET_CLOSED",
        actor_tg_id=auth.tg_id,
        entity_type="ticket",
        entity_id=ticket_id,
    )
    await telegram_send(
        request.app,
        int(ticket["tg_id"]),
        f"Обращение #{ticket_id} закрыто. Если вопрос остался, создайте новое обращение.",
    )
    return web.json_response(
        {"ok": True, "ticket": row_to_dict(await db.get_ticket(ticket_id))}
    )


async def api_admin_grant_user(request: web.Request) -> web.Response:
    auth = await require_admin(request)
    tg_id = int(request.match_info["tg_id"])
    data = await read_json(request)
    days = int(data.get("days") or 30)
    days = min(max(days, 1), 730)

    db: Database = request.app["db"]
    remnawave: RemnawaveClient = request.app["remnawave"]
    user = await db.get_user(tg_id)
    if not user:
        raise web.HTTPNotFound(text="User not found")

    name = user["first_name"] or user["username"] or f"TG {tg_id}"
    subscription = await remnawave.activate(
        tg_id=tg_id,
        display_name=str(name),
        days=days,
    )
    await db.save_subscription(
        tg_id,
        remnawave_uuid=subscription.uuid,
        subscription_url=subscription.subscription_url,
        status=subscription.status,
        expire_at=subscription.expire_at,
        traffic_used=subscription.traffic_used,
    )
    await db.audit(
        "WEBAPP_USER_GRANTED",
        actor_tg_id=auth.tg_id,
        entity_type="user",
        entity_id=tg_id,
        details=f"{days} days",
    )
    await telegram_send(
        request.app,
        tg_id,
        f"<b>Подписка активирована</b>\n\nАдминистратор добавил {days} дней доступа.",
    )
    return web.json_response(
        {"ok": True, "subscription": subscription_to_dict(subscription)}
    )


async def api_admin_user_action(request: web.Request) -> web.Response:
    auth = await require_admin(request)
    tg_id = int(request.match_info["tg_id"])
    action = request.match_info["action"]
    if action not in {"enable", "disable"}:
        raise web.HTTPNotFound()

    db: Database = request.app["db"]
    remnawave: RemnawaveClient = request.app["remnawave"]
    user = await db.get_user(tg_id)
    if not user or not user["remnawave_uuid"]:
        raise web.HTTPNotFound(text="Subscription not found")

    subscription = (
        await remnawave.enable(user["remnawave_uuid"])
        if action == "enable"
        else await remnawave.disable(user["remnawave_uuid"])
    )
    await db.save_subscription(
        tg_id,
        remnawave_uuid=subscription.uuid,
        subscription_url=subscription.subscription_url,
        status=subscription.status,
        expire_at=subscription.expire_at,
        traffic_used=subscription.traffic_used,
    )
    await db.audit(
        f"WEBAPP_USER_{action.upper()}D",
        actor_tg_id=auth.tg_id,
        entity_type="user",
        entity_id=tg_id,
    )
    if action == "disable":
        await telegram_send(
            request.app,
            tg_id,
            "<b>Доступ поставлен на паузу</b>\n\n"
            "Подписка сохранена, но подключение временно выключено администратором. "
            "Если это неожиданно, напишите в поддержку.",
        )
    else:
        await telegram_send(
            request.app,
            tg_id,
            "<b>Доступ снова включён</b>\n\n"
            "Можно обновить подписку в Happ и подключаться как обычно.",
        )
    return web.json_response(
        {"ok": True, "subscription": subscription_to_dict(subscription)}
    )


@web.middleware
async def error_middleware(
    request: web.Request,
    handler,
) -> web.StreamResponse:
    try:
        return await handler(request)
    except web.HTTPException as error:
        if request.path.startswith("/api/"):
            return web.json_response(
                {"ok": False, "error": error.text or error.reason},
                status=error.status,
            )
        raise
    except Exception:
        LOGGER.exception("Unhandled Mini App error")
        if request.path.startswith("/api/"):
            await notify_admins(
                request.app,
                "<b>Ошибка Mini App</b>\n\n"
                f"Путь: <code>{html.escape(request.path)}</code>\n"
                f"<pre>{html.escape(traceback.format_exc()[-2500:])}</pre>",
            )
            return web.json_response(
                {"ok": False, "error": "Ошибка, обратитесь к админу"},
                status=500,
            )
        raise


async def build_app(app_settings: Settings = settings) -> web.Application:
    db = Database(app_settings.database_path)
    await db.init()
    app = web.Application(middlewares=[error_middleware])
    app["settings"] = app_settings
    app["db"] = db
    app["remnawave"] = RemnawaveClient(app_settings)
    app["yookassa"] = YooKassaClient(app_settings)

    app.router.add_get("/", index)
    app.router.add_get("/health", health)
    app.router.add_static("/assets", STATIC_DIR, show_index=False)

    app.router.add_get("/api/me", api_me)
    app.router.add_get("/api/plans", api_plans)
    app.router.add_post("/api/orders", api_create_order)
    app.router.add_post(r"/api/orders/{order_id:\d+}/proof", api_submit_order_proof)
    app.router.add_post("/api/yookassa/webhook", api_yookassa_webhook)
    app.router.add_post("/api/support", api_create_ticket)

    app.router.add_get("/api/admin/summary", api_admin_summary)
    app.router.add_get("/api/admin/users", api_admin_users)
    app.router.add_get("/api/admin/orders", api_admin_orders)
    app.router.add_get("/api/admin/tickets", api_admin_tickets)
    app.router.add_post(
        r"/api/admin/orders/{order_id:\d+}/approve", api_admin_approve_order
    )
    app.router.add_post(
        r"/api/admin/orders/{order_id:\d+}/reject", api_admin_reject_order
    )
    app.router.add_post(
        r"/api/admin/tickets/{ticket_id:\d+}/reply", api_admin_reply_ticket
    )
    app.router.add_post(
        r"/api/admin/tickets/{ticket_id:\d+}/close", api_admin_close_ticket
    )
    app.router.add_post(r"/api/admin/users/{tg_id:\d+}/grant", api_admin_grant_user)
    app.router.add_post(
        r"/api/admin/users/{tg_id:\d+}/{action:enable|disable}",
        api_admin_user_action,
    )
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    validate_settings()
    web.run_app(
        build_app(settings),
        host=settings.webapp_host,
        port=settings.webapp_port,
        print=None,
    )


if __name__ == "__main__":
    main()

import time
from datetime import datetime, timedelta, timezone

import aiohttp

from config import settings


class MarzbanError(Exception):
    pass


async def _get_token() -> str:
    url = f"{settings.marzban_url}/api/admin/token"
    data = {
        "username": settings.marzban_username,
        "password": settings.marzban_password,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(url, data=data) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise MarzbanError(f"Ошибка авторизации Marzban {resp.status}: {text}")

            result = await resp.json()
            token = result.get("access_token")
            if not token:
                raise MarzbanError("Marzban не вернул access_token")

            return token


def _expire_timestamp(days: int) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())


def _extract_link(user_data: dict) -> str:
    links = user_data.get("links") or []
    if links:
        return links[0]

    subscription_url = user_data.get("subscription_url")
    if subscription_url:
        return subscription_url

    raise MarzbanError(
        "Marzban не вернул ссылку. Проверь MARZBAN_INBOUND_TAG и inbound VLESS в Marzban."
    )


def _fix_link_host(link: str) -> str:
    if not settings.public_host:
        return link

    # Аккуратно меняем host только для vless:// ссылок.
    if not link.startswith("vless://"):
        return link

    try:
        prefix, rest = link.split("@", 1)
        host_port_and_query = rest

        if host_port_and_query.startswith("["):
            # IPv6 format: [addr]:port?...
            after_bracket = host_port_and_query.split("]", 1)[1]
            if after_bracket.startswith(":"):
                port_and_query = after_bracket[1:]
                if "?" in port_and_query:
                    port, query = port_and_query.split("?", 1)
                    return f"{prefix}@{settings.public_host}:{port}?{query}"
        else:
            host_port, query = host_port_and_query.split("?", 1)
            if ":" in host_port:
                _, port = host_port.rsplit(":", 1)
                return f"{prefix}@{settings.public_host}:{port}?{query}"

        return link
    except Exception:
        return link


async def create_or_update_user(tg_id: int, days: int, data_limit_gb: int = 0) -> tuple[str, int, str]:
    token = await _get_token()
    marzban_username = f"tg_{tg_id}"
    expire_at = _expire_timestamp(days)
    data_limit = data_limit_gb * 1024 * 1024 * 1024 if data_limit_gb else 0

    payload = {
        "username": marzban_username,
        "proxies": {
            "vless": {}
        },
        "inbounds": {
            "vless": [settings.marzban_inbound_tag]
        },
        "expire": expire_at,
        "data_limit": data_limit,
        "data_limit_reset_strategy": "no_reset",
        "status": "active",
    }

    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(f"{settings.marzban_url}/api/user", json=payload) as resp:
            text = await resp.text()

            if resp.status in (400, 409):
                async with session.put(
                    f"{settings.marzban_url}/api/user/{marzban_username}",
                    json=payload,
                ) as update_resp:
                    update_text = await update_resp.text()
                    if update_resp.status not in (200, 201):
                        raise MarzbanError(f"Ошибка обновления пользователя {update_resp.status}: {update_text}")

            elif resp.status not in (200, 201):
                raise MarzbanError(f"Ошибка создания пользователя {resp.status}: {text}")

        async with session.get(f"{settings.marzban_url}/api/user/{marzban_username}") as resp:
            text = await resp.text()
            if resp.status != 200:
                raise MarzbanError(f"Ошибка получения пользователя {resp.status}: {text}")

            user_data = await resp.json()

    vpn_link = _fix_link_host(_extract_link(user_data))
    return marzban_username, expire_at, vpn_link


async def disable_user(tg_id: int) -> None:
    token = await _get_token()
    marzban_username = f"tg_{tg_id}"
    headers = {"Authorization": f"Bearer {token}"}

    payload = {"status": "disabled"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.put(f"{settings.marzban_url}/api/user/{marzban_username}", json=payload) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                raise MarzbanError(f"Ошибка отключения пользователя {resp.status}: {text}")

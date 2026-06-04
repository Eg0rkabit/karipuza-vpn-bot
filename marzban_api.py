import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit, urlunsplit

import aiohttp
from config import settings


class MarzbanError(Exception):
    pass


async def get_token() -> str:
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
            return result["access_token"]


def _replace_vless_host(link: str, public_host: str | None) -> str:
    if not public_host or not link.startswith("vless://"):
        return link

    # vless://uuid@host:443?params#name
    return re.sub(r"(vless://[^@]+@)(\[[^\]]+\]|[^:?#/]+)(:\d+)", rf"\g<1>{public_host}\3", link, count=1)


async def create_or_update_user(tg_id: int, days: int, data_limit_gb: int = 0) -> tuple[str, int, str]:
    token = await get_token()
    marzban_username = f"tg_{tg_id}"
    expire_at = int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())
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
        "note": f"Telegram ID: {tg_id}",
    }

    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.post(f"{settings.marzban_url}/api/user", json=payload) as resp:
            text = await resp.text()
            if resp.status in (400, 409):
                async with session.put(f"{settings.marzban_url}/api/user/{marzban_username}", json=payload) as update_resp:
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

    links = user_data.get("links") or []
    if not links:
        raise MarzbanError(
            "Marzban не вернул links. Проверь MARZBAN_INBOUND_TAG в .env. "
            f"Сейчас стоит: {settings.marzban_inbound_tag}"
        )

    vpn_link = _replace_vless_host(links[0], settings.public_host)
    return marzban_username, expire_at, vpn_link

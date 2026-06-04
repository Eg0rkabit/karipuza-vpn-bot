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
                raise MarzbanError(f"Marzban auth error {resp.status}: {text}")

            result = await resp.json()
            token = result.get("access_token")
            if not token:
                raise MarzbanError("Marzban не вернул access_token")

            return token


def expire_timestamp(days: int) -> int:
    return int((datetime.now(timezone.utc) + timedelta(days=days)).timestamp())


def fix_vless_host(link: str) -> str:
    if not settings.public_host or not link.startswith("vless://"):
        return link

    try:
        scheme_rest = link[len("vless://"):]
        userinfo, rest = scheme_rest.split("@", 1)

        if rest.startswith("["):
            # IPv6: [addr]:443?...
            _, after = rest.split("]", 1)
            if after.startswith(":"):
                port_query = after[1:]
                if "?" in port_query:
                    port, query = port_query.split("?", 1)
                    return f"vless://{userinfo}@{settings.public_host}:{port}?{query}"
        else:
            host_port, query = rest.split("?", 1)
            if ":" in host_port:
                _, port = host_port.rsplit(":", 1)
                return f"vless://{userinfo}@{settings.public_host}:{port}?{query}"

        return link
    except Exception:
        return link


def extract_user_link(user_data: dict) -> str:
    links = user_data.get("links") or []
    if links:
        return fix_vless_host(str(links[0]))

    subscription_url = user_data.get("subscription_url")
    if subscription_url:
        return str(subscription_url)

    raise MarzbanError(
        "Marzban не вернул links. Проверьте MARZBAN_INBOUND_TAG и inbound в Marzban."
    )


async def create_or_update_user(tg_id: int, days: int, data_limit_gb: int = 0) -> tuple[str, int, str]:
    token = await get_token()
    marzban_username = f"tg_{tg_id}"
    expire_at = expire_timestamp(days)
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
        create_url = f"{settings.marzban_url}/api/user"
        async with session.post(create_url, json=payload) as resp:
            text = await resp.text()

            if resp.status in (400, 409):
                update_url = f"{settings.marzban_url}/api/user/{marzban_username}"
                async with session.put(update_url, json=payload) as update_resp:
                    update_text = await update_resp.text()
                    if update_resp.status not in (200, 201):
                        raise MarzbanError(f"Marzban update user error {update_resp.status}: {update_text}")

            elif resp.status not in (200, 201):
                raise MarzbanError(f"Marzban create user error {resp.status}: {text}")

        get_url = f"{settings.marzban_url}/api/user/{marzban_username}"
        async with session.get(get_url) as resp:
            text = await resp.text()
            if resp.status != 200:
                raise MarzbanError(f"Marzban get user error {resp.status}: {text}")

            user_data = await resp.json()

    vpn_link = extract_user_link(user_data)
    return marzban_username, expire_at, vpn_link


async def disable_user(tg_id: int) -> None:
    token = await get_token()
    marzban_username = f"tg_{tg_id}"
    headers = {"Authorization": f"Bearer {token}"}

    payload = {
        "status": "disabled"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        url = f"{settings.marzban_url}/api/user/{marzban_username}"
        async with session.put(url, json=payload) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                raise MarzbanError(f"Marzban disable user error {resp.status}: {text}")

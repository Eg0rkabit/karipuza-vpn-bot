from datetime import datetime, timedelta, timezone

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
        before_at, after_at = link.split("@", 1)

        if after_at.startswith("["):
            # [IPv6]:443?...
            _, rest = after_at.split("]", 1)
            if rest.startswith(":"):
                port_query = rest[1:]
                if "?" in port_query:
                    port, query = port_query.split("?", 1)
                    return f"{before_at}@{settings.public_host}:{port}?{query}"
        else:
            host_port, query = after_at.split("?", 1)
            if ":" in host_port:
                _, port = host_port.rsplit(":", 1)
                return f"{before_at}@{settings.public_host}:{port}?{query}"

        return link
    except Exception:
        return link


def extract_link(user_data: dict) -> str:
    links = user_data.get("links") or []
    if links:
        fixed_links = [fix_vless_host(str(link)) for link in links if str(link).strip()]
        if fixed_links:
            return "\n".join(fixed_links)

    subscription_url = user_data.get("subscription_url")
    if subscription_url:
        return str(subscription_url)

    raise MarzbanError(
        "Marzban не вернул links. Проверь MARZBAN_INBOUND_TAG и inbound в Marzban."
    )


async def get_user_data(tg_id: int) -> dict | None:
    token = await get_token()
    marzban_username = f"tg_{tg_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{settings.marzban_url}/api/user/{marzban_username}") as resp:
            text = await resp.text()
            if resp.status == 404:
                return None
            if resp.status != 200:
                raise MarzbanError(f"Marzban get user error {resp.status}: {text}")

            return await resp.json()


def is_active_user(user_data: dict) -> bool:
    status = str(user_data.get("status") or "").lower()
    if status != "active":
        return False

    expire = int(user_data.get("expire") or 0)
    return expire == 0 or expire > int(datetime.now(timezone.utc).timestamp())


async def get_active_user(tg_id: int) -> tuple[str, int, str] | None:
    user_data = await get_user_data(tg_id)
    if not user_data or not is_active_user(user_data):
        return None

    username = str(user_data.get("username") or f"tg_{tg_id}")
    expire_at = int(user_data.get("expire") or 0)
    return username, expire_at, extract_link(user_data)


async def enable_user(tg_id: int) -> tuple[str, int, str]:
    token = await get_token()
    marzban_username = f"tg_{tg_id}"
    headers = {"Authorization": f"Bearer {token}"}

    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{settings.marzban_url}/api/user/{marzban_username}") as get_resp:
            text = await get_resp.text()
            if get_resp.status == 404:
                raise MarzbanError(f"Пользователь {marzban_username} не найден в Marzban")
            if get_resp.status != 200:
                raise MarzbanError(f"Marzban get before enable error {get_resp.status}: {text}")
            user_data = await get_resp.json()

        user_data["status"] = "active"

        async with session.put(f"{settings.marzban_url}/api/user/{marzban_username}", json=user_data) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                raise MarzbanError(f"Marzban enable error {resp.status}: {text}")

        async with session.get(f"{settings.marzban_url}/api/user/{marzban_username}") as resp:
            text = await resp.text()
            if resp.status != 200:
                raise MarzbanError(f"Marzban get after enable error {resp.status}: {text}")
            enabled_user_data = await resp.json()

    username = str(enabled_user_data.get("username") or marzban_username)
    expire_at = int(enabled_user_data.get("expire") or 0)
    return username, expire_at, extract_link(enabled_user_data)


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
            "vless": settings.marzban_inbound_tags
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
                        raise MarzbanError(f"Marzban update error {update_resp.status}: {update_text}")

            elif resp.status not in (200, 201):
                raise MarzbanError(f"Marzban create error {resp.status}: {text}")

        async with session.get(f"{settings.marzban_url}/api/user/{marzban_username}") as resp:
            text = await resp.text()
            if resp.status != 200:
                raise MarzbanError(f"Marzban get user error {resp.status}: {text}")

            user_data = await resp.json()

    return marzban_username, expire_at, extract_link(user_data)


async def disable_user(tg_id: int) -> None:
    token = await get_token()
    marzban_username = f"tg_{tg_id}"
    headers = {"Authorization": f"Bearer {token}"}

    # В некоторых версиях Marzban PUT с частичным payload не проходит,
    # поэтому сначала получаем пользователя и меняем status.
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(f"{settings.marzban_url}/api/user/{marzban_username}") as get_resp:
            text = await get_resp.text()
            if get_resp.status != 200:
                raise MarzbanError(f"Marzban get before disable error {get_resp.status}: {text}")
            user_data = await get_resp.json()

        user_data["status"] = "disabled"

        async with session.put(f"{settings.marzban_url}/api/user/{marzban_username}", json=user_data) as resp:
            text = await resp.text()
            if resp.status not in (200, 201):
                raise MarzbanError(f"Marzban disable error {resp.status}: {text}")

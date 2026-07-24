from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import aiohttp

from .config import Settings


class RemnawaveError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class Subscription:
    uuid: str
    username: str
    status: str
    subscription_url: str
    expire_at: int
    traffic_used: int
    traffic_limit: int
    device_limit: int

    @property
    def is_active(self) -> bool:
        return self.status == "ACTIVE" and self.expire_at > int(
            datetime.now(timezone.utc).timestamp()
        )


class RemnawaveClient:
    def __init__(self, settings: Settings):
        self.base_url = settings.remnawave_url
        self.api_token = settings.remnawave_api_token
        self.squad_uuids = settings.remnawave_squad_uuids
        self.device_limit = settings.subscription_device_limit

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_token and self.squad_uuids)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        if not self.api_token:
            raise RemnawaveError("REMNAWAVE_API_TOKEN не настроен")

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Accept": "application/json",
        }
        timeout = aiohttp.ClientTimeout(total=15)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.request(
                method, f"{self.base_url}{path}", json=json
            ) as response:
                text = await response.text()
                if allow_not_found and response.status == 404:
                    return None
                if response.status < 200 or response.status >= 300:
                    raise RemnawaveError(
                        f"Remnawave {method} {path}: HTTP {response.status}: {text[:500]}"
                    )
                if not text:
                    return {}
                try:
                    return await response.json()
                except Exception as error:
                    raise RemnawaveError(
                        f"Remnawave вернул некорректный JSON: {text[:500]}"
                    ) from error

    @staticmethod
    def _timestamp(value: str | None) -> int:
        if not value:
            return 0
        return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp())

    @classmethod
    def _subscription(cls, payload: dict[str, Any]) -> Subscription:
        traffic = payload.get("userTraffic") or {}
        return Subscription(
            uuid=str(payload["uuid"]),
            username=str(payload["username"]),
            status=str(payload.get("status") or "UNKNOWN"),
            subscription_url=str(payload.get("subscriptionUrl") or ""),
            expire_at=cls._timestamp(payload.get("expireAt")),
            traffic_used=int(traffic.get("usedTrafficBytes") or 0),
            traffic_limit=int(payload.get("trafficLimitBytes") or 0),
            device_limit=int(payload.get("hwidDeviceLimit") or 0),
        )

    async def health(self) -> bool:
        if not self.api_token:
            return False
        try:
            await self._request("GET", "/api/system/health")
        except Exception:
            return False
        return True

    async def get_by_telegram_id(self, tg_id: int) -> Subscription | None:
        result = await self._request(
            "GET",
            f"/api/users/by-telegram-id/{tg_id}",
            allow_not_found=True,
        )
        if not result:
            return None
        users = result.get("response") or []
        if not users:
            return None
        users.sort(key=lambda item: item.get("createdAt") or "", reverse=True)
        return self._subscription(users[0])

    async def get_by_uuid(self, uuid: str) -> Subscription | None:
        result = await self._request("GET", f"/api/users/{uuid}", allow_not_found=True)
        if not result:
            return None
        return self._subscription(result["response"])

    async def ensure_device_limit_enabled(self) -> bool:
        if not self.configured or self.device_limit < 1:
            return False

        result = await self._request("GET", "/api/subscription-settings")
        current = (result or {}).get("response") or {}
        settings_uuid = str(current.get("uuid") or "")
        if not settings_uuid:
            raise RemnawaveError("Remnawave не вернул UUID настроек подписки")

        hwid = current.get("hwidSettings") or {}
        if (
            hwid.get("enabled") is True
            and int(hwid.get("fallbackDeviceLimit") or 0) == self.device_limit
        ):
            return False

        announce = hwid.get("maxDevicesAnnounce") or (
            f"К одной подписке можно подключить до {self.device_limit} устройств. "
            "Чтобы удалить старое устройство, обратитесь в поддержку."
        )
        await self._request(
            "PATCH",
            "/api/subscription-settings",
            json={
                "uuid": settings_uuid,
                "hwidSettings": {
                    "enabled": True,
                    "fallbackDeviceLimit": self.device_limit,
                    "maxDevicesAnnounce": announce,
                },
            },
        )
        return True

    async def activate(
        self,
        *,
        tg_id: int,
        display_name: str,
        days: int,
    ) -> Subscription:
        if not self.configured:
            raise RemnawaveError(
                "Remnawave ещё не готов: нужен API-токен и UUID внутренней группы"
            )

        current = await self.get_by_telegram_id(tg_id)
        now = datetime.now(timezone.utc)
        if current and current.expire_at > int(now.timestamp()):
            start = datetime.fromtimestamp(current.expire_at, timezone.utc)
        else:
            start = now
        expire_at = start + timedelta(days=days)
        expire_iso = expire_at.isoformat(timespec="milliseconds").replace("+00:00", "Z")

        if current:
            result = await self._request(
                "PATCH",
                "/api/users",
                json={
                    "uuid": current.uuid,
                    "status": "ACTIVE",
                    "expireAt": expire_iso,
                    "activeInternalSquads": list(self.squad_uuids),
                    "telegramId": tg_id,
                    "description": display_name[:200],
                    "hwidDeviceLimit": self.device_limit,
                },
            )
        else:
            result = await self._request(
                "POST",
                "/api/users",
                json={
                    "username": f"tg_{tg_id}",
                    "status": "ACTIVE",
                    "expireAt": expire_iso,
                    "trafficLimitBytes": 0,
                    "trafficLimitStrategy": "NO_RESET",
                    "telegramId": tg_id,
                    "description": display_name[:200],
                    "activeInternalSquads": list(self.squad_uuids),
                    "hwidDeviceLimit": self.device_limit,
                },
            )

        if not result or "response" not in result:
            raise RemnawaveError("Remnawave не вернул созданного пользователя")
        return self._subscription(result["response"])

    async def disable(self, uuid: str) -> Subscription:
        result = await self._request("POST", f"/api/users/{uuid}/actions/disable")
        if not result:
            raise RemnawaveError("Remnawave не вернул пользователя после отключения")
        return self._subscription(result["response"])

    async def enable(self, uuid: str) -> Subscription:
        result = await self._request("POST", f"/api/users/{uuid}/actions/enable")
        if not result:
            raise RemnawaveError("Remnawave не вернул пользователя после включения")
        return self._subscription(result["response"])

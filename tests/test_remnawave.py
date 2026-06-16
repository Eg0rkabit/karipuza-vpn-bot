from __future__ import annotations

import unittest
from pathlib import Path
from typing import Any

from karipuza_bot.config import Settings
from karipuza_bot.remnawave import RemnawaveClient


def user_payload(*, expire_at: str = "2026-07-15T12:00:00.000Z") -> dict[str, Any]:
    return {
        "uuid": "11111111-1111-1111-1111-111111111111",
        "username": "tg_100",
        "status": "ACTIVE",
        "subscriptionUrl": "https://sub.example/api/sub/abc",
        "expireAt": expire_at,
        "trafficLimitBytes": 0,
        "createdAt": "2026-06-15T12:00:00.000Z",
        "userTraffic": {"usedTrafficBytes": 1024},
    }


class FakeRemnawaveClient(RemnawaveClient):
    def __init__(self, settings: Settings):
        super().__init__(settings)
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.existing: dict[str, Any] | None = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, Any] | None = None,
        allow_not_found: bool = False,
    ) -> dict[str, Any] | None:
        self.calls.append((method, path, json))
        if path.startswith("/api/users/by-telegram-id/"):
            return {"response": [self.existing] if self.existing else []}
        return {"response": user_payload()}


class RemnawaveClientTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        settings = Settings(
            bot_token="token",
            admin_ids=(1,),
            database_path=Path("test.db"),
            mini_app_url="https://app.example",
            webapp_host="127.0.0.1",
            webapp_port=8080,
            webapp_dev_auth=False,
            webapp_auth_ttl_seconds=86400,
            remnawave_url="http://127.0.0.1:3000",
            remnawave_api_token="api-token",
            remnawave_squad_uuids=("22222222-2222-2222-2222-222222222222",),
            payment_details="details",
            yookassa_shop_id="",
            yookassa_secret_key="",
            yookassa_return_url="https://app.example",
            action_cooldown_seconds=0.8,
            heavy_action_cooldown_seconds=3,
        )
        self.client = FakeRemnawaveClient(settings)

    async def test_create_user_payload_matches_remnawave_contract(self) -> None:
        subscription = await self.client.activate(
            tg_id=100,
            display_name="Тест",
            days=30,
        )
        method, path, payload = self.client.calls[-1]

        self.assertEqual((method, path), ("POST", "/api/users"))
        self.assertEqual(payload["telegramId"], 100)
        self.assertEqual(payload["trafficLimitStrategy"], "NO_RESET")
        self.assertEqual(
            payload["activeInternalSquads"],
            ["22222222-2222-2222-2222-222222222222"],
        )
        self.assertEqual(subscription.traffic_used, 1024)

    async def test_existing_user_is_updated(self) -> None:
        self.client.existing = user_payload()
        await self.client.activate(tg_id=100, display_name="Тест", days=30)
        method, path, payload = self.client.calls[-1]

        self.assertEqual((method, path), ("PATCH", "/api/users"))
        self.assertEqual(payload["uuid"], self.client.existing["uuid"])

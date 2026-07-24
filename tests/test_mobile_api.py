from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from aiohttp.test_utils import TestClient, TestServer

from karipuza_bot.config import Settings
from karipuza_bot.webapp import build_app, subscription_url_for_client


class SubscriptionUrlTests(unittest.TestCase):
    def test_appends_explicit_singbox_format(self) -> None:
        self.assertEqual(
            subscription_url_for_client("https://sub.karipuza.ru/secret-token"),
            "https://sub.karipuza.ru/secret-token/singbox",
        )

    def test_preserves_query_and_does_not_duplicate_format(self) -> None:
        self.assertEqual(
            subscription_url_for_client(
                "https://sub.karipuza.ru/secret-token/singbox?foo=bar"
            ),
            "https://sub.karipuza.ru/secret-token/singbox?foo=bar",
        )

    def test_removes_fragment(self) -> None:
        self.assertEqual(
            subscription_url_for_client("https://sub.karipuza.ru/secret-token#unused"),
            "https://sub.karipuza.ru/secret-token/singbox",
        )


class MobileApiTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        settings = Settings(
            bot_token="123456:test-token",
            bot_username="karipaza_test_bot",
            admin_ids=(1,),
            database_path=Path(self.temp_dir.name) / "mobile-api.db",
            mini_app_url="https://app.example",
            webapp_host="127.0.0.1",
            webapp_port=8080,
            webapp_dev_auth=False,
            webapp_auth_ttl_seconds=86400,
            mobile_auth_ttl_seconds=600,
            mobile_session_ttl_days=180,
            mobile_subscription_max_bytes=2097152,
            mobile_subscription_allowed_hosts=("sub.karipuza.ru",),
            remnawave_url="http://127.0.0.1:3002",
            remnawave_api_token="",
            remnawave_squad_uuids=(),
            payment_details="",
            yookassa_shop_id="",
            yookassa_secret_key="",
            yookassa_return_url="",
            action_cooldown_seconds=0.8,
            heavy_action_cooldown_seconds=3,
        )
        app = await build_app(settings)
        self.client = TestClient(TestServer(app))
        await self.client.start_server()

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.temp_dir.cleanup()

    async def test_telegram_device_login_and_logout(self) -> None:
        start_response = await self.client.post(
            "/api/mobile/auth/start",
            json={
                "deviceId": "test-device-12345",
                "deviceName": "Pixel Test",
                "platform": "ANDROID",
            },
        )
        self.assertEqual(start_response.status, 201)
        challenge = await start_response.json()
        self.assertIn("karipaza_test_bot", challenge["botUrl"])
        self.assertNotIn("test-token", str(challenge))

        pending_response = await self.client.post(
            "/api/mobile/auth/complete",
            json={
                "requestId": challenge["requestId"],
                "secret": challenge["secret"],
            },
        )
        self.assertEqual(pending_response.status, 202)

        db = self.client.app["db"]
        await db.ensure_user(100, "tester", "Тест")
        approved = await db.approve_mobile_auth_request(
            challenge["requestId"],
            100,
        )
        self.assertEqual(approved, "APPROVED")

        complete_response = await self.client.post(
            "/api/mobile/auth/complete",
            json={
                "requestId": challenge["requestId"],
                "secret": challenge["secret"],
            },
        )
        self.assertEqual(complete_response.status, 200)
        token = (await complete_response.json())["token"]

        me_response = await self.client.get(
            "/api/mobile/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_response.status, 200)
        me = await me_response.json()
        self.assertEqual(me["user"]["tgId"], 100)
        self.assertEqual(me["device"]["name"], "Pixel Test")
        self.assertFalse(me["payment"]["enabled"])
        self.assertNotIn("subscriptionUrl", str(me))

        logout_response = await self.client.post(
            "/api/mobile/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(logout_response.status, 200)

        expired_response = await self.client.get(
            "/api/mobile/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(expired_response.status, 401)

    async def test_invalid_device_id_is_rejected(self) -> None:
        response = await self.client.post(
            "/api/mobile/auth/start",
            json={
                "deviceId": "short",
                "deviceName": "Android",
            },
        )
        self.assertEqual(response.status, 400)

    async def test_public_legal_pages_are_available_without_auth(self) -> None:
        expected = {
            "/documents": (
                "Соглашения и тарифы",
                "229 ₽",
                "1979 ₽",
                "до 5 личных устройств",
            ),
            "/privacy": (
                "Политика конфиденциальности",
                "Написать в поддержку",
                "Platega",
                "HWID",
            ),
            "/terms": (
                "Пользовательское соглашение",
                "Отказ от услуги и возврат",
                "до 5 личных устройств",
            ),
        }

        for path, snippets in expected.items():
            with self.subTest(path=path):
                response = await self.client.get(path)
                self.assertEqual(response.status, 200)
                self.assertEqual(response.content_type, "text/html")
                self.assertIn(
                    "default-src 'none'",
                    response.headers["Content-Security-Policy"],
                )
                body = await response.text()
                self.assertIn("Karipaza Froxy", body)
                self.assertIn(
                    "https://t.me/karipaza_test_bot?start=support",
                    body,
                )
                for snippet in snippets:
                    self.assertIn(snippet, body)

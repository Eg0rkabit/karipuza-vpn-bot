from __future__ import annotations

import tempfile
import time
import unittest
from pathlib import Path

import aiosqlite

from karipuza_bot.database import Database


class DatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db = Database(Path(self.temp_dir.name) / "karipuza.db")
        await self.db.init()
        await self.db.ensure_user(100, "tester", "Тест")

    async def asyncTearDown(self) -> None:
        self.temp_dir.cleanup()

    async def test_order_can_only_be_claimed_once(self) -> None:
        order_id = await self.db.create_order(
            100,
            tariff_code="month_1",
            title="1 месяц",
            duration_days=30,
            amount_rub=299,
        )
        submitted = await self.db.submit_order_proof(
            order_id,
            proof_type="TEXT",
            proof_file_id=None,
            proof_text="Оплачено",
        )
        self.assertTrue(submitted)

        first = await self.db.transition_order_status(
            order_id,
            expected_status="REVIEW",
            new_status="PROCESSING",
            reviewed_by=1,
        )
        second = await self.db.transition_order_status(
            order_id,
            expected_status="REVIEW",
            new_status="PROCESSING",
            reviewed_by=2,
        )

        self.assertTrue(first)
        self.assertFalse(second)

    async def test_waiting_order_can_be_reused(self) -> None:
        order_id = await self.db.create_order(
            100,
            tariff_code="month_1",
            title="1 месяц",
            duration_days=30,
            amount_rub=299,
        )

        waiting = await self.db.find_waiting_order(100, "month_1")

        self.assertEqual(waiting["id"], order_id)

    async def test_order_payment_fields_are_saved(self) -> None:
        order_id = await self.db.create_order(
            100,
            tariff_code="month_1",
            title="1 месяц",
            duration_days=30,
            amount_rub=299,
        )

        saved = await self.db.attach_order_payment(
            order_id,
            provider="yookassa",
            payment_id="pay_123",
            payment_url="https://yoomoney.ru/payment",
            payment_status="pending",
        )
        self.assertTrue(saved)

        order = await self.db.get_order_by_payment_id("pay_123")

        self.assertEqual(order["id"], order_id)
        self.assertEqual(order["payment_provider"], "yookassa")
        self.assertEqual(order["payment_url"], "https://yoomoney.ru/payment")

        await self.db.set_order_payment_status(order_id, payment_status="succeeded")
        updated = await self.db.get_order(order_id)
        self.assertEqual(updated["payment_status"], "succeeded")

    async def test_old_orders_schema_is_migrated(self) -> None:
        old_db_path = Path(self.temp_dir.name) / "old-schema.db"
        async with aiosqlite.connect(old_db_path) as connection:
            await connection.executescript(
                """
                CREATE TABLE users (
                    tg_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    remnawave_uuid TEXT,
                    subscription_url TEXT,
                    vpn_status TEXT NOT NULL DEFAULT 'NONE',
                    expire_at INTEGER NOT NULL DEFAULT 0,
                    traffic_used INTEGER NOT NULL DEFAULT 0,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                    tariff_code TEXT NOT NULL,
                    title TEXT NOT NULL,
                    duration_days INTEGER NOT NULL,
                    amount_rub INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    proof_type TEXT,
                    proof_file_id TEXT,
                    proof_text TEXT,
                    reviewed_by INTEGER,
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );
                """
            )
            await connection.commit()

        migrated = Database(old_db_path)
        await migrated.init()

        async with migrated.connect() as connection:
            cursor = await connection.execute("PRAGMA table_info(orders)")
            columns = {row[1] for row in await cursor.fetchall()}
            cursor = await connection.execute(
                """
                SELECT name FROM sqlite_master
                WHERE type = 'index' AND name = 'idx_orders_payment_id'
                """
            )
            index = await cursor.fetchone()

        self.assertIn("payment_id", columns)
        self.assertIsNotNone(index)

    async def test_ticket_and_session_flow(self) -> None:
        await self.db.set_session(100, "support_new", {"source": "menu"})
        self.assertEqual(
            await self.db.get_session(100),
            ("support_new", {"source": "menu"}),
        )

        ticket_id = await self.db.create_ticket(100, "Не подключается")
        await self.db.add_ticket_message(
            ticket_id,
            sender_tg_id=1,
            sender_role="ADMIN",
            text="Проверяем",
        )
        ticket = await self.db.get_ticket(ticket_id)

        self.assertEqual(ticket["status"], "OPEN")
        self.assertEqual((await self.db.stats())["tickets"], 1)

    async def test_mobile_auth_creates_and_revokes_device_session(self) -> None:
        expires_at = int(time.time()) + 600
        await self.db.create_mobile_auth_request(
            request_id="request-one",
            secret_hash="secret-hash-one",
            device_id="device-12345",
            device_name="Pixel Test",
            platform="ANDROID",
            expires_at=expires_at,
        )

        self.assertEqual(
            await self.db.approve_mobile_auth_request("request-one", 100),
            "APPROVED",
        )
        status, tg_id = await self.db.consume_mobile_auth_request(
            request_id="request-one",
            secret_hash="secret-hash-one",
            token_hash="token-hash-one",
            session_expires_at=int(time.time()) + 86400,
        )

        self.assertEqual((status, tg_id), ("AUTHORIZED", 100))
        session = await self.db.get_mobile_session("token-hash-one")
        self.assertEqual(session["device_name"], "Pixel Test")
        self.assertTrue(await self.db.revoke_mobile_session("token-hash-one"))
        self.assertIsNone(await self.db.get_mobile_session("token-hash-one"))

    async def test_mobile_auth_waits_for_telegram_confirmation(self) -> None:
        await self.db.create_mobile_auth_request(
            request_id="request-pending",
            secret_hash="secret-hash-pending",
            device_id="device-pending",
            device_name="Android",
            platform="ANDROID",
            expires_at=int(time.time()) + 600,
        )

        status, tg_id = await self.db.consume_mobile_auth_request(
            request_id="request-pending",
            secret_hash="secret-hash-pending",
            token_hash="token-hash-pending",
            session_expires_at=int(time.time()) + 86400,
        )

        self.assertEqual((status, tg_id), ("PENDING", None))

    async def test_mobile_auth_rejects_wrong_or_expired_secret(self) -> None:
        await self.db.create_mobile_auth_request(
            request_id="request-expired",
            secret_hash="correct-hash",
            device_id="device-expired",
            device_name="Android",
            platform="ANDROID",
            expires_at=int(time.time()) - 1,
        )

        wrong_status, _ = await self.db.consume_mobile_auth_request(
            request_id="request-expired",
            secret_hash="wrong-hash",
            token_hash="unused",
            session_expires_at=int(time.time()) + 86400,
        )
        expired_status = await self.db.approve_mobile_auth_request(
            "request-expired", 100
        )

        self.assertEqual(wrong_status, "INVALID_SECRET")
        self.assertEqual(expired_status, "EXPIRED")

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

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

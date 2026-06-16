from __future__ import annotations

import json
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, AsyncIterator

import aiosqlite


class Database:
    def __init__(self, path: Path):
        self.path = path

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[aiosqlite.Connection]:
        connection = await aiosqlite.connect(self.path)
        connection.row_factory = aiosqlite.Row
        await connection.execute("PRAGMA foreign_keys = ON")
        await connection.execute("PRAGMA busy_timeout = 5000")
        try:
            yield connection
        finally:
            await connection.close()

    async def init(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        async with self.connect() as db:
            await db.execute("PRAGMA journal_mode = WAL")
            await db.executescript(
                """
                CREATE TABLE IF NOT EXISTS users (
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

                CREATE TABLE IF NOT EXISTS orders (
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

                CREATE INDEX IF NOT EXISTS idx_orders_status
                ON orders(status, created_at DESC);

                CREATE TABLE IF NOT EXISTS tickets (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                    status TEXT NOT NULL DEFAULT 'OPEN',
                    subject TEXT NOT NULL DEFAULT 'Поддержка',
                    created_at INTEGER NOT NULL,
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS ticket_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ticket_id INTEGER NOT NULL REFERENCES tickets(id),
                    sender_tg_id INTEGER NOT NULL,
                    sender_role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    created_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS sessions (
                    tg_id INTEGER PRIMARY KEY,
                    state TEXT NOT NULL,
                    payload TEXT NOT NULL DEFAULT '{}',
                    updated_at INTEGER NOT NULL
                );

                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    actor_tg_id INTEGER,
                    action TEXT NOT NULL,
                    entity_type TEXT,
                    entity_id TEXT,
                    details TEXT,
                    created_at INTEGER NOT NULL
                );
                """
            )
            await db.commit()

    async def ensure_user(
        self, tg_id: int, username: str | None, first_name: str | None
    ) -> None:
        now = int(time.time())
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO users (tg_id, username, first_name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET
                    username = excluded.username,
                    first_name = excluded.first_name,
                    updated_at = excluded.updated_at
                """,
                (tg_id, username, first_name, now, now),
            )
            await db.commit()

    async def get_user(self, tg_id: int) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute("SELECT * FROM users WHERE tg_id = ?", (tg_id,))
            return await cursor.fetchone()

    async def list_users(self, limit: int = 10, offset: int = 0) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT * FROM users
                ORDER BY updated_at DESC, created_at DESC
                LIMIT ? OFFSET ?
                """,
                (limit, offset),
            )
            return await cursor.fetchall()

    async def count_users(self) -> int:
        async with self.connect() as db:
            cursor = await db.execute("SELECT COUNT(*) FROM users")
            row = await cursor.fetchone()
            return int(row[0])

    async def save_subscription(
        self,
        tg_id: int,
        *,
        remnawave_uuid: str,
        subscription_url: str,
        status: str,
        expire_at: int,
        traffic_used: int,
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE users SET
                    remnawave_uuid = ?,
                    subscription_url = ?,
                    vpn_status = ?,
                    expire_at = ?,
                    traffic_used = ?,
                    updated_at = ?
                WHERE tg_id = ?
                """,
                (
                    remnawave_uuid,
                    subscription_url,
                    status,
                    expire_at,
                    traffic_used,
                    int(time.time()),
                    tg_id,
                ),
            )
            await db.commit()

    async def clear_subscription(self, tg_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                UPDATE users SET
                    remnawave_uuid = NULL,
                    subscription_url = NULL,
                    vpn_status = 'NONE',
                    expire_at = 0,
                    traffic_used = 0,
                    updated_at = ?
                WHERE tg_id = ?
                """,
                (int(time.time()), tg_id),
            )
            await db.commit()

    async def create_order(
        self,
        tg_id: int,
        *,
        tariff_code: str,
        title: str,
        duration_days: int,
        amount_rub: int,
    ) -> int:
        now = int(time.time())
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO orders (
                    tg_id, tariff_code, title, duration_days, amount_rub,
                    status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'WAITING_PAYMENT', ?, ?)
                """,
                (
                    tg_id,
                    tariff_code,
                    title,
                    duration_days,
                    amount_rub,
                    now,
                    now,
                ),
            )
            await db.commit()
            return int(cursor.lastrowid)

    async def find_waiting_order(
        self, tg_id: int, tariff_code: str
    ) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT orders.*, users.username, users.first_name
                FROM orders
                JOIN users ON users.tg_id = orders.tg_id
                WHERE orders.tg_id = ?
                  AND orders.tariff_code = ?
                  AND orders.status = 'WAITING_PAYMENT'
                ORDER BY orders.created_at DESC
                LIMIT 1
                """,
                (tg_id, tariff_code),
            )
            return await cursor.fetchone()

    async def get_order(self, order_id: int) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT orders.*, users.username, users.first_name
                FROM orders
                JOIN users ON users.tg_id = orders.tg_id
                WHERE orders.id = ?
                """,
                (order_id,),
            )
            return await cursor.fetchone()

    async def submit_order_proof(
        self,
        order_id: int,
        *,
        proof_type: str,
        proof_file_id: str | None,
        proof_text: str | None,
    ) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE orders SET
                    status = 'REVIEW',
                    proof_type = ?,
                    proof_file_id = ?,
                    proof_text = ?,
                    updated_at = ?
                WHERE id = ? AND status = 'WAITING_PAYMENT'
                """,
                (
                    proof_type,
                    proof_file_id,
                    proof_text,
                    int(time.time()),
                    order_id,
                ),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def set_order_status(
        self, order_id: int, status: str, reviewed_by: int | None = None
    ) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE orders SET status = ?, reviewed_by = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, reviewed_by, int(time.time()), order_id),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def transition_order_status(
        self,
        order_id: int,
        *,
        expected_status: str,
        new_status: str,
        reviewed_by: int | None = None,
    ) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE orders SET status = ?, reviewed_by = ?, updated_at = ?
                WHERE id = ? AND status = ?
                """,
                (
                    new_status,
                    reviewed_by,
                    int(time.time()),
                    order_id,
                    expected_status,
                ),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def list_orders(
        self, status: str | None = None, limit: int = 20
    ) -> list[aiosqlite.Row]:
        query = """
            SELECT orders.*, users.username, users.first_name
            FROM orders
            JOIN users ON users.tg_id = orders.tg_id
        """
        params: tuple[Any, ...]
        if status:
            query += " WHERE orders.status = ?"
            params = (status, limit)
        else:
            params = (limit,)
        query += " ORDER BY orders.created_at DESC LIMIT ?"

        async with self.connect() as db:
            cursor = await db.execute(query, params)
            return await cursor.fetchall()

    async def list_user_orders(
        self, tg_id: int, limit: int = 10
    ) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT orders.*, users.username, users.first_name
                FROM orders
                JOIN users ON users.tg_id = orders.tg_id
                WHERE orders.tg_id = ?
                ORDER BY orders.created_at DESC
                LIMIT ?
                """,
                (tg_id, limit),
            )
            return await cursor.fetchall()

    async def create_ticket(self, tg_id: int, text: str) -> int:
        now = int(time.time())
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO tickets (tg_id, status, created_at, updated_at)
                VALUES (?, 'OPEN', ?, ?)
                """,
                (tg_id, now, now),
            )
            ticket_id = int(cursor.lastrowid)
            await db.execute(
                """
                INSERT INTO ticket_messages (
                    ticket_id, sender_tg_id, sender_role, text, created_at
                )
                VALUES (?, ?, 'USER', ?, ?)
                """,
                (ticket_id, tg_id, text, now),
            )
            await db.commit()
            return ticket_id

    async def get_ticket(self, ticket_id: int) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT tickets.*, users.username, users.first_name
                FROM tickets
                JOIN users ON users.tg_id = tickets.tg_id
                WHERE tickets.id = ?
                """,
                (ticket_id,),
            )
            return await cursor.fetchone()

    async def list_tickets(
        self, status: str = "OPEN", limit: int = 20
    ) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT tickets.*, users.username, users.first_name
                FROM tickets
                JOIN users ON users.tg_id = tickets.tg_id
                WHERE tickets.status = ?
                ORDER BY tickets.updated_at DESC
                LIMIT ?
                """,
                (status, limit),
            )
            return await cursor.fetchall()

    async def list_user_tickets(
        self, tg_id: int, limit: int = 10
    ) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT tickets.*, users.username, users.first_name
                FROM tickets
                JOIN users ON users.tg_id = tickets.tg_id
                WHERE tickets.tg_id = ?
                ORDER BY tickets.updated_at DESC
                LIMIT ?
                """,
                (tg_id, limit),
            )
            return await cursor.fetchall()

    async def add_ticket_message(
        self,
        ticket_id: int,
        *,
        sender_tg_id: int,
        sender_role: str,
        text: str,
    ) -> None:
        now = int(time.time())
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO ticket_messages (
                    ticket_id, sender_tg_id, sender_role, text, created_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (ticket_id, sender_tg_id, sender_role, text, now),
            )
            await db.execute(
                "UPDATE tickets SET updated_at = ? WHERE id = ?",
                (now, ticket_id),
            )
            await db.commit()

    async def close_ticket(self, ticket_id: int) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE tickets SET status = 'CLOSED', updated_at = ? WHERE id = ?",
                (int(time.time()), ticket_id),
            )
            await db.commit()

    async def set_session(
        self, tg_id: int, state: str, payload: dict[str, Any] | None = None
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO sessions (tg_id, state, payload, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(tg_id) DO UPDATE SET
                    state = excluded.state,
                    payload = excluded.payload,
                    updated_at = excluded.updated_at
                """,
                (tg_id, state, json.dumps(payload or {}), int(time.time())),
            )
            await db.commit()

    async def get_session(self, tg_id: int) -> tuple[str, dict[str, Any]] | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT state, payload FROM sessions WHERE tg_id = ?", (tg_id,)
            )
            row = await cursor.fetchone()
            if not row:
                return None
            return str(row["state"]), json.loads(row["payload"])

    async def clear_session(self, tg_id: int) -> None:
        async with self.connect() as db:
            await db.execute("DELETE FROM sessions WHERE tg_id = ?", (tg_id,))
            await db.commit()

    async def audit(
        self,
        action: str,
        *,
        actor_tg_id: int | None = None,
        entity_type: str | None = None,
        entity_id: str | int | None = None,
        details: str | None = None,
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO audit_log (
                    actor_tg_id, action, entity_type, entity_id, details, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    actor_tg_id,
                    action,
                    entity_type,
                    str(entity_id) if entity_id is not None else None,
                    details,
                    int(time.time()),
                ),
            )
            await db.commit()

    async def stats(self) -> dict[str, int]:
        now = int(time.time())
        async with self.connect() as db:
            values: dict[str, int] = {}
            for key, query, params in (
                ("users", "SELECT COUNT(*) FROM users", ()),
                (
                    "active",
                    """
                    SELECT COUNT(*) FROM users
                    WHERE vpn_status = 'ACTIVE' AND expire_at > ?
                    """,
                    (now,),
                ),
                (
                    "orders",
                    "SELECT COUNT(*) FROM orders WHERE status = 'REVIEW'",
                    (),
                ),
                (
                    "tickets",
                    "SELECT COUNT(*) FROM tickets WHERE status = 'OPEN'",
                    (),
                ),
            ):
                cursor = await db.execute(query, params)
                row = await cursor.fetchone()
                values[key] = int(row[0])
            return values

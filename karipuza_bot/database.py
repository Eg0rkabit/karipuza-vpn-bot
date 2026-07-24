from __future__ import annotations

import json
import hmac
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
                    payment_provider TEXT,
                    payment_id TEXT,
                    payment_url TEXT,
                    payment_status TEXT,
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

                CREATE TABLE IF NOT EXISTS mobile_auth_requests (
                    request_id TEXT PRIMARY KEY,
                    secret_hash TEXT NOT NULL,
                    device_id TEXT NOT NULL,
                    device_name TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT 'ANDROID',
                    status TEXT NOT NULL DEFAULT 'PENDING',
                    tg_id INTEGER REFERENCES users(tg_id),
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    approved_at INTEGER,
                    consumed_at INTEGER
                );

                CREATE INDEX IF NOT EXISTS idx_mobile_auth_expires
                ON mobile_auth_requests(expires_at);

                CREATE TABLE IF NOT EXISTS mobile_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                    token_hash TEXT NOT NULL UNIQUE,
                    device_id TEXT NOT NULL,
                    device_name TEXT NOT NULL DEFAULT '',
                    platform TEXT NOT NULL DEFAULT 'ANDROID',
                    expires_at INTEGER NOT NULL,
                    created_at INTEGER NOT NULL,
                    last_used_at INTEGER NOT NULL,
                    revoked_at INTEGER,
                    UNIQUE(tg_id, device_id)
                );

                CREATE INDEX IF NOT EXISTS idx_mobile_sessions_device
                ON mobile_sessions(device_id);
                """
            )
            await self._migrate_orders(db)
            await db.commit()

    async def _migrate_orders(self, db: aiosqlite.Connection) -> None:
        cursor = await db.execute("PRAGMA table_info(orders)")
        columns = {row[1] for row in await cursor.fetchall()}
        for name in (
            "payment_provider",
            "payment_id",
            "payment_url",
            "payment_status",
        ):
            if name not in columns:
                await db.execute(f"ALTER TABLE orders ADD COLUMN {name} TEXT")
        await db.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_orders_payment_id
            ON orders(payment_id)
            """
        )

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

    async def create_mobile_auth_request(
        self,
        *,
        request_id: str,
        secret_hash: str,
        device_id: str,
        device_name: str,
        platform: str,
        expires_at: int,
    ) -> None:
        now = int(time.time())
        async with self.connect() as db:
            await db.execute(
                """
                INSERT INTO mobile_auth_requests (
                    request_id, secret_hash, device_id, device_name, platform,
                    status, expires_at, created_at
                )
                VALUES (?, ?, ?, ?, ?, 'PENDING', ?, ?)
                """,
                (
                    request_id,
                    secret_hash,
                    device_id,
                    device_name,
                    platform,
                    expires_at,
                    now,
                ),
            )
            await db.execute(
                """
                DELETE FROM mobile_auth_requests
                WHERE expires_at < ? AND status IN ('PENDING', 'EXPIRED')
                """,
                (now - 86400,),
            )
            await db.commit()

    async def get_mobile_auth_request(self, request_id: str) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(
                "SELECT * FROM mobile_auth_requests WHERE request_id = ?",
                (request_id,),
            )
            return await cursor.fetchone()

    async def approve_mobile_auth_request(
        self,
        request_id: str,
        tg_id: int,
    ) -> str:
        now = int(time.time())
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT * FROM mobile_auth_requests WHERE request_id = ?",
                (request_id,),
            )
            request = await cursor.fetchone()
            if not request:
                await db.rollback()
                return "NOT_FOUND"
            if int(request["expires_at"]) <= now:
                await db.execute(
                    """
                    UPDATE mobile_auth_requests SET status = 'EXPIRED'
                    WHERE request_id = ? AND status != 'CONSUMED'
                    """,
                    (request_id,),
                )
                await db.commit()
                return "EXPIRED"
            if request["status"] in {"APPROVED", "CONSUMED"}:
                await db.rollback()
                if int(request["tg_id"] or 0) == tg_id:
                    return "ALREADY_APPROVED"
                return "CLAIMED"
            if request["status"] != "PENDING":
                await db.rollback()
                return str(request["status"])

            cursor = await db.execute(
                """
                UPDATE mobile_auth_requests SET
                    status = 'APPROVED',
                    tg_id = ?,
                    approved_at = ?
                WHERE request_id = ? AND status = 'PENDING'
                """,
                (tg_id, now, request_id),
            )
            await db.commit()
            return "APPROVED" if cursor.rowcount == 1 else "CLAIMED"

    async def consume_mobile_auth_request(
        self,
        *,
        request_id: str,
        secret_hash: str,
        token_hash: str,
        session_expires_at: int,
    ) -> tuple[str, int | None]:
        now = int(time.time())
        async with self.connect() as db:
            await db.execute("BEGIN IMMEDIATE")
            cursor = await db.execute(
                "SELECT * FROM mobile_auth_requests WHERE request_id = ?",
                (request_id,),
            )
            request = await cursor.fetchone()
            if not request:
                await db.rollback()
                return "NOT_FOUND", None
            if not hmac.compare_digest(str(request["secret_hash"]), secret_hash):
                await db.rollback()
                return "INVALID_SECRET", None
            if int(request["expires_at"]) <= now:
                if request["status"] != "CONSUMED":
                    await db.execute(
                        """
                        UPDATE mobile_auth_requests SET status = 'EXPIRED'
                        WHERE request_id = ?
                        """,
                        (request_id,),
                    )
                    await db.commit()
                else:
                    await db.rollback()
                return "EXPIRED", None
            if request["status"] == "PENDING":
                await db.rollback()
                return "PENDING", None
            if request["status"] not in {"APPROVED", "CONSUMED"}:
                await db.rollback()
                return str(request["status"]), None

            tg_id = int(request["tg_id"])
            await db.execute(
                """
                UPDATE mobile_sessions SET revoked_at = ?
                WHERE device_id = ? AND tg_id != ? AND revoked_at IS NULL
                """,
                (now, request["device_id"], tg_id),
            )
            await db.execute(
                """
                INSERT INTO mobile_sessions (
                    tg_id, token_hash, device_id, device_name, platform,
                    expires_at, created_at, last_used_at, revoked_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, NULL)
                ON CONFLICT(tg_id, device_id) DO UPDATE SET
                    token_hash = excluded.token_hash,
                    device_name = excluded.device_name,
                    platform = excluded.platform,
                    expires_at = excluded.expires_at,
                    last_used_at = excluded.last_used_at,
                    revoked_at = NULL
                """,
                (
                    tg_id,
                    token_hash,
                    request["device_id"],
                    request["device_name"],
                    request["platform"],
                    session_expires_at,
                    now,
                    now,
                ),
            )
            await db.execute(
                """
                UPDATE mobile_auth_requests SET
                    status = 'CONSUMED',
                    consumed_at = COALESCE(consumed_at, ?)
                WHERE request_id = ?
                """,
                (now, request_id),
            )
            await db.commit()
            return "AUTHORIZED", tg_id

    async def get_mobile_session(self, token_hash: str) -> aiosqlite.Row | None:
        now = int(time.time())
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT
                    mobile_sessions.*,
                    users.username,
                    users.first_name
                FROM mobile_sessions
                JOIN users ON users.tg_id = mobile_sessions.tg_id
                WHERE mobile_sessions.token_hash = ?
                  AND mobile_sessions.revoked_at IS NULL
                  AND mobile_sessions.expires_at > ?
                """,
                (token_hash, now),
            )
            return await cursor.fetchone()

    async def touch_mobile_session(self, session_id: int) -> None:
        await self._update_mobile_session_timestamp(session_id, int(time.time()))

    async def _update_mobile_session_timestamp(
        self, session_id: int, timestamp: int
    ) -> None:
        async with self.connect() as db:
            await db.execute(
                "UPDATE mobile_sessions SET last_used_at = ? WHERE id = ?",
                (timestamp, session_id),
            )
            await db.commit()

    async def revoke_mobile_session(self, token_hash: str) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE mobile_sessions SET revoked_at = ?
                WHERE token_hash = ? AND revoked_at IS NULL
                """,
                (int(time.time()), token_hash),
            )
            await db.commit()
            return cursor.rowcount == 1

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

    async def get_order_by_payment_id(self, payment_id: str) -> aiosqlite.Row | None:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT orders.*, users.username, users.first_name
                FROM orders
                JOIN users ON users.tg_id = orders.tg_id
                WHERE orders.payment_id = ?
                """,
                (payment_id,),
            )
            return await cursor.fetchone()

    async def attach_order_payment(
        self,
        order_id: int,
        *,
        provider: str,
        payment_id: str,
        payment_url: str | None,
        payment_status: str | None,
    ) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE orders SET
                    payment_provider = ?,
                    payment_id = ?,
                    payment_url = ?,
                    payment_status = ?,
                    updated_at = ?
                WHERE id = ?
                """,
                (
                    provider,
                    payment_id,
                    payment_url,
                    payment_status,
                    int(time.time()),
                    order_id,
                ),
            )
            await db.commit()
            return cursor.rowcount == 1

    async def set_order_payment_status(
        self,
        order_id: int,
        *,
        payment_status: str,
    ) -> bool:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                UPDATE orders SET payment_status = ?, updated_at = ?
                WHERE id = ?
                """,
                (payment_status, int(time.time()), order_id),
            )
            await db.commit()
            return cursor.rowcount == 1

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

    async def create_ticket(
        self,
        tg_id: int,
        text: str,
        *,
        subject: str = "Поддержка",
    ) -> int:
        now = int(time.time())
        async with self.connect() as db:
            cursor = await db.execute(
                """
                INSERT INTO tickets (
                    tg_id, status, subject, created_at, updated_at
                )
                VALUES (?, 'OPEN', ?, ?, ?)
                """,
                (tg_id, subject[:100], now, now),
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

    async def list_ticket_messages(
        self, ticket_id: int, limit: int = 20
    ) -> list[aiosqlite.Row]:
        async with self.connect() as db:
            cursor = await db.execute(
                """
                SELECT *
                FROM ticket_messages
                WHERE ticket_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (ticket_id, limit),
            )
            return await cursor.fetchall()

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

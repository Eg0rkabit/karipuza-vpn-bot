import sqlite3
import time
from pathlib import Path

DB_PATH = Path(__file__).with_name("bot.db")


def _connect():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            tg_id INTEGER PRIMARY KEY,
            tg_username TEXT,
            marzban_username TEXT,
            expire_at INTEGER,
            vpn_link TEXT,
            created_at INTEGER,
            updated_at INTEGER
        )
        """)
        cur.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tg_id INTEGER NOT NULL,
            tg_username TEXT,
            tariff_id TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)
        conn.commit()


def create_order(tg_id: int, tg_username: str | None, tariff_id: str) -> int:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (tg_id, tg_username, tariff_id, status, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (tg_id, tg_username, tariff_id, "pending", now, now),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_order(order_id: int):
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, tg_id, tg_username, tariff_id, status, created_at, updated_at FROM orders WHERE id = ?",
            (order_id,),
        )
        return cur.fetchone()


def update_order_status(order_id: int, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE orders SET status = ?, updated_at = ? WHERE id = ?", (status, int(time.time()), order_id))
        conn.commit()


def save_user(tg_id: int, tg_username: str | None, marzban_username: str, expire_at: int, vpn_link: str) -> None:
    now = int(time.time())
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT tg_id, created_at FROM users WHERE tg_id = ?", (tg_id,))
        row = cur.fetchone()
        created_at = row[1] if row else now
        cur.execute("""
        INSERT OR REPLACE INTO users
        (tg_id, tg_username, marzban_username, expire_at, vpn_link, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (tg_id, tg_username, marzban_username, expire_at, vpn_link, created_at, now))
        conn.commit()


def get_user(tg_id: int):
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT tg_id, tg_username, marzban_username, expire_at, vpn_link, created_at, updated_at FROM users WHERE tg_id = ?",
            (tg_id,),
        )
        return cur.fetchone()


def list_recent_users(limit: int = 20):
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT tg_id, tg_username, marzban_username, expire_at, updated_at FROM users ORDER BY updated_at DESC LIMIT ?",
            (limit,),
        )
        return cur.fetchall()

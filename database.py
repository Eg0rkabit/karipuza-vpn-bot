import sqlite3
import time
from pathlib import Path

DB_PATH = Path("bot.db")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = connect()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        tg_username TEXT,
        marzban_username TEXT,
        expire_at INTEGER DEFAULT 0,
        vpn_link TEXT,
        trial_used INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS purchases (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        tg_id INTEGER NOT NULL,
        tg_username TEXT,
        tariff_id TEXT NOT NULL,
        status TEXT NOT NULL,
        created_at INTEGER NOT NULL
    )
    """)

    conn.commit()
    conn.close()


def ensure_user(tg_id: int, tg_username: str | None = None) -> None:
    now = int(time.time())
    conn = connect()
    cur = conn.cursor()

    cur.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,))
    exists = cur.fetchone()

    if exists:
        cur.execute("""
            UPDATE users
            SET tg_username = COALESCE(?, tg_username), updated_at = ?
            WHERE tg_id = ?
        """, (tg_username, now, tg_id))
    else:
        cur.execute("""
            INSERT INTO users (
                tg_id, tg_username, marzban_username, expire_at, vpn_link,
                trial_used, created_at, updated_at
            )
            VALUES (?, ?, NULL, 0, NULL, 0, ?, ?)
        """, (tg_id, tg_username, now, now))

    conn.commit()
    conn.close()


def get_user(tg_id: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT tg_id, tg_username, marzban_username, expire_at, vpn_link,
               trial_used, created_at, updated_at
        FROM users
        WHERE tg_id = ?
    """, (tg_id,))
    row = cur.fetchone()
    conn.close()
    return row


def has_used_trial(tg_id: int) -> bool:
    user = get_user(tg_id)
    return bool(user and user[5])


def save_vpn_user(
    tg_id: int,
    tg_username: str | None,
    marzban_username: str,
    expire_at: int,
    vpn_link: str,
    mark_trial_used: bool = False,
) -> None:
    now = int(time.time())
    old = get_user(tg_id)

    if old:
        created_at = old[6] or now
        trial_used = bool(old[5]) or mark_trial_used
    else:
        created_at = now
        trial_used = mark_trial_used

    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT OR REPLACE INTO users (
            tg_id, tg_username, marzban_username, expire_at, vpn_link,
            trial_used, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        tg_id,
        tg_username,
        marzban_username,
        expire_at,
        vpn_link,
        1 if trial_used else 0,
        created_at,
        now,
    ))
    conn.commit()
    conn.close()


def create_purchase(tg_id: int, tg_username: str | None, tariff_id: str, status: str) -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO purchases (tg_id, tg_username, tariff_id, status, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (tg_id, tg_username, tariff_id, status, int(time.time())))
    purchase_id = int(cur.lastrowid)
    conn.commit()
    conn.close()
    return purchase_id


def list_recent_users(limit: int = 10):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT tg_id, tg_username, marzban_username, expire_at, trial_used
        FROM users
        WHERE vpn_link IS NOT NULL AND vpn_link != ''
        ORDER BY updated_at DESC
        LIMIT ?
    """, (limit,))
    rows = cur.fetchall()
    conn.close()
    return rows


def clear_user_key(tg_id: int) -> None:
    now = int(time.time())
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        UPDATE users
        SET vpn_link = NULL, expire_at = 0, updated_at = ?
        WHERE tg_id = ?
    """, (now, tg_id))
    conn.commit()
    conn.close()

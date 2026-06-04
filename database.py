import sqlite3
import time
from pathlib import Path

DB_PATH = Path("bot.db")


def get_conn():
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS users (
        tg_id INTEGER PRIMARY KEY,
        tg_username TEXT,
        marzban_username TEXT,
        expire_at INTEGER,
        vpn_link TEXT,
        trial_used INTEGER DEFAULT 0,
        created_at INTEGER,
        updated_at INTEGER
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


def get_user(tg_id: int):
    conn = get_conn()
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


def save_user(
    tg_id: int,
    tg_username: str | None,
    marzban_username: str,
    expire_at: int,
    vpn_link: str,
    trial_used: bool | None = None,
) -> None:
    old = get_user(tg_id)
    now = int(time.time())

    if old:
        old_trial_used = bool(old[5])
        final_trial_used = old_trial_used if trial_used is None else trial_used
        created_at = old[6] or now
    else:
        final_trial_used = False if trial_used is None else trial_used
        created_at = now

    conn = get_conn()
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
        1 if final_trial_used else 0,
        created_at,
        now,
    ))
    conn.commit()
    conn.close()


def mark_trial_used(tg_id: int) -> None:
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,))
    exists = cur.fetchone()

    now = int(time.time())
    if exists:
        cur.execute("""
            UPDATE users
            SET trial_used = 1, updated_at = ?
            WHERE tg_id = ?
        """, (now, tg_id))
    else:
        cur.execute("""
            INSERT INTO users (
                tg_id, tg_username, marzban_username, expire_at, vpn_link,
                trial_used, created_at, updated_at
            )
            VALUES (?, NULL, NULL, 0, NULL, 1, ?, ?)
        """, (tg_id, now, now))

    conn.commit()
    conn.close()


def has_used_trial(tg_id: int) -> bool:
    user = get_user(tg_id)
    return bool(user and user[5])


def create_purchase(tg_id: int, tg_username: str | None, tariff_id: str, status: str) -> int:
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO purchases (tg_id, tg_username, tariff_id, status, created_at)
        VALUES (?, ?, ?, ?, ?)
    """, (tg_id, tg_username, tariff_id, status, int(time.time())))
    purchase_id = cur.lastrowid
    conn.commit()
    conn.close()
    return purchase_id


def list_recent_users(limit: int = 10):
    conn = get_conn()
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

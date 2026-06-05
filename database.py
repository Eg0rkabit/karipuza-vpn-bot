import sqlite3
import time
from pathlib import Path

DB_PATH = Path("bot.db")


def connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def ensure_column(cur: sqlite3.Cursor, table: str, column: str, definition: str) -> None:
    cur.execute(f"PRAGMA table_info({table})")
    columns = {row[1] for row in cur.fetchall()}
    if column not in columns:
        cur.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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

    ensure_column(cur, "users", "tg_username", "TEXT")
    ensure_column(cur, "users", "marzban_username", "TEXT")
    ensure_column(cur, "users", "expire_at", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "vpn_link", "TEXT")
    ensure_column(cur, "users", "trial_used", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "created_at", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "updated_at", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "notice_3d_expire_at", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "notice_1d_expire_at", "INTEGER DEFAULT 0")
    ensure_column(cur, "users", "notice_0d_expire_at", "INTEGER DEFAULT 0")

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

    ensure_column(cur, "purchases", "tg_id", "INTEGER NOT NULL DEFAULT 0")
    ensure_column(cur, "purchases", "tg_username", "TEXT")
    ensure_column(cur, "purchases", "tariff_id", "TEXT NOT NULL DEFAULT ''")
    ensure_column(cur, "purchases", "status", "TEXT NOT NULL DEFAULT 'unknown'")
    ensure_column(cur, "purchases", "created_at", "INTEGER NOT NULL DEFAULT 0")

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

    if old:
        cur.execute("""
            UPDATE users
            SET tg_username = COALESCE(?, tg_username),
                marzban_username = ?,
                expire_at = ?,
                vpn_link = ?,
                trial_used = ?,
                updated_at = ?
            WHERE tg_id = ?
        """, (
            tg_username,
            marzban_username,
            expire_at,
            vpn_link,
            1 if trial_used else 0,
            now,
            tg_id,
        ))
    else:
        cur.execute("""
            INSERT INTO users (
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


def count_users() -> int:
    conn = connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    count = int(cur.fetchone()[0])
    conn.close()
    return count


def list_users(limit: int = 8, offset: int = 0):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT tg_id, tg_username, marzban_username, expire_at, vpn_link,
               trial_used, created_at, updated_at
        FROM users
        ORDER BY updated_at DESC, created_at DESC
        LIMIT ? OFFSET ?
    """, (limit, offset))
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


def list_users_for_expiry_notifications(now: int):
    conn = connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT tg_id, tg_username, expire_at, vpn_link,
               notice_3d_expire_at, notice_1d_expire_at, notice_0d_expire_at
        FROM users
        WHERE vpn_link IS NOT NULL
          AND vpn_link != ''
          AND expire_at > 0
          AND expire_at <= ?
    """, (now + 3 * 86400,))
    rows = cur.fetchall()
    conn.close()
    return rows


def mark_expiry_notice_sent(tg_id: int, notice_kind: str, expire_at: int) -> None:
    columns = {
        "3d": "notice_3d_expire_at",
        "1d": "notice_1d_expire_at",
        "0d": "notice_0d_expire_at",
    }
    column = columns.get(notice_kind)
    if not column:
        raise ValueError(f"Unknown expiry notice kind: {notice_kind}")

    conn = connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE users SET {column} = ? WHERE tg_id = ?", (expire_at, tg_id))
    conn.commit()
    conn.close()

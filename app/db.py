"""طبقة التخزين — SQLite بدون أي اعتماديات خارجية."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, Iterator

from .config import normalize_phone, settings

_LOCK = threading.RLock()
_CONN: sqlite3.Connection | None = None

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    phone           TEXT PRIMARY KEY,
    name            TEXT,
    risk_profile    TEXT    DEFAULT 'متوازن',
    alerts_enabled  INTEGER DEFAULT 1,
    brief_enabled   INTEGER DEFAULT 1,
    created_at      TEXT    NOT NULL,
    last_inbound_at TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    phone      TEXT NOT NULL,
    role       TEXT NOT NULL,
    content    TEXT NOT NULL,          -- JSON: قائمة بلوكات المحتوى
    is_anchor  INTEGER DEFAULT 0,      -- 1 إذا كانت رسالة مستخدم نصية (نقطة قطع آمنة)
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_messages_phone ON messages(phone, id);

CREATE TABLE IF NOT EXISTS watchlist (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    phone    TEXT NOT NULL,
    symbol   TEXT NOT NULL,
    label    TEXT,
    notes    TEXT,
    added_at TEXT NOT NULL,
    UNIQUE(phone, symbol)
);

CREATE TABLE IF NOT EXISTS alerts (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    phone   TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    kind    TEXT NOT NULL,
    score   REAL,
    payload TEXT,
    sent_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_alerts_lookup ON alerts(phone, symbol, sent_at);

CREATE TABLE IF NOT EXISTS price_alerts (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    phone      TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    direction  TEXT NOT NULL,          -- above | below
    price      REAL NOT NULL,
    note       TEXT,
    active     INTEGER DEFAULT 1,
    created_at TEXT NOT NULL,
    fired_at   TEXT
);

CREATE TABLE IF NOT EXISTS reminders (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    phone         TEXT NOT NULL,
    text          TEXT NOT NULL,
    due_at        TEXT,                -- ISO UTC لتذكير لمرة واحدة
    repeat_daily  TEXT,                -- HH:MM لتذكير يومي
    active        INTEGER DEFAULT 1,
    created_at    TEXT NOT NULL,
    last_fired_at TEXT
);

CREATE TABLE IF NOT EXISTS memory (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    phone      TEXT NOT NULL,
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE(phone, key)
);

CREATE TABLE IF NOT EXISTS kv (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat()


def parse_iso(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def get_conn() -> sqlite3.Connection:
    global _CONN
    with _LOCK:
        if _CONN is None:
            _CONN = sqlite3.connect(settings.db_file, check_same_thread=False)
            _CONN.row_factory = sqlite3.Row
            _CONN.execute("PRAGMA journal_mode=WAL")
            _CONN.executescript(SCHEMA)
            _CONN.commit()
        return _CONN


@contextmanager
def tx() -> Iterator[sqlite3.Connection]:
    conn = get_conn()
    with _LOCK:
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def init_db() -> None:
    get_conn()


# ----------------------------------------------------------------- المستخدمون


def ensure_user(phone: str, name: str | None = None) -> sqlite3.Row:
    phone = normalize_phone(phone)
    with tx() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO users (phone, name, created_at) VALUES (?, ?, ?)",
            (phone, name, iso(now_utc())),
        )
        if name:
            conn.execute(
                "UPDATE users SET name = COALESCE(NULLIF(?, ''), name) WHERE phone = ?",
                (name, phone),
            )
    return get_user(phone)


def get_user(phone: str) -> sqlite3.Row:
    row = get_conn().execute(
        "SELECT * FROM users WHERE phone = ?", (normalize_phone(phone),)
    ).fetchone()
    return row


def all_users(only_alerts: bool = False, only_brief: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM users"
    clauses = []
    if only_alerts:
        clauses.append("alerts_enabled = 1")
    if only_brief:
        clauses.append("brief_enabled = 1")
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    return list(get_conn().execute(sql).fetchall())


def touch_inbound(phone: str) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE users SET last_inbound_at = ? WHERE phone = ?",
            (iso(now_utc()), normalize_phone(phone)),
        )


def within_service_window(phone: str, hours: int = 24) -> bool:
    """نافذة واتساب: الرسائل الحرة مسموحة خلال 24 ساعة من آخر رسالة واردة."""
    user = get_user(phone)
    last = parse_iso(user["last_inbound_at"]) if user else None
    if last is None:
        return False
    return now_utc() - last < timedelta(hours=hours)


def set_flag(phone: str, column: str, value: bool) -> None:
    if column not in ("alerts_enabled", "brief_enabled"):
        raise ValueError(f"عمود غير مسموح: {column}")
    with tx() as conn:
        conn.execute(
            f"UPDATE users SET {column} = ? WHERE phone = ?",
            (1 if value else 0, normalize_phone(phone)),
        )


# --------------------------------------------------------------- سجل المحادثة


def save_message(phone: str, role: str, content: Any, is_anchor: bool = False) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO messages (phone, role, content, is_anchor, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                normalize_phone(phone),
                role,
                json.dumps(content, ensure_ascii=False, default=str),
                1 if is_anchor else 0,
                iso(now_utc()),
            ),
        )


def load_history(phone: str, max_messages: int = 40) -> list[dict]:
    """يعيد آخر رسائل المحادثة بدءاً من نقطة قطع آمنة.

    القطع عند رسالة عشوائية قد يفصل ``tool_result`` عن ``tool_use`` المقابل له
    فترفض الواجهة الطلب. لذلك نبدأ دائماً من رسالة مستخدم نصية (``is_anchor``):
    نأخذ أحدث مرساة تقع قبل نافذة القص — حتى لو كانت خارجها — بدل إسقاط السجل
    كله. وإن كبرت النافذة الناتجة أكثر من اللازم نكتفي بالمرساة التالية.
    """
    phone = normalize_phone(phone)
    conn = get_conn()

    window = conn.execute(
        "SELECT id FROM messages WHERE phone = ? ORDER BY id DESC LIMIT ?",
        (phone, max_messages),
    ).fetchall()
    if not window:
        return []
    window_start = window[-1]["id"]

    # أحدث مرساة تسبق النافذة (أو تقع في بدايتها)، وأقرب مرساة بعدها
    backward = conn.execute(
        "SELECT id FROM messages WHERE phone = ? AND is_anchor = 1 AND id <= ?"
        " ORDER BY id DESC LIMIT 1",
        (phone, window_start),
    ).fetchone()
    forward = conn.execute(
        "SELECT id FROM messages WHERE phone = ? AND is_anchor = 1 AND id > ?"
        " ORDER BY id ASC LIMIT 1",
        (phone, window_start),
    ).fetchone()

    anchor = backward or forward
    if backward and forward:
        span = conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE phone = ? AND id >= ?",
            (phone, backward["id"]),
        ).fetchone()["c"]
        # لو توسّعت النافذة كثيراً للخلف، اكتفِ بالمرساة التالية — لكن فقط
        # عندما توجد بالفعل مرساة لاحقة، وإلا فقدنا السجل كله.
        if span > max_messages * 2:
            anchor = forward

    if anchor is None:
        return []

    rows = conn.execute(
        "SELECT role, content FROM messages WHERE phone = ? AND id >= ? ORDER BY id ASC",
        (phone, anchor["id"]),
    ).fetchall()
    return [{"role": r["role"], "content": json.loads(r["content"])} for r in rows]


def clear_history(phone: str) -> int:
    with tx() as conn:
        cur = conn.execute("DELETE FROM messages WHERE phone = ?", (normalize_phone(phone),))
    return cur.rowcount


# ------------------------------------------------------------ قائمة المتابعة


def add_watch(phone: str, symbol: str, label: str | None = None, notes: str | None = None) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO watchlist (phone, symbol, label, notes, added_at)"
            " VALUES (?, ?, ?, ?, ?)"
            " ON CONFLICT(phone, symbol) DO UPDATE SET"
            "   label = COALESCE(excluded.label, label),"
            "   notes = COALESCE(excluded.notes, notes)",
            (normalize_phone(phone), symbol.upper(), label, notes, iso(now_utc())),
        )


def remove_watch(phone: str, symbol: str) -> int:
    with tx() as conn:
        cur = conn.execute(
            "DELETE FROM watchlist WHERE phone = ? AND symbol = ?",
            (normalize_phone(phone), symbol.upper()),
        )
    return cur.rowcount


def get_watchlist(phone: str) -> list[sqlite3.Row]:
    return list(
        get_conn().execute(
            "SELECT * FROM watchlist WHERE phone = ? ORDER BY added_at",
            (normalize_phone(phone),),
        )
    )


# ------------------------------------------------------------------ التنبيهات


def record_alert(phone: str, symbol: str, kind: str, score: float, payload: dict) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO alerts (phone, symbol, kind, score, payload, sent_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (
                normalize_phone(phone),
                symbol.upper(),
                kind,
                score,
                json.dumps(payload, ensure_ascii=False, default=str),
                iso(now_utc()),
            ),
        )


def alert_on_cooldown(phone: str, symbol: str, kind: str, hours: int) -> bool:
    cutoff = iso(now_utc() - timedelta(hours=hours))
    row = get_conn().execute(
        "SELECT 1 FROM alerts WHERE phone = ? AND symbol = ? AND kind = ? AND sent_at > ? LIMIT 1",
        (normalize_phone(phone), symbol.upper(), kind, cutoff),
    ).fetchone()
    return row is not None


def alerts_sent_today(phone: str) -> int:
    cutoff = iso(now_utc() - timedelta(hours=24))
    row = get_conn().execute(
        "SELECT COUNT(*) AS c FROM alerts WHERE phone = ? AND sent_at > ?",
        (normalize_phone(phone), cutoff),
    ).fetchone()
    return int(row["c"])


def add_price_alert(phone: str, symbol: str, direction: str, price: float, note: str | None) -> int:
    direction = direction.lower().strip()
    if direction not in ("above", "below"):
        raise ValueError("الاتجاه يجب أن يكون above أو below")
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO price_alerts (phone, symbol, direction, price, note, created_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (normalize_phone(phone), symbol.upper(), direction, float(price), note, iso(now_utc())),
        )
    return int(cur.lastrowid)


def active_price_alerts(phone: str | None = None) -> list[sqlite3.Row]:
    if phone:
        return list(
            get_conn().execute(
                "SELECT * FROM price_alerts WHERE active = 1 AND phone = ?",
                (normalize_phone(phone),),
            )
        )
    return list(get_conn().execute("SELECT * FROM price_alerts WHERE active = 1"))


def fire_price_alert(alert_id: int) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE price_alerts SET active = 0, fired_at = ? WHERE id = ?",
            (iso(now_utc()), alert_id),
        )


def cancel_price_alert(phone: str, alert_id: int) -> int:
    with tx() as conn:
        cur = conn.execute(
            "UPDATE price_alerts SET active = 0 WHERE id = ? AND phone = ?",
            (alert_id, normalize_phone(phone)),
        )
    return cur.rowcount


# ------------------------------------------------------------------ التذكيرات


def add_reminder(
    phone: str, text: str, due_at: datetime | None = None, repeat_daily: str | None = None
) -> int:
    with tx() as conn:
        cur = conn.execute(
            "INSERT INTO reminders (phone, text, due_at, repeat_daily, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (
                normalize_phone(phone),
                text,
                iso(due_at) if due_at else None,
                repeat_daily,
                iso(now_utc()),
            ),
        )
    return int(cur.lastrowid)


def due_reminders(now: datetime | None = None) -> list[sqlite3.Row]:
    now = now or now_utc()
    return list(
        get_conn().execute(
            "SELECT * FROM reminders WHERE active = 1 AND due_at IS NOT NULL AND due_at <= ?",
            (iso(now),),
        )
    )


def daily_reminders(hhmm: str) -> list[sqlite3.Row]:
    return list(
        get_conn().execute(
            "SELECT * FROM reminders WHERE active = 1 AND repeat_daily = ?", (hhmm,)
        )
    )


def list_reminders(phone: str) -> list[sqlite3.Row]:
    return list(
        get_conn().execute(
            "SELECT * FROM reminders WHERE phone = ? AND active = 1 ORDER BY id",
            (normalize_phone(phone),),
        )
    )


def complete_reminder(reminder_id: int, keep_active: bool = False) -> None:
    with tx() as conn:
        conn.execute(
            "UPDATE reminders SET last_fired_at = ?, active = ? WHERE id = ?",
            (iso(now_utc()), 1 if keep_active else 0, reminder_id),
        )


def cancel_reminder(phone: str, reminder_id: int) -> int:
    with tx() as conn:
        cur = conn.execute(
            "UPDATE reminders SET active = 0 WHERE id = ? AND phone = ?",
            (reminder_id, normalize_phone(phone)),
        )
    return cur.rowcount


# -------------------------------------------------------------- ذاكرة المستخدم


def remember(phone: str, key: str, value: str) -> None:
    with tx() as conn:
        conn.execute(
            "INSERT INTO memory (phone, key, value, updated_at) VALUES (?, ?, ?, ?)"
            " ON CONFLICT(phone, key) DO UPDATE SET value = excluded.value,"
            " updated_at = excluded.updated_at",
            (normalize_phone(phone), key, value, iso(now_utc())),
        )


def recall(phone: str) -> dict[str, str]:
    rows = get_conn().execute(
        "SELECT key, value FROM memory WHERE phone = ? ORDER BY updated_at DESC LIMIT 60",
        (normalize_phone(phone),),
    )
    return {r["key"]: r["value"] for r in rows}


def forget(phone: str, key: str) -> int:
    with tx() as conn:
        cur = conn.execute(
            "DELETE FROM memory WHERE phone = ? AND key = ?", (normalize_phone(phone), key)
        )
    return cur.rowcount

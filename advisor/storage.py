"""تخزين دائم بسيط على SQLite: المستخدمون، قوائم المتابعة، المحافظ، سجل المحادثة.

كل الدوال العامة غير متزامنة (async) وتشغّل SQLite في خيط منفصل حتى لا تُعطّل
حلقة الأحداث في البوت.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
import time
from dataclasses import dataclass
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id        INTEGER PRIMARY KEY,
    channel        TEXT    NOT NULL DEFAULT 'telegram',
    display_name   TEXT,
    risk_profile   TEXT    NOT NULL DEFAULT 'متوازن',
    capital_note   TEXT    NOT NULL DEFAULT '',
    horizon        TEXT    NOT NULL DEFAULT 'متوسط المدى',
    daily_brief    INTEGER NOT NULL DEFAULT 0,
    created_at     REAL    NOT NULL,
    updated_at     REAL    NOT NULL
);

CREATE TABLE IF NOT EXISTS watchlist (
    user_id  INTEGER NOT NULL,
    symbol   TEXT    NOT NULL,
    added_at REAL    NOT NULL,
    PRIMARY KEY (user_id, symbol)
);

CREATE TABLE IF NOT EXISTS holdings (
    user_id   INTEGER NOT NULL,
    symbol    TEXT    NOT NULL,
    quantity  REAL    NOT NULL,
    avg_price REAL,
    note      TEXT    NOT NULL DEFAULT '',
    PRIMARY KEY (user_id, symbol)
);

CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id   INTEGER NOT NULL,
    role      TEXT    NOT NULL,
    content   TEXT    NOT NULL,
    created_at REAL   NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_messages_user ON messages (user_id, id);
"""

RISK_PROFILES = ("محافظ", "متوازن", "مخاطرة عالية")
HORIZONS = ("قصير المدى", "متوسط المدى", "طويل المدى")


@dataclass
class UserProfile:
    user_id: int
    display_name: str
    risk_profile: str
    capital_note: str
    horizon: str
    daily_brief: bool

    def as_context(self) -> str:
        """وصف موجز للملف الشخصي يُمرَّر للنموذج."""
        lines = [
            f"- مستوى تحمّل المخاطر: {self.risk_profile}",
            f"- الأفق الزمني للاستثمار: {self.horizon}",
        ]
        if self.capital_note:
            lines.append(f"- ملاحظات عن رأس المال والوضع المالي: {self.capital_note}")
        return "\n".join(lines)


class Storage:
    def __init__(self, path: str) -> None:
        self._path = path
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        self._lock = asyncio.Lock()

    # ── مساعدات داخلية ────────────────────────────────────────
    def _execute(self, sql: str, params: tuple = ()) -> None:
        with self._conn:
            self._conn.execute(sql, params)

    def _query(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        return list(self._conn.execute(sql, params).fetchall())

    async def _run(self, fn, *args):
        async with self._lock:
            return await asyncio.to_thread(fn, *args)

    # ── المستخدمون ────────────────────────────────────────────
    async def ensure_user(self, user_id: int, display_name: str = "", channel: str = "telegram") -> UserProfile:
        def work() -> sqlite3.Row:
            now = time.time()
            with self._conn:
                self._conn.execute(
                    """INSERT INTO users (user_id, channel, display_name, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?)
                       ON CONFLICT(user_id) DO UPDATE SET
                           display_name = COALESCE(NULLIF(excluded.display_name, ''), users.display_name),
                           updated_at = excluded.updated_at""",
                    (user_id, channel, display_name, now, now),
                )
            return self._conn.execute("SELECT * FROM users WHERE user_id = ?", (user_id,)).fetchone()

        row = await self._run(work)
        return _row_to_profile(row)

    async def get_profile(self, user_id: int) -> UserProfile | None:
        rows = await self._run(self._query, "SELECT * FROM users WHERE user_id = ?", (user_id,))
        return _row_to_profile(rows[0]) if rows else None

    async def update_profile(self, user_id: int, **fields: Any) -> None:
        allowed = {"risk_profile", "capital_note", "horizon", "daily_brief", "display_name"}
        sets, params = [], []
        for key, value in fields.items():
            if key in allowed:
                sets.append(f"{key} = ?")
                params.append(int(value) if key == "daily_brief" else value)
        if not sets:
            return
        sets.append("updated_at = ?")
        params.extend([time.time(), user_id])
        await self._run(self._execute, f"UPDATE users SET {', '.join(sets)} WHERE user_id = ?", tuple(params))

    async def subscribers(self) -> list[UserProfile]:
        rows = await self._run(self._query, "SELECT * FROM users WHERE daily_brief = 1", ())
        return [_row_to_profile(r) for r in rows]

    # ── قائمة المتابعة ────────────────────────────────────────
    async def add_watch(self, user_id: int, symbol: str) -> None:
        await self._run(
            self._execute,
            "INSERT OR IGNORE INTO watchlist (user_id, symbol, added_at) VALUES (?, ?, ?)",
            (user_id, symbol.strip().upper(), time.time()),
        )

    async def remove_watch(self, user_id: int, symbol: str) -> None:
        await self._run(
            self._execute,
            "DELETE FROM watchlist WHERE user_id = ? AND symbol = ?",
            (user_id, symbol.strip().upper()),
        )

    async def get_watchlist(self, user_id: int) -> list[str]:
        rows = await self._run(
            self._query,
            "SELECT symbol FROM watchlist WHERE user_id = ? ORDER BY added_at",
            (user_id,),
        )
        return [r["symbol"] for r in rows]

    # ── المحفظة ───────────────────────────────────────────────
    async def upsert_holding(self, user_id: int, symbol: str, quantity: float,
                             avg_price: float | None = None, note: str = "") -> None:
        await self._run(
            self._execute,
            """INSERT INTO holdings (user_id, symbol, quantity, avg_price, note)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(user_id, symbol) DO UPDATE SET
                   quantity = excluded.quantity,
                   avg_price = COALESCE(excluded.avg_price, holdings.avg_price),
                   note = excluded.note""",
            (user_id, symbol.strip().upper(), quantity, avg_price, note),
        )

    async def remove_holding(self, user_id: int, symbol: str) -> None:
        await self._run(
            self._execute,
            "DELETE FROM holdings WHERE user_id = ? AND symbol = ?",
            (user_id, symbol.strip().upper()),
        )

    async def get_holdings(self, user_id: int) -> list[dict[str, Any]]:
        rows = await self._run(
            self._query,
            "SELECT symbol, quantity, avg_price, note FROM holdings WHERE user_id = ? ORDER BY symbol",
            (user_id,),
        )
        return [dict(r) for r in rows]

    # ── سجل المحادثة ──────────────────────────────────────────
    async def append_message(self, user_id: int, role: str, content: str) -> None:
        await self._run(
            self._execute,
            "INSERT INTO messages (user_id, role, content, created_at) VALUES (?, ?, ?, ?)",
            (user_id, role, content, time.time()),
        )

    async def recent_messages(self, user_id: int, limit: int) -> list[dict[str, str]]:
        rows = await self._run(
            self._query,
            "SELECT role, content FROM messages WHERE user_id = ? ORDER BY id DESC LIMIT ?",
            (user_id, limit),
        )
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]

    async def clear_messages(self, user_id: int) -> None:
        await self._run(self._execute, "DELETE FROM messages WHERE user_id = ?", (user_id,))

    async def close(self) -> None:
        await self._run(self._conn.close)


def _row_to_profile(row: sqlite3.Row) -> UserProfile:
    return UserProfile(
        user_id=row["user_id"],
        display_name=row["display_name"] or "",
        risk_profile=row["risk_profile"],
        capital_note=row["capital_note"],
        horizon=row["horizon"],
        daily_brief=bool(row["daily_brief"]),
    )


def dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)

"""تخزين المحادثات (SQLite) — الدردشات والرسائل والقرارات."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from .schemas import ChatMessage


class ChatStore:
    def __init__(self, db_path: Path) -> None:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id       TEXT PRIMARY KEY,
                chat_id  TEXT NOT NULL,
                author   TEXT NOT NULL,
                text     TEXT NOT NULL,
                ts       TEXT NOT NULL,
                kind     TEXT NOT NULL DEFAULT 'text',
                meta     TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_messages_chat ON messages(chat_id, ts);

            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                topic       TEXT NOT NULL,
                created_at  TEXT NOT NULL,
                payload     TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_decisions_time ON decisions(created_at DESC);
            """
        )
        self._conn.commit()

    # ------------------------------------------------------------ رسائل

    def add_message(self, message: ChatMessage) -> ChatMessage:
        self._conn.execute(
            "INSERT OR REPLACE INTO messages(id, chat_id, author, text, ts, kind, meta) "
            "VALUES(?,?,?,?,?,?,?)",
            (message.id, message.chat_id, message.author, message.text,
             message.ts, message.kind, json.dumps(message.meta, ensure_ascii=False)),
        )
        self._conn.commit()
        return message

    def history(self, chat_id: str, limit: int = 100) -> list[ChatMessage]:
        rows = self._conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY ts ASC, rowid ASC LIMIT ?",
            (chat_id, limit),
        ).fetchall()
        return [self._to_message(r) for r in rows]

    def last_message(self, chat_id: str) -> ChatMessage | None:
        row = self._conn.execute(
            "SELECT * FROM messages WHERE chat_id = ? ORDER BY ts DESC, rowid DESC LIMIT 1",
            (chat_id,),
        ).fetchone()
        return self._to_message(row) if row else None

    def clear_chat(self, chat_id: str) -> int:
        cursor = self._conn.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))
        self._conn.commit()
        return cursor.rowcount

    # ------------------------------------------------------------ قرارات

    def save_decision(self, decision_id: str, topic: str, created_at: str,
                      payload: dict[str, Any]) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO decisions(decision_id, topic, created_at, payload) "
            "VALUES(?,?,?,?)",
            (decision_id, topic, created_at, json.dumps(payload, ensure_ascii=False)),
        )
        self._conn.commit()

    def get_decision(self, decision_id: str) -> dict[str, Any] | None:
        row = self._conn.execute(
            "SELECT payload FROM decisions WHERE decision_id = ?", (decision_id,)
        ).fetchone()
        return json.loads(row["payload"]) if row else None

    def list_decisions(self, limit: int = 20) -> list[dict[str, Any]]:
        rows = self._conn.execute(
            "SELECT decision_id, topic, created_at FROM decisions "
            "ORDER BY created_at DESC LIMIT ?", (limit,),
        ).fetchall()
        return [dict(r) for r in rows]

    @staticmethod
    def _to_message(row: sqlite3.Row) -> ChatMessage:
        return ChatMessage(
            id=row["id"], chat_id=row["chat_id"], author=row["author"],
            text=row["text"], ts=row["ts"], kind=row["kind"],
            meta=json.loads(row["meta"]),
        )

"""الذاكرة طويلة الأمد للوكلاء (Retrieval Layer).

الهدف: ألّا يبدأ أي وكيل من الصفر في كل دورة، وأن يتمكن الوكيل التنسيقي
من سؤال "ماذا قلنا عن هذا الموضوع قبل أسبوع؟".

التنفيذ الافتراضي محلي بلا اعتماديات: SQLite + FTS5 (بحث نصي BM25).
واجهة `VectorStore` مجردة، و`QdrantStore` جاهز للإنتاج عند توفر الخدمة.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_TOKEN_RE = re.compile(r"[\w؀-ۿ]+", re.UNICODE)


@dataclass
class MemoryHit:
    doc_id: str
    agent_id: str
    topic: str
    text: str
    ts: str
    score: float
    meta: dict[str, Any]


class VectorStore(ABC):
    """واجهة التخزين الاسترجاعي. أي بديل إنتاجي ينفّذ هذه الدوال الثلاث."""

    @abstractmethod
    def upsert(self, doc_id: str, agent_id: str, topic: str, text: str, ts: str,
               meta: dict[str, Any] | None = None) -> None: ...

    @abstractmethod
    def search(self, query: str, k: int = 5, agent_id: str | None = None) -> list[MemoryHit]: ...

    @abstractmethod
    def recent(self, k: int = 10, agent_id: str | None = None) -> list[MemoryHit]: ...


def _tokenize(text: str) -> str:
    """تطبيع عربي خفيف + توكنة، لأن FTS5 الافتراضي لا يتعامل جيداً مع العربية."""
    text = text.replace("ـ", "")                       # حذف التطويل
    text = re.sub(r"[ً-ْ]", "", text)             # حذف التشكيل
    text = text.replace("أ", "ا").replace("إ", "ا").replace("آ", "ا")
    text = text.replace("ى", "ي").replace("ة", "ه")
    return " ".join(_TOKEN_RE.findall(text.lower()))


class SqliteBM25Store(VectorStore):
    """تخزين استرجاعي محلي عبر SQLite FTS5 (ترتيب BM25).

    يسقط تلقائياً إلى بحث LIKE إذا لم تكن FTS5 مبنية في نسخة SQLite.
    """

    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._fts = self._try_fts()
        self._init_schema()

    def _try_fts(self) -> bool:
        try:
            self._conn.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
            self._conn.execute("DROP TABLE IF EXISTS _fts_probe")
            return True
        except sqlite3.OperationalError:
            log.warning("FTS5 غير متاح - سيُستخدم بحث LIKE البديل")
            return False

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS memory (
                doc_id   TEXT PRIMARY KEY,
                agent_id TEXT NOT NULL,
                topic    TEXT NOT NULL,
                text     TEXT NOT NULL,
                ts       TEXT NOT NULL,
                meta     TEXT NOT NULL DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_memory_agent ON memory(agent_id);
            CREATE INDEX IF NOT EXISTS idx_memory_ts ON memory(ts DESC);
            """
        )
        if self._fts:
            self._conn.executescript(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts
                USING fts5(doc_id UNINDEXED, tokens);
                """
            )
        self._conn.commit()

    # ---------------------------------------------------------------- كتابة

    def upsert(self, doc_id: str, agent_id: str, topic: str, text: str, ts: str,
               meta: dict[str, Any] | None = None) -> None:
        self._conn.execute(
            "INSERT INTO memory(doc_id, agent_id, topic, text, ts, meta) "
            "VALUES(?,?,?,?,?,?) ON CONFLICT(doc_id) DO UPDATE SET "
            "text=excluded.text, topic=excluded.topic, ts=excluded.ts, meta=excluded.meta",
            (doc_id, agent_id, topic, text, ts, json.dumps(meta or {}, ensure_ascii=False)),
        )
        if self._fts:
            self._conn.execute("DELETE FROM memory_fts WHERE doc_id = ?", (doc_id,))
            self._conn.execute(
                "INSERT INTO memory_fts(doc_id, tokens) VALUES(?, ?)",
                (doc_id, _tokenize(f"{topic} {text}")),
            )
        self._conn.commit()

    # ---------------------------------------------------------------- قراءة

    def search(self, query: str, k: int = 5, agent_id: str | None = None) -> list[MemoryHit]:
        tokens = _tokenize(query)
        if not tokens:
            return self.recent(k, agent_id)

        if self._fts:
            match = " OR ".join(tokens.split()[:24])
            sql = (
                "SELECT m.*, bm25(memory_fts) AS rank FROM memory_fts "
                "JOIN memory m ON m.doc_id = memory_fts.doc_id "
                "WHERE memory_fts MATCH ?"
            )
            params: list[Any] = [match]
            if agent_id:
                sql += " AND m.agent_id = ?"
                params.append(agent_id)
            sql += " ORDER BY rank LIMIT ?"
            params.append(k)
            try:
                rows = self._conn.execute(sql, params).fetchall()
                return [self._row_to_hit(r, score=-float(r["rank"])) for r in rows]
            except sqlite3.OperationalError:
                log.warning("فشل استعلام FTS - التحويل إلى LIKE")

        # بديل: تطابق جزئي بسيط مرتّب بعدد الكلمات المشتركة
        rows = self._conn.execute(
            "SELECT * FROM memory" + (" WHERE agent_id = ?" if agent_id else "")
            + " ORDER BY ts DESC LIMIT 400",
            ([agent_id] if agent_id else []),
        ).fetchall()
        wanted = set(tokens.split())
        scored: list[tuple[float, sqlite3.Row]] = []
        for row in rows:
            have = set(_tokenize(f"{row['topic']} {row['text']}").split())
            overlap = len(wanted & have)
            if overlap:
                scored.append((overlap / max(len(wanted), 1), row))
        scored.sort(key=lambda p: p[0], reverse=True)
        return [self._row_to_hit(r, score=s) for s, r in scored[:k]]

    def recent(self, k: int = 10, agent_id: str | None = None) -> list[MemoryHit]:
        rows = self._conn.execute(
            "SELECT * FROM memory" + (" WHERE agent_id = ?" if agent_id else "")
            + " ORDER BY ts DESC LIMIT ?",
            ([agent_id, k] if agent_id else [k]),
        ).fetchall()
        return [self._row_to_hit(r, score=1.0) for r in rows]

    @staticmethod
    def _row_to_hit(row: sqlite3.Row, score: float) -> MemoryHit:
        return MemoryHit(
            doc_id=row["doc_id"],
            agent_id=row["agent_id"],
            topic=row["topic"],
            text=row["text"],
            ts=row["ts"],
            score=round(score, 4),
            meta=json.loads(row["meta"]),
        )


class QdrantStore(VectorStore):
    """محوّل Qdrant للإنتاج (بحث دلالي حقيقي عبر متجهات).

    يتطلب: `pip install qdrant-client` وخدمة Qdrant تعمل، بالإضافة إلى
    دالة تضمين (embedding) تمررها أنت - مثلاً Voyage أو نموذج محلي.
    يُرفع خطأ واضح إن لم تتوفر الاعتماديات بدل الفشل الصامت.
    """

    def __init__(self, url: str, collection: str, embed_fn, dim: int = 1024) -> None:
        try:
            from qdrant_client import QdrantClient                       # type: ignore
            from qdrant_client.models import Distance, VectorParams      # type: ignore
        except ImportError as exc:                                       # pragma: no cover
            raise RuntimeError(
                "QdrantStore يحتاج qdrant-client: pip install qdrant-client"
            ) from exc

        self._client = QdrantClient(url=url)
        self._collection = collection
        self._embed = embed_fn
        if not self._client.collection_exists(collection):
            self._client.create_collection(
                collection_name=collection,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )

    def upsert(self, doc_id: str, agent_id: str, topic: str, text: str, ts: str,
               meta: dict[str, Any] | None = None) -> None:  # pragma: no cover
        from qdrant_client.models import PointStruct                     # type: ignore

        self._client.upsert(
            collection_name=self._collection,
            points=[PointStruct(
                id=abs(hash(doc_id)) % (2**63),
                vector=self._embed(f"{topic}\n{text}"),
                payload={"doc_id": doc_id, "agent_id": agent_id, "topic": topic,
                         "text": text, "ts": ts, "meta": meta or {}},
            )],
        )

    def search(self, query: str, k: int = 5, agent_id: str | None = None) -> list[MemoryHit]:  # pragma: no cover
        from qdrant_client.models import FieldCondition, Filter, MatchValue   # type: ignore

        flt = Filter(must=[FieldCondition(key="agent_id", match=MatchValue(value=agent_id))]) \
            if agent_id else None
        res = self._client.search(
            collection_name=self._collection,
            query_vector=self._embed(query), limit=k, query_filter=flt,
        )
        return [
            MemoryHit(doc_id=p.payload["doc_id"], agent_id=p.payload["agent_id"],
                      topic=p.payload["topic"], text=p.payload["text"],
                      ts=p.payload["ts"], score=float(p.score), meta=p.payload.get("meta", {}))
            for p in res
        ]

    def recent(self, k: int = 10, agent_id: str | None = None) -> list[MemoryHit]:  # pragma: no cover
        raise NotImplementedError("استخدم search() مع Qdrant أو خزّن الأحدث في SQLite")

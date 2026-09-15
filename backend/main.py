"""تطبيق «مجلس القرار» — واجهة دردشة شبيهة بالواتساب فوق منظومة وكلاء.

نموذج الواجهة: كل وكيل جهة اتصال مستقلة، و«غرفة القرار» محادثة جماعية
تُشغّل دورة التنسيق الكاملة وتبثّ تقارير الوكلاء لحظة وصولها.
"""
from __future__ import annotations

import asyncio
import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .agents.base import AGENT_PROFILES
from .bus import bus
from .config import BASE_DIR, settings
from .formatting import decision_to_text, report_to_text
from .llm import llm
from .memory import SqliteBM25Store
from .orchestrator import SPECIALISTS, Orchestrator
from .schemas import AgentId, ChatMessage, CycleRequest, now_iso
from .store import ChatStore

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s | %(message)s"
)
log = logging.getLogger("majlis")

FRONTEND_DIR = BASE_DIR / "frontend"
WAR_ROOM = "war_room"

memory = SqliteBM25Store(settings.db_path)
store = ChatStore(settings.db_path)
orchestrator = Orchestrator(llm=llm, memory=memory, message_bus=bus)

_BACKGROUND: set[asyncio.Task] = set()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    yield
    for task in list(_BACKGROUND):
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="مجلس القرار — Multi-Agent Decision App",
    version="1.0.0",
    lifespan=lifespan,
)


# ------------------------------------------------------------ إدارة الاتصالات

class ConnectionHub:
    """يبثّ الأحداث لكل العملاء المتصلين عبر WebSocket."""

    def __init__(self) -> None:
        self._sockets: set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, socket: WebSocket) -> None:
        await socket.accept()
        async with self._lock:
            self._sockets.add(socket)

    async def disconnect(self, socket: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(socket)

    async def broadcast(self, event: dict[str, Any]) -> None:
        payload = json.dumps(event, ensure_ascii=False, default=str)
        async with self._lock:
            targets = list(self._sockets)
        for socket in targets:
            try:
                await socket.send_text(payload)
            except (WebSocketDisconnect, RuntimeError):
                await self.disconnect(socket)


hub = ConnectionHub()


async def push_message(message: ChatMessage) -> ChatMessage:
    store.add_message(message)
    await hub.broadcast({"event": "message", "data": message.model_dump(mode="json")})
    return message


async def push_status(agent_id: AgentId, state: str, meta: dict[str, Any]) -> None:
    await hub.broadcast({
        "event": "status",
        "data": {"agent": agent_id.value, "state": state, "meta": meta, "ts": now_iso()},
    })


# ------------------------------------------------------------ نماذج الطلبات

class ChatRequest(BaseModel):
    chat_id: str
    text: str


# ------------------------------------------------------------ نقاط REST

@app.get("/api/health")
async def health() -> dict[str, Any]:
    return {
        "ok": True,
        "llm_enabled": llm.enabled,
        "model": settings.specialist_model,
        "chief_model": settings.chief_model,
        "mode": "live" if llm.enabled else "offline-demo",
    }


@app.get("/api/chats")
async def list_chats() -> list[dict[str, Any]]:
    """قائمة الدردشات كما تظهر في الشريط الجانبي."""
    chats: list[dict[str, Any]] = [{
        "id": WAR_ROOM,
        "name": "غرفة القرار",
        "avatar": "قر",
        "color": "#075E54",
        "tagline": "المجلس كامل — دورة تحليل شاملة",
        "is_group": True,
        "members": [AGENT_PROFILES[a].display_name for a in SPECIALISTS]
                   + [AGENT_PROFILES[AgentId.CHIEF].display_name],
    }]
    for agent_id in (*SPECIALISTS, AgentId.CHIEF):
        profile = AGENT_PROFILES[agent_id]
        chats.append({
            "id": agent_id.value,
            "name": profile.display_name,
            "avatar": profile.avatar,
            "color": profile.color,
            "tagline": profile.tagline,
            "is_group": False,
        })

    for chat in chats:
        last = store.last_message(chat["id"])
        chat["last_message"] = last.text[:80] if last else ""
        chat["last_ts"] = last.ts if last else ""
    return chats


@app.get("/api/chats/{chat_id}/messages")
async def chat_history(chat_id: str, limit: int = 200) -> list[dict[str, Any]]:
    return [m.model_dump(mode="json") for m in store.history(chat_id, limit)]


@app.delete("/api/chats/{chat_id}/messages")
async def clear_history(chat_id: str) -> dict[str, int]:
    return {"deleted": store.clear_chat(chat_id)}


@app.post("/api/chat")
async def send_chat(request: ChatRequest) -> dict[str, Any]:
    """رسالة في دردشة مباشرة مع وكيل واحد."""
    text = request.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="نص فارغ")
    try:
        agent_id = AgentId(request.chat_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail="دردشة غير معروفة") from exc

    await push_message(ChatMessage(chat_id=request.chat_id, author="user", text=text))
    await push_status(agent_id, "typing", {})

    history = [
        {"role": "assistant" if m.author != "user" else "user", "content": m.text}
        for m in store.history(request.chat_id, 20)
    ]
    reply = await orchestrator.ask_agent(agent_id, history)

    message = await push_message(
        ChatMessage(chat_id=request.chat_id, author=agent_id.value, text=reply)
    )
    await push_status(agent_id, "idle", {})
    return message.model_dump(mode="json")


@app.post("/api/cycle")
async def run_cycle(request: CycleRequest) -> dict[str, Any]:
    """يشغّل دورة تحليل كاملة في الخلفية ويبثّ نتائجها عبر WebSocket."""
    topic = request.topic.strip()
    if not topic:
        raise HTTPException(status_code=400, detail="الموضوع مطلوب")

    await push_message(ChatMessage(chat_id=request.chat_id, author="user", text=topic))
    task = asyncio.create_task(_cycle_task(request, topic))
    _BACKGROUND.add(task)
    task.add_done_callback(_BACKGROUND.discard)
    return {"status": "started", "topic": topic}


async def _cycle_task(request: CycleRequest, topic: str) -> None:
    chat_id = request.chat_id
    await push_message(ChatMessage(
        chat_id=chat_id, author=AgentId.CHIEF.value, kind="system",
        text=f"بدأت دورة تحليل حول «{topic}» — تم توزيع المهمة على "
             f"{len(request.agents or SPECIALISTS)} وكلاء.",
    ))

    try:
        decision, reports = await orchestrator.run_cycle(
            topic, agents=request.agents, depth=request.depth, status=push_status,
        )
    except Exception as exc:                                         # noqa: BLE001
        log.exception("فشلت الدورة")
        await push_message(ChatMessage(
            chat_id=chat_id, author=AgentId.CHIEF.value, kind="system",
            text=f"توقفت الدورة بخطأ: {exc}",
        ))
        return

    for report in reports:
        await push_message(ChatMessage(
            chat_id=chat_id, author=report.agent_id.value, kind="report",
            text=report_to_text(report),
            meta={"confidence": report.confidence, "degraded": report.degraded,
                  "evidence": len(report.evidence), "urgency": report.urgency},
        ))

    store.save_decision(decision.decision_id, decision.topic, decision.created_at,
                        decision.model_dump(mode="json"))
    await push_message(ChatMessage(
        chat_id=chat_id, author=AgentId.CHIEF.value, kind="decision",
        text=decision_to_text(decision),
        meta={"decision_id": decision.decision_id, "confidence": decision.confidence,
              "risk": decision.risk_score, "stance": decision.stance.value},
    ))


@app.get("/api/decisions")
async def list_decisions(limit: int = 20) -> list[dict[str, Any]]:
    return store.list_decisions(limit)


@app.get("/api/decisions/{decision_id}")
async def get_decision(decision_id: str) -> JSONResponse:
    payload = store.get_decision(decision_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="قرار غير موجود")
    return JSONResponse(payload)


@app.get("/api/trace/{correlation_id}")
async def audit_trace(correlation_id: str) -> list[dict[str, Any]]:
    """سجل التدقيق: كل الرسائل التي أنتجت قراراً بعينه."""
    return [e.model_dump(mode="json") for e in bus.audit_trail(correlation_id)]


@app.get("/api/memory")
async def search_memory(q: str, k: int = 8, agent: str | None = None) -> list[dict[str, Any]]:
    hits = memory.search(q, k=k, agent_id=agent)
    return [hit.__dict__ for hit in hits]


# ------------------------------------------------------------ WebSocket

@app.websocket("/ws")
async def websocket_endpoint(socket: WebSocket) -> None:
    await hub.connect(socket)
    await socket.send_text(json.dumps({
        "event": "ready",
        "data": {"llm_enabled": llm.enabled,
                 "mode": "live" if llm.enabled else "offline-demo"},
    }, ensure_ascii=False))
    try:
        while True:
            # نبقي الاتصال حياً؛ الإرسال من العميل يتم عبر REST.
            await socket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        await hub.disconnect(socket)


# ------------------------------------------------------------ الواجهة الثابتة

if FRONTEND_DIR.exists():
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(FRONTEND_DIR / "index.html")

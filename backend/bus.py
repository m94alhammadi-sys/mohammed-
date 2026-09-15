"""ناقل رسائل الوكلاء (Agent-to-Agent Message Bus).

تنفيذ داخل العملية باستخدام asyncio، بواجهة مصمّمة لتُستبدل لاحقاً بـ
NATS أو Redis Streams أو Kafka دون تغيير كود الوكلاء: الوكيل يعرف
`publish` و`subscribe` فقط.

قواعد التوجيه:
  * رسالة بلا `recipients` = بث عام (broadcast) لكل المشتركين.
  * رسالة بـ `recipients` = تُسلَّم لهؤلاء فقط.
  * كل رسالة تُسجَّل في سجل تدقيق غير قابل للتعديل (audit log) لتتبع
    مسار أي قرار رجوعاً إلى مصادره.
"""
from __future__ import annotations

import asyncio
import logging
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Awaitable, Callable
from typing import Deque

from .schemas import AgentId, Envelope, MessageType

log = logging.getLogger(__name__)

Handler = Callable[[Envelope], Awaitable[None]]


class MessageBus:
    def __init__(self, audit_limit: int = 5000) -> None:
        self._queues: dict[AgentId, asyncio.Queue[Envelope]] = {}
        self._handlers: dict[AgentId, list[Handler]] = defaultdict(list)
        self._observers: list[Handler] = []           # مراقبون لكل الحركة (واجهة/تسجيل)
        self._audit: Deque[Envelope] = deque(maxlen=audit_limit)
        self._lock = asyncio.Lock()

    # ------------------------------------------------------------ اشتراك

    def register(self, agent_id: AgentId) -> asyncio.Queue[Envelope]:
        """يسجّل وكيلاً ويعيد طابور الوارد الخاص به."""
        if agent_id not in self._queues:
            self._queues[agent_id] = asyncio.Queue()
        return self._queues[agent_id]

    def subscribe(self, agent_id: AgentId, handler: Handler) -> None:
        """يربط معالجاً بوارد وكيل بعينه."""
        self.register(agent_id)
        self._handlers[agent_id].append(handler)

    def observe(self, handler: Handler) -> Callable[[], None]:
        """يراقب كل حركة الناقل. يعيد دالة لإلغاء المراقبة."""
        self._observers.append(handler)

        def _cancel() -> None:
            if handler in self._observers:
                self._observers.remove(handler)

        return _cancel

    # ------------------------------------------------------------ نشر

    async def publish(self, env: Envelope) -> None:
        async with self._lock:
            self._audit.append(env)

        targets = env.recipients or [a for a in self._queues if a != env.sender]
        for target in targets:
            queue = self.register(target)
            await queue.put(env)
            for handler in list(self._handlers.get(target, [])):
                asyncio.create_task(self._safe(handler, env))

        for observer in list(self._observers):
            asyncio.create_task(self._safe(observer, env))

    @staticmethod
    async def _safe(handler: Handler, env: Envelope) -> None:
        try:
            await handler(env)
        except Exception:                                   # noqa: BLE001
            log.exception("فشل معالج رسالة %s", env.message_id)

    # ------------------------------------------------------------ استقبال

    async def receive(self, agent_id: AgentId) -> Envelope:
        return await self.register(agent_id).get()

    async def stream(self, agent_id: AgentId) -> AsyncIterator[Envelope]:
        queue = self.register(agent_id)
        while True:
            yield await queue.get()

    async def collect(
        self,
        agent_id: AgentId,
        correlation_id: str,
        expected: int,
        timeout: float,
        types: tuple[MessageType, ...] = (MessageType.REPORT,),
    ) -> list[Envelope]:
        """يجمع `expected` رسالة تخص دورة واحدة، أو ما وصل عند انتهاء المهلة.

        هذه هي نقطة الالتقاء (fan-in) التي ينتظر عندها الوكيل التنسيقي
        تقارير المتخصصين.
        """
        queue = self.register(agent_id)
        collected: list[Envelope] = []
        deadline = asyncio.get_running_loop().time() + timeout

        while len(collected) < expected:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                break
            try:
                env = await asyncio.wait_for(queue.get(), timeout=remaining)
            except asyncio.TimeoutError:
                break
            if env.correlation_id == correlation_id and env.type in types:
                collected.append(env)
        return collected

    # ------------------------------------------------------------ تدقيق

    def audit_trail(self, correlation_id: str | None = None) -> list[Envelope]:
        items = list(self._audit)
        if correlation_id:
            items = [e for e in items if e.correlation_id == correlation_id]
        return items


bus = MessageBus()

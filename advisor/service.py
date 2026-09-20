"""طبقة الخدمة: تجمع ملف المستخدم وبيانات السوق الحية والنموذج في رد واحد.

قنوات المحادثة (تيليجرام، واتساب) تستدعي هذه الطبقة فقط — لا تعرف شيئاً عن
Claude أو مصادر الأسعار.
"""

from __future__ import annotations

import logging

from . import market_data, prompts
from .brain import AdvisorBrain, AdvisorReply
from .config import settings
from .storage import Storage, UserProfile

log = logging.getLogger(__name__)


class AdvisorService:
    def __init__(self, storage: Storage, brain: AdvisorBrain) -> None:
        self.storage = storage
        self.brain = brain

    # ── بناء السياق ───────────────────────────────────────────
    async def _market_block(self, include_uae: bool = True) -> str:
        try:
            snapshot = await market_data.fetch_snapshot(include_uae=include_uae)
            return snapshot.to_prompt()
        except Exception as exc:  # الأسعار إضافة، لا شرط — نكمل بدونها
            log.warning("تعذّر جلب لقطة السوق: %s", exc)
            return (
                "تعذّر الوصول إلى مصادر الأسعار المباشرة الآن. "
                "اعتمد على البحث في الإنترنت للحصول على الأرقام، واذكر أنها من البحث."
            )

    async def _context_turn(self, profile: UserProfile, question: str,
                            with_market: bool = True, with_holdings: bool = True) -> str:
        watchlist = await self.storage.get_watchlist(profile.user_id)
        holdings = await self.storage.get_holdings(profile.user_id) if with_holdings else []
        market_block = await self._market_block() if with_market else ""
        return prompts.build_user_turn(
            question,
            timezone=settings.timezone,
            profile_context=profile.as_context(),
            market_block=market_block,
            watchlist=watchlist,
            holdings=holdings,
        )

    # ── الواجهات العامة ───────────────────────────────────────
    async def chat(self, profile: UserProfile, question: str) -> AdvisorReply:
        """سؤال حر من المستخدم، مع ذاكرة محادثة قصيرة."""
        history = await self.storage.recent_messages(profile.user_id, settings.history_turns)
        turn = await self._context_turn(profile, question)
        reply = await self.brain.ask(turn, history)
        await self.storage.append_message(profile.user_id, "user", question)
        await self.storage.append_message(profile.user_id, "assistant", reply.text)
        return reply

    async def daily_brief(self, profile: UserProfile) -> AdvisorReply:
        turn = await self._context_turn(profile, prompts.DAILY_BRIEF_REQUEST)
        return await self.brain.ask(turn)

    async def news_digest(self, profile: UserProfile) -> AdvisorReply:
        turn = await self._context_turn(profile, prompts.NEWS_REQUEST, with_market=False)
        return await self.brain.ask(turn)

    async def portfolio_review(self, profile: UserProfile) -> AdvisorReply:
        holdings = await self.storage.get_holdings(profile.user_id)
        if not holdings:
            return AdvisorReply(
                text="محفظتك فاضية. أضف مراكزك أولاً بالأمر:\n/add رمز الكمية سعر_الشراء\n"
                     "مثال: /add BTC 0.5 61000"
            )
        turn = await self._context_turn(profile, prompts.portfolio_review_request())
        return await self.brain.ask(turn)

    async def analyze_symbol(self, profile: UserProfile, symbol: str) -> AdvisorReply:
        quotes, missing = await market_data.fetch_symbols([symbol])
        if quotes:
            price_block = "سعر محدّث من مصدر مباشر:\n" + "\n".join(q.line() for q in quotes)
        else:
            price_block = (
                f"لم يتوفر سعر مباشر للرمز {symbol} من مصادري. ابحث في الإنترنت عن السعر الحالي "
                "واذكر مصدره وتاريخه."
            )
        question = (
            f"حلّل لي {symbol} تحليلاً كاملاً: الوضع الحالي، آخر الأخبار المؤثرة عليه "
            "(ابحث في الإنترنت)، العوامل الداعمة والضاغطة، ثم توصية واضحة تناسب ملفي "
            "مع مستوى دخول وإدارة مخاطر."
        )
        turn = prompts.build_user_turn(
            question,
            timezone=settings.timezone,
            profile_context=profile.as_context(),
            market_block=price_block,
        )
        return await self.brain.ask(turn)

    async def market_snapshot_text(self) -> str:
        """أسعار خام بدون استدعاء النموذج — سريع ومجاني."""
        snapshot = await market_data.fetch_snapshot()
        if snapshot.is_empty():
            return "تعذّر الوصول إلى مصادر الأسعار المباشرة الآن. جرّب /brief ليبحث المستشار في الإنترنت."
        lines = [f"📊 لقطة الأسواق — {snapshot.taken_at}"]
        for group, quotes in snapshot.groups.items():
            if not quotes:
                continue
            lines.append(f"\n<b>{group}</b>")
            for q in quotes:
                arrow = "▫️" if q.change_pct is None else ("🟢" if q.change_pct >= 0 else "🔴")
                lines.append(f"{arrow} {q.line()}")
        if snapshot.errors:
            lines.append("\n⚠️ " + " | ".join(snapshot.errors))
        return "\n".join(lines)

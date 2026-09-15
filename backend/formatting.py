"""تحويل التقارير والقرارات إلى نص دردشة عربي مقروء داخل الفقاعات."""
from __future__ import annotations

from .agents.base import AGENT_PROFILES
from .schemas import AgentReport, ChiefDecision, Direction

_STANCE_AR = {
    Direction.BULLISH: "صاعد / إيجابي",
    Direction.BEARISH: "هابط / سلبي",
    Direction.NEUTRAL: "محايد",
}
_RISK_AR = {"low": "منخفضة", "medium": "متوسطة", "high": "مرتفعة"}


def _bar(value: float, width: int = 10) -> str:
    filled = max(0, min(width, round(value * width)))
    return "●" * filled + "○" * (width - filled)


def report_to_text(report: AgentReport) -> str:
    profile = AGENT_PROFILES[report.agent_id]
    lines = [f"*{profile.display_name}* — {report.headline}", "", report.summary]

    if report.signals:
        lines += ["", "*الإشارات المرصودة*"]
        for signal in report.signals:
            assets = "، ".join(signal.asset_classes) or "عام"
            lines.append(
                f"• {signal.name} — {_STANCE_AR[signal.direction]} "
                f"(قوة {signal.strength:.0%}، أفق {signal.horizon.value}، {assets})"
            )
            if signal.rationale:
                lines.append(f"   ↳ {signal.rationale}")

    if report.risks:
        lines += ["", "*المخاطر*"] + [f"• {r}" for r in report.risks]

    if report.unverified_claims:
        lines += ["", "*غير مؤكد*"] + [f"• {c}" for c in report.unverified_claims]

    if report.data_gaps:
        lines += ["", "*فجوات البيانات*"] + [f"• {g}" for g in report.data_gaps[:6]]

    lines += ["", f"الثقة: {_bar(report.confidence)} {report.confidence:.0%}"]
    if report.urgency:
        lines.append(f"الإلحاح: {_bar(report.urgency)} {report.urgency:.0%}")
    lines.append(f"الأدلة: {len(report.evidence)} مصدراً"
                 + ("  ⚠ وضع منقطع" if report.degraded else ""))
    return "\n".join(lines)


def decision_to_text(decision: ChiefDecision) -> str:
    lines = [
        "*التقرير التنفيذي*",
        f"الموضوع: {decision.topic}",
        "",
        "*١. خلاصة الموقف*",
        decision.situation,
    ]

    if decision.linkages:
        lines += ["", "*٢. ربط التأثيرات*"]
        for link in decision.linkages:
            who = "، ".join(a.value for a in link.agents_involved) or "—"
            lines.append(f"• {link.cause} ⇐ يؤثر في ⇒ {link.effect}")
            lines.append(f"   ↳ القناة: {link.channel or '—'} | يسنده: {who} "
                         f"| قوة الرابط {link.strength:.0%}")

    if decision.conflicts:
        lines += ["", "*٣. التضارب بين الوكلاء*"]
        for conflict in decision.conflicts:
            lines.append(
                f"• [{conflict.severity:.0%}] {conflict.topic}: "
                f"{conflict.agent_a.value} «{conflict.claim_a}» ⟷ "
                f"{conflict.agent_b.value} «{conflict.claim_b}»"
            )
            lines.append(f"   ↳ الحسم: {conflict.resolution}")

    lines += [
        "",
        "*٤. القرار / التوصية*",
        decision.recommendation,
        "",
        f"الاتجاه: {_STANCE_AR[decision.stance]}",
        f"الثقة: {_bar(decision.confidence)} {decision.confidence:.0%}",
        f"المخاطرة: {_bar(decision.risk_score)} {decision.risk_score:.0%}",
    ]

    if decision.options:
        lines += ["", "*٥. خيارات التنفيذ*"]
        for index, option in enumerate(decision.options, 1):
            lines.append(f"{index}) *{option.label}* — مخاطرة {_RISK_AR[option.risk_level]}")
            lines.append(f"   الإجراء: {option.action}")
            lines.append(f"   المبرر: {option.rationale}")
            if option.expected_impact:
                lines.append(f"   الأثر المتوقع: {option.expected_impact}")
            if option.invalidation:
                lines.append(f"   يبطل إذا: {option.invalidation}")

    if decision.invalidation_triggers:
        lines += ["", "*٦. شروط إبطال التوصية*"] + [
            f"• {t}" for t in decision.invalidation_triggers
        ]

    if decision.watchlist:
        lines += ["", "*٧. قائمة المراقبة*"] + [f"• {w}" for w in decision.watchlist]

    if decision.quality_flags:
        lines += ["", "*أعلام الجودة*"] + [f"• {f}" for f in decision.quality_flags]

    if decision.sources_used:
        lines += ["", f"*المصادر ({len(decision.sources_used)})*"]
        for source in decision.sources_used[:8]:
            lines.append(f"• [{source.reliability:.0%}] {source.title}"
                         + (f" — {source.url}" if source.url else ""))

    return "\n".join(lines)

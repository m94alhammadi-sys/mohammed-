"""منطق المطابقة التبادلية وحساب الثقة — دوال صرفة بلا نموذج لغوي.

لماذا خارج النموذج؟ لأن حساب الثقة وكشف التضارب يجب أن يكونا حتميّين
وقابلين للتدقيق والاختبار. النموذج يكتب التحليل؛ الأرقام التي يُبنى
عليها القرار تُحسب هنا بقواعد معلنة يمكن مراجعتها سطراً سطراً.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from .schemas import AgentId, AgentReport, Conflict, Direction, Evidence

# أوزان الوكلاء في التصويت على الاتجاه.
# التدفق الفعلي والبيانات الرسمية تُرجَّح فوق المشاعر عمداً: الضجيج
# الاجتماعي هو أكثر مصادر الإشارات الكاذبة في القرارات المالية.
AGENT_WEIGHTS: dict[AgentId, float] = {
    AgentId.FLOW: 1.00,
    AgentId.MACRO: 0.95,
    AgentId.GEO: 0.80,
    AgentId.BREAKING: 0.75,
    AgentId.SOCIAL: 0.45,
}

# ثقة قصوى مسموح بها عندما يعمل أي وكيل بلا مصادر حية.
DEGRADED_CONFIDENCE_CAP = 0.60
CONFIDENCE_FLOOR = 0.05
CONFIDENCE_CEIL = 0.95


@dataclass
class StanceResult:
    direction: Direction
    score: float          # -1 (هبوطي تام) .. +1 (صعودي تام)
    agreement: float      # 0..1 نسبة الوزن المتفق مع الاتجاه الغالب
    voters: dict[str, float]


# ------------------------------------------------------------------ الأدلة

def dedupe_evidence(reports: list[AgentReport]) -> list[Evidence]:
    """يوحّد الأدلة عبر التقارير ويرتّبها بالموثوقية.

    الدليل المكرر عبر عدة وكلاء لا يُحسب مرتين في العدّ، لكن تكراره
    يُستخدم كإشارة تأكيد في `corroboration_index`.
    """
    seen: dict[str, Evidence] = {}
    for report in reports:
        for item in report.evidence:
            key = item.key()
            if key not in seen or item.reliability > seen[key].reliability:
                seen[key] = item
    return sorted(seen.values(), key=lambda e: e.reliability, reverse=True)


def corroboration_index(reports: list[AgentReport]) -> float:
    """نسبة الأدلة التي ورد كلٌّ منها لدى أكثر من وكيل (0..1)."""
    owners: dict[str, set[str]] = defaultdict(set)
    for report in reports:
        for item in report.evidence:
            owners[item.key()].add(report.agent_id.value)
    if not owners:
        return 0.0
    shared = sum(1 for agents in owners.values() if len(agents) > 1)
    return round(shared / len(owners), 4)


# ------------------------------------------------------------- الاتجاه

def _signed(direction: Direction) -> int:
    return {Direction.BULLISH: 1, Direction.BEARISH: -1, Direction.NEUTRAL: 0}[direction]


def consensus_stance(reports: list[AgentReport]) -> StanceResult:
    """تصويت مرجّح على الاتجاه العام.

    وزن الإشارة = وزن الوكيل × ثقة الوكيل × قوة الإشارة.
    """
    voters: dict[str, float] = {}
    total_weight = 0.0
    net = 0.0

    for report in reports:
        agent_weight = AGENT_WEIGHTS.get(report.agent_id, 0.5)
        agent_net = 0.0
        agent_mass = 0.0
        for signal in report.signals:
            weight = agent_weight * report.confidence * signal.strength
            agent_net += _signed(signal.direction) * weight
            agent_mass += weight
        voters[report.agent_id.value] = round(agent_net, 4)
        net += agent_net
        total_weight += agent_mass

    if total_weight <= 0:
        return StanceResult(Direction.NEUTRAL, 0.0, 0.0, voters)

    score = max(-1.0, min(1.0, net / total_weight))
    if score >= 0.20:
        direction = Direction.BULLISH
    elif score <= -0.20:
        direction = Direction.BEARISH
    else:
        direction = Direction.NEUTRAL

    aligned = sum(
        abs(v) for v in voters.values()
        if (v > 0 and direction == Direction.BULLISH)
        or (v < 0 and direction == Direction.BEARISH)
    )
    spread = sum(abs(v) for v in voters.values()) or 1.0
    agreement = round(aligned / spread, 4) if direction != Direction.NEUTRAL else 0.0

    return StanceResult(direction, round(score, 4), agreement, voters)


# ------------------------------------------------------------- التضارب

def detect_conflicts(reports: list[AgentReport], min_strength: float = 0.4) -> list[Conflict]:
    """يكشف التضارب البنيوي: إشارتان متعاكستان على نفس فئة الأصول.

    الشدة = متوسط قوة الإشارتين مرجّحاً بثقة الوكيلين، لأن تضارب
    تقريرين واثقين أخطر من تضارب تخمينين.
    """
    buckets: dict[str, list[tuple[AgentReport, object]]] = defaultdict(list)
    for report in reports:
        for signal in report.signals:
            if signal.strength < min_strength or signal.direction == Direction.NEUTRAL:
                continue
            for asset in (signal.asset_classes or ["عام"]):
                buckets[asset.strip().lower()].append((report, signal))

    conflicts: list[Conflict] = []
    for asset, entries in buckets.items():
        for i in range(len(entries)):
            report_a, signal_a = entries[i]
            for j in range(i + 1, len(entries)):
                report_b, signal_b = entries[j]
                if report_a.agent_id == report_b.agent_id:
                    continue
                if signal_a.direction == signal_b.direction:
                    continue
                severity = round(
                    (signal_a.strength * report_a.confidence
                     + signal_b.strength * report_b.confidence) / 2, 4
                )
                conflicts.append(Conflict(
                    topic=asset,
                    agent_a=report_a.agent_id,
                    agent_b=report_b.agent_id,
                    claim_a=f"{signal_a.name}: {signal_a.direction.value} ({signal_a.strength:.2f})",
                    claim_b=f"{signal_b.name}: {signal_b.direction.value} ({signal_b.strength:.2f})",
                    severity=severity,
                ))
    conflicts.sort(key=lambda c: c.severity, reverse=True)
    return conflicts


# --------------------------------------------------------------- الثقة

def aggregate_confidence(
    reports: list[AgentReport],
    conflicts: list[Conflict],
    *,
    stance: StanceResult | None = None,
) -> tuple[float, list[str]]:
    """الثقة النهائية + أسباب معلنة لكل تعديل أُجري عليها.

    القاعدة: نبدأ من أضعف حلقة (أدنى ثقة وكيل)، ثم نعدّل صعوداً بالتأكيد
    المستقل ونزولاً بالتضارب والفجوات. لا نأخذ المتوسط أبداً: المتوسط
    يخفي الوكيل الأعمى خلف الوكلاء المبصرين.
    """
    if not reports:
        return CONFIDENCE_FLOOR, ["لا تقارير واردة"]

    reasons: list[str] = []
    weakest = min(r.confidence for r in reports)
    value = weakest
    reasons.append(f"البداية من أضعف حلقة: {weakest:.2f}")

    stance = stance or consensus_stance(reports)
    if stance.direction != Direction.NEUTRAL and stance.agreement >= 0.7:
        contributing = sum(1 for v in stance.voters.values() if abs(v) > 0.01)
        bonus = min(0.10 * max(contributing - 1, 0), 0.20)
        if bonus:
            value += bonus
            reasons.append(f"تأكيد مستقل من {contributing} وكلاء: +{bonus:.2f}")

    corroboration = corroboration_index(reports)
    if corroboration > 0.2:
        bonus = round(min(corroboration * 0.15, 0.10), 4)
        value += bonus
        reasons.append(f"تقاطع مصادر بنسبة {corroboration:.0%}: +{bonus:.2f}")

    if conflicts:
        penalty = round(min(sum(c.severity for c in conflicts) * 0.08, 0.25), 4)
        value -= penalty
        reasons.append(f"{len(conflicts)} تضارب غير محسوم: -{penalty:.2f}")

    gaps = sum(len(r.data_gaps) for r in reports)
    if gaps:
        penalty = round(min(gaps * 0.02, 0.12), 4)
        value -= penalty
        reasons.append(f"{gaps} فجوة بيانات معلنة: -{penalty:.2f}")

    unverified = sum(len(r.unverified_claims) for r in reports)
    if unverified:
        penalty = round(min(unverified * 0.015, 0.08), 4)
        value -= penalty
        reasons.append(f"{unverified} ادعاء غير مؤكد: -{penalty:.2f}")

    degraded = [r.agent_id.value for r in reports if r.degraded]
    if degraded:
        value = min(value, DEGRADED_CONFIDENCE_CAP)
        reasons.append(
            f"سقف {DEGRADED_CONFIDENCE_CAP:.2f} بسبب عمل وكلاء بلا مصادر حية: {', '.join(degraded)}"
        )

    value = round(max(CONFIDENCE_FLOOR, min(CONFIDENCE_CEIL, value)), 4)
    reasons.append(f"الثقة النهائية: {value:.2f}")
    return value, reasons


def risk_score(reports: list[AgentReport], conflicts: list[Conflict]) -> float:
    """درجة المخاطرة 0..1 — ترتفع مع الإلحاح والتضارب والإشارات الهبوطية."""
    if not reports:
        return 0.5

    urgency = max((r.urgency for r in reports), default=0.0)
    conflict_load = min(sum(c.severity for c in conflicts) / 2.0, 1.0)

    bearish_mass = 0.0
    total_mass = 0.0
    for report in reports:
        weight = AGENT_WEIGHTS.get(report.agent_id, 0.5) * report.confidence
        for signal in report.signals:
            total_mass += weight * signal.strength
            if signal.direction == Direction.BEARISH:
                bearish_mass += weight * signal.strength
    bearish_ratio = (bearish_mass / total_mass) if total_mass else 0.0

    risks = min(sum(len(r.risks) for r in reports) / 12.0, 1.0)

    score = (0.32 * urgency + 0.26 * conflict_load
             + 0.27 * bearish_ratio + 0.15 * risks)
    return round(max(0.0, min(1.0, score)), 4)


def quality_flags(reports: list[AgentReport], conflicts: list[Conflict]) -> list[str]:
    """أعلام جودة تُعرض للمستخدم بصراحة قبل أي توصية."""
    flags: list[str] = []
    degraded = [r.agent_id.value for r in reports if r.degraded]
    if degraded:
        flags.append(f"⚠ وكلاء بلا مصادر حية: {', '.join(degraded)}")
    if not any(r.evidence for r in reports):
        flags.append("⚠ لا توجد أدلة مُثبتة في هذه الدورة — القرار غير مسنود")
    if conflicts:
        flags.append(f"⚠ {len(conflicts)} تضارب بين الوكلاء يستوجب الحسم")
    social = next((r for r in reports if r.agent_id == AgentId.SOCIAL), None)
    hard = [r for r in reports if r.agent_id in (AgentId.FLOW, AgentId.MACRO)]
    if social and social.signals and hard and not any(r.signals for r in hard):
        flags.append("⚠ الإشارة مبنية على المشاعر بلا سند من التدفق أو الاقتصاد — ضجيج محتمل")
    thin = [r.agent_id.value for r in reports if len(r.evidence) < 2]
    if thin:
        flags.append(f"⚠ تقارير بأدلة شحيحة (أقل من مصدرين): {', '.join(thin)}")
    return flags

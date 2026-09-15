"""عقود البيانات المشتركة بين الوكلاء (Agent-to-Agent Contracts).

كل رسالة تنتقل بين الوكلاء هي `Envelope`، وكل تقرير متخصص هو `AgentReport`،
والمخرج النهائي للوكيل التنسيقي هو `ChiefDecision`.
هذه العقود هي ما يمنع الهلوسة معمارياً: لا يُقبل تقرير بلا أدلة وبلا ثقة معلنة.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


# ---------------------------------------------------------------- الأنواع

class AgentId(str, Enum):
    SOCIAL = "abu_aloloum"       # بوالعلوم - مشاعر ومنصات التواصل
    GEO = "political_analyst"    # المحلل السياسي
    MACRO = "economic_analyst"   # المحلل الاقتصادي
    BREAKING = "breaking_desk"   # غرفة الأخبار العاجلة
    FLOW = "the_trader"          # التاجر - تدفقات السوق والحيتان
    CHIEF = "chief"              # الوكيل التنسيقي وصانع القرار
    USER = "user"                # المستخدم - صاحب القرار الأعلى


class MessageType(str, Enum):
    TASK = "task"               # المستخدم/التنسيقي -> وكيل متخصص
    REPORT = "report"           # وكيل متخصص -> التنسيقي
    CLARIFICATION = "clarify"   # التنسيقي -> وكيل (طلب استيضاح عند التضارب)
    ALERT = "alert"             # بث عاجل من وكيل الأحداث إلى الجميع
    DECISION = "decision"       # التنسيقي -> المستخدم
    CHAT = "chat"               # دردشة مباشرة (واجهة الواتساب)
    STATUS = "status"           # مؤشرات الحالة (يكتب الآن / يبحث)


class Direction(str, Enum):
    BULLISH = "bullish"      # إيجابي/صاعد
    BEARISH = "bearish"      # سلبي/هابط
    NEUTRAL = "neutral"      # محايد


class Horizon(str, Enum):
    INTRADAY = "intraday"    # خلال اليوم
    SHORT = "short"          # أيام إلى أسابيع
    MEDIUM = "medium"        # أسابيع إلى أشهر
    LONG = "long"            # أشهر فأكثر


# ---------------------------------------------------------------- الأدلة

class Evidence(BaseModel):
    """مصدر واحد قابل للتحقق. بلا دليل = بلا ادعاء."""

    source_type: Literal[
        "news", "social", "market_data", "official", "filing", "research", "web", "unknown"
    ] = "unknown"
    title: str
    url: str | None = None
    publisher: str | None = None
    published_at: str | None = None
    excerpt: str = ""
    # موثوقية المصدر 0..1 (بيان رسمي أعلى من منشور مجهول)
    reliability: float = Field(default=0.5, ge=0.0, le=1.0)

    def key(self) -> str:
        return (self.url or f"{self.publisher}:{self.title}").strip().lower()


class Signal(BaseModel):
    """إشارة مُقاسة يستخرجها الوكيل من الأدلة."""

    name: str
    direction: Direction = Direction.NEUTRAL
    strength: float = Field(default=0.5, ge=0.0, le=1.0)
    horizon: Horizon = Horizon.SHORT
    asset_classes: list[str] = Field(default_factory=list)
    rationale: str = ""
    evidence_refs: list[int] = Field(default_factory=list)  # فهارس في قائمة الأدلة


class AgentReport(BaseModel):
    """المخرج المعياري لأي وكيل متخصص."""

    report_id: str = Field(default_factory=lambda: new_id("rep"))
    agent_id: AgentId
    topic: str
    created_at: str = Field(default_factory=now_iso)
    headline: str
    summary: str
    signals: list[Signal] = Field(default_factory=list)
    evidence: list[Evidence] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    # ما لم يستطع الوكيل التحقق منه - إعلانه إلزامي لمنع الهلوسة
    data_gaps: list[str] = Field(default_factory=list)
    unverified_claims: list[str] = Field(default_factory=list)
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    # درجة الإلحاح 0..1 (يستخدمها وكيل الأحداث العاجلة)
    urgency: float = Field(default=0.0, ge=0.0, le=1.0)
    degraded: bool = False   # صحيح إذا عمل الوكيل بلا مصادر حية
    notes: str = ""


class Conflict(BaseModel):
    """تضارب مكتشف بين تقريرَي وكيلين."""

    topic: str
    agent_a: AgentId
    agent_b: AgentId
    claim_a: str
    claim_b: str
    severity: float = Field(default=0.5, ge=0.0, le=1.0)
    resolution: str = ""


class DecisionOption(BaseModel):
    """خيار تنفيذي يُعرض على المستخدم صاحب القرار."""

    label: str
    action: str
    rationale: str
    risk_level: Literal["low", "medium", "high"] = "medium"
    expected_impact: str = ""
    invalidation: str = ""   # ما الذي يُبطل هذا الخيار


class Linkage(BaseModel):
    """ربط الخيوط: كيف يؤثر حدث في مجال على مجال آخر."""

    cause: str
    effect: str
    channel: str = ""         # قناة الانتقال (سيولة، سلاسل إمداد، مشاعر...)
    agents_involved: list[AgentId] = Field(default_factory=list)
    strength: float = Field(default=0.5, ge=0.0, le=1.0)


class ChiefDecision(BaseModel):
    """التقرير التنفيذي النهائي."""

    decision_id: str = Field(default_factory=lambda: new_id("dec"))
    topic: str
    created_at: str = Field(default_factory=now_iso)
    situation: str                                  # خلاصة الموقف الحالي
    linkages: list[Linkage] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    recommendation: str                             # القرار/التوصية الحاسمة
    stance: Direction = Direction.NEUTRAL
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    risk_score: float = Field(default=0.5, ge=0.0, le=1.0)
    options: list[DecisionOption] = Field(default_factory=list)
    invalidation_triggers: list[str] = Field(default_factory=list)
    watchlist: list[str] = Field(default_factory=list)
    sources_used: list[Evidence] = Field(default_factory=list)
    agent_confidences: dict[str, float] = Field(default_factory=dict)
    quality_flags: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- المغلّف

class Envelope(BaseModel):
    """مغلّف الرسالة الموحّد على ناقل الوكلاء (A2A)."""

    message_id: str = Field(default_factory=lambda: new_id("msg"))
    correlation_id: str                       # يربط كل رسائل دورة واحدة
    ts: str = Field(default_factory=now_iso)
    sender: AgentId
    recipients: list[AgentId] = Field(default_factory=list)
    type: MessageType
    topic: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    # أثر التتبع: لماذا أُرسلت هذه الرسالة (للتدقيق والمراجعة)
    trace: list[str] = Field(default_factory=list)

    def is_broadcast(self) -> bool:
        return not self.recipients


# ---------------------------------------------------------------- الواجهة

class ChatMessage(BaseModel):
    """رسالة كما تظهر في واجهة الدردشة."""

    id: str = Field(default_factory=lambda: new_id("cm"))
    chat_id: str
    author: str                # AgentId أو "user"
    text: str
    ts: str = Field(default_factory=now_iso)
    kind: Literal["text", "report", "decision", "alert", "system"] = "text"
    meta: dict[str, Any] = Field(default_factory=dict)


class CycleRequest(BaseModel):
    """طلب تشغيل دورة تحليل كاملة."""

    topic: str
    chat_id: str = "war_room"
    agents: list[AgentId] | None = None       # None = كل الوكلاء المتخصصين
    depth: Literal["quick", "standard", "deep"] = "standard"


# ------------------------------------------------- مخططات مخرجات النموذج
# هذه النماذج هي ما يُطلب من Claude إخراجه حرفياً (Structured Outputs).
# كل حقولها إلزامية بلا قيم افتراضية، لأن الحقل الاختياري يصبح باباً
# للتهرب من إعلان الفجوات والثقة.

class SignalDraft(BaseModel):
    name: str
    direction: Direction
    strength: float = Field(ge=0.0, le=1.0)
    horizon: Horizon
    asset_classes: list[str]
    rationale: str
    evidence_refs: list[int]


class ReportDraft(BaseModel):
    """ما يُخرجه الوكيل المتخصص من النموذج قبل دمج الأدلة المُثبتة."""

    headline: str
    summary: str
    signals: list[SignalDraft]
    risks: list[str]
    data_gaps: list[str]
    unverified_claims: list[str]
    confidence: float = Field(ge=0.0, le=1.0)
    urgency: float = Field(ge=0.0, le=1.0)
    notes: str


class LinkageDraft(BaseModel):
    cause: str
    effect: str
    channel: str
    agents_involved: list[str]
    strength: float = Field(ge=0.0, le=1.0)


class ConflictDraft(BaseModel):
    topic: str
    agent_a: str
    agent_b: str
    claim_a: str
    claim_b: str
    severity: float = Field(ge=0.0, le=1.0)
    resolution: str


class OptionDraft(BaseModel):
    label: str
    action: str
    rationale: str
    risk_level: Literal["low", "medium", "high"]
    expected_impact: str
    invalidation: str


class DecisionDraft(BaseModel):
    """ما يُخرجه الوكيل التنسيقي من النموذج."""

    situation: str
    linkages: list[LinkageDraft]
    conflicts: list[ConflictDraft]
    recommendation: str
    stance: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    options: list[OptionDraft]
    invalidation_triggers: list[str]
    watchlist: list[str]

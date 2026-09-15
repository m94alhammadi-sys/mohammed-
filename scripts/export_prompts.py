"""يولّد `docs/02-agents-prompts.md` من `backend/prompts.py` مباشرة.

الغرض: ألّا يفترق التوثيق عن السلوك الفعلي. أي تعديل على برومبت يُعاد
تصديره بأمر واحد:

    python3 scripts/export_prompts.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.agents.base import AGENT_PROFILES                      # noqa: E402
from backend.prompts import AGENT_PROMPTS, CHIEF_PROMPT, SHARED_CORE  # noqa: E402
from backend.schemas import AgentId                                 # noqa: E402
from backend.synthesis import AGENT_WEIGHTS                         # noqa: E402

OUT = ROOT / "docs" / "02-agents-prompts.md"

HEADER = """# ٢. برومبتات النظام لكل وكيل

> المستند الثاني من ثلاثة: **برومبتات النظام المخصصة لضمان عدم الخروج
> عن الاختصاص وتجنب الهلوسة**.
> الأول: [المعمارية وتدفق البيانات](01-architecture.md).
> الثالث: [التقنيات ومصادر البيانات](03-tech-stack.md).

⚠ **هذا المستند مُولَّد آلياً من `backend/prompts.py`** عبر
`python3 scripts/export_prompts.py`. لا تُحرّره يدوياً — حرّر المصدر
وأعد التوليد، حتى لا يفترق التوثيق عن السلوك الفعلي.

---

## ٢.١ كيف يُمنع الخروج عن الاختصاص والهلوسة؟

البرومبت وحده لا يكفي. المنع هنا على أربع طبقات متتالية:

| الطبقة | الآلية | الملف |
|---|---|---|
| ١. التعليمات | قسم «ما لا تفعله أبداً» + «تحذير منهجي إلزامي» في كل وكيل | `prompts.py` |
| ٢. المصادر | كل وكيل يقرأ من موصلاته وحدها؛ لا وصول متقاطع | `tools/registry.py` |
| ٣. المخطط | `ReportDraft` بلا حقل توصية، وبحقول فجوات إلزامية | `schemas.py` |
| ٤. ما بعد المعالجة | حذف إحالات الأدلة المخترعة، ووسم الإشارات بلا دليل | `agents/base.py` |

مثال على الطبقة الرابعة: لو أحال النموذج إلى الدليل رقم 99 وهو لا يملك
سوى 3 أدلة، تُحذف الإحالة وتُنقل الإشارة تلقائياً إلى
`unverified_claims`. البرومبت يطلب الصدق، والكود يتحقق منه.

## ٢.٢ سلّم الثقة المشترك

| المدى | الشرط |
|---|---|
| 0.85 – 1.00 | مصادر رسمية أو بيانات سوق مباشرة، متعددة ومتوافقة |
| 0.60 – 0.84 | مصادر إعلامية موثوقة متعددة، أو مصدر رسمي واحد |
| 0.35 – 0.59 | مصدر واحد غير رسمي، أو إشارات متضاربة |
| 0.00 – 0.34 | لا مصادر حية، أو معلومة متداولة بلا تأكيد |

---

## ٢.٣ البرومبت المشترك (يُضاف إلى كل وكيل)

```text
"""

FOOTER = """
## ٢.١٠ برومبتات المهام (Task Prompts)

إلى جانب برومبت النظام الثابت، يتلقى الوكيل في كل دورة برومبتين:

**أ) برومبت البحث** (`SpecialistAgent._research_prompt`): يعرض ما وصل
من كل موصل، ويعرض **صراحةً** الموصلات التي فشلت بعلامة ❌ وسبب فشلها،
ويضيف ما سبق أن قاله الوكيل عن الموضوع من الذاكرة.

**ب) برومبت الهيكلة** (`SpecialistAgent._structure_prompt`): يعطي فهرساً
مرقّماً للأدلة المتاحة ويطالب بربط كل إشارة بفهرس منها، ويمنع اختراع
فهارس غير موجودة.

**ج) برومبت التركيب** (`ChiefAgent._prompt`): يحمل التقارير كاملة،
ثم قسماً بعنوان «نتائج المحرك الحتمي (مُلزِمة — لا تعدّلها)» يحوي
الاتجاه والثقة والمخاطرة المحسوبة والتضارب المكتشف وأعلام الجودة.

## ٢.١١ تغطية الاختبارات

`tests/test_prompts.py` يتحقق آلياً من أن كل برومبت متخصص:
يرث البرومبت المشترك، وفيه قسم «ما لا تفعله أبداً»، وفيه تحذير منهجي
إلزامي، ويحيل التوصية إلى الوكيل التنسيقي. وأن برومبت التنسيقي يطالب
بشروط الإبطال، ويمنع متوسط الثقة، وينص على سقف 0.60 عند الانقطاع.
"""

ORDER = [AgentId.SOCIAL, AgentId.GEO, AgentId.MACRO, AgentId.BREAKING, AgentId.FLOW]


def build() -> str:
    parts = [HEADER + SHARED_CORE.rstrip() + "\n```\n\n---\n"]

    for index, agent_id in enumerate(ORDER, start=4):
        profile = AGENT_PROFILES[agent_id]
        parts.append(
            f"\n## ٢.{index} {profile.display_name} — `{agent_id.value}`\n\n"
            f"| | |\n|---|---|\n"
            f"| **الاختصاص** | {profile.tagline} |\n"
            f"| **وزنه في التصويت** | {AGENT_WEIGHTS[agent_id]:.2f} |\n"
            f"| **نطاقات بحثه المفضّلة** | {', '.join(profile.preferred_domains) or '—'} |\n"
            f"| **موصلات بياناته** | انظر `CONNECTORS[{agent_id.name}]` في `tools/registry.py` |\n\n"
            f"```text\n{AGENT_PROMPTS[agent_id].rstrip()}\n```\n\n---\n"
        )

    parts.append(
        "\n## ٢.٩ الوكيل التنسيقي وصانع القرار — `chief`\n\n"
        "| | |\n|---|---|\n"
        "| **الاختصاص** | تركيب تقارير الوكلاء إلى قرار تنفيذي |\n"
        "| **موصلات بياناته** | **لا شيء** — مصدره الوحيد تقارير الوكلاء |\n"
        "| **أرقامه** | تُحسب في `synthesis.py` وتُفرض عليه بعد المسودة |\n\n"
        f"```text\n{CHIEF_PROMPT.rstrip()}\n```\n\n---\n"
        + FOOTER
    )
    return "".join(parts)


if __name__ == "__main__":
    OUT.write_text(build(), encoding="utf-8")
    print(f"كُتب {OUT} ({OUT.stat().st_size} بايت)")

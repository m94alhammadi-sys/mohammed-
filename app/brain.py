"""عقل الوكيل — حلقة الأدوات مع Claude."""

from __future__ import annotations

import json
import logging
from concurrent.futures import ThreadPoolExecutor

import anthropic

from . import db
from .config import settings
from .prompts import SYSTEM_PROMPT, build_context
from .tools import TOOL_SCHEMAS, dispatch, server_tools

log = logging.getLogger(__name__)

MAX_ITERATIONS = 12          # سقف دورات الأدوات لكل رسالة
MAX_TOKENS = 8000
HISTORY_LIMIT = 40

_CLIENT: anthropic.Anthropic | None = None
_fallback_supported = settings.enable_refusal_fallback


class BrainError(RuntimeError):
    """فشل في توليد الرد."""


def get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        if not settings.anthropic_api_key:
            raise BrainError("ANTHROPIC_API_KEY غير مضبوط في ملف .env")
        _CLIENT = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    return _CLIENT


def _system_blocks(phone: str, user_name: str | None) -> list[dict]:
    """الجزء الثابت مُخزَّن مؤقتاً (cache)، والسياق المتغير بعده."""
    watchlist = [r["symbol"] for r in db.get_watchlist(phone)]
    memory = db.recall(phone)
    return [
        {
            "type": "text",
            "text": SYSTEM_PROMPT,
            "cache_control": {"type": "ephemeral"},
        },
        {
            "type": "text",
            "text": build_context(phone, user_name, watchlist, memory),
        },
    ]


def _create(**kwargs):
    """نداء واحد للنموذج مع البث، ومع الاحتياط التلقائي عند الرفض إن كان مدعوماً."""
    global _fallback_supported
    client = get_client()

    if _fallback_supported:
        try:
            with client.beta.messages.stream(
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                **kwargs,
            ) as stream:
                return stream.get_final_message()
        except (TypeError, anthropic.BadRequestError) as exc:
            # نسخة SDK أو حساب لا يدعم المعامل — نطفئه ونكمل عادي
            log.warning("الاحتياط التلقائي غير مدعوم، سأتابع بدونه: %s", exc)
            _fallback_supported = False

    with client.messages.stream(**kwargs) as stream:
        return stream.get_final_message()


def _run_tools(blocks, phone: str) -> list[dict]:
    """ينفّذ أدوات الاستدعاء بالتوازي (كلها عمليات شبكة بطيئة)."""
    if not blocks:
        return []

    def run(block):
        args = block.input if isinstance(block.input, dict) else {}
        log.info("أداة: %s | %s", block.name, json.dumps(args, ensure_ascii=False)[:200])
        return {
            "type": "tool_result",
            "tool_use_id": block.id,
            "content": dispatch(block.name, args, phone),
        }

    if len(blocks) == 1:
        return [run(blocks[0])]

    with ThreadPoolExecutor(max_workers=min(len(blocks), 6)) as pool:
        return list(pool.map(run, blocks))


def _final_text(message) -> str:
    parts = [block.text for block in message.content if block.type == "text" and block.text.strip()]
    return "\n\n".join(parts).strip()


def _agent_loop(phone: str, user_name: str | None, messages: list[dict]) -> str:
    """الحلقة الرئيسية: نادِ النموذج، نفّذ الأدوات، كرّر حتى ينتهي."""
    system = _system_blocks(phone, user_name)
    tools = TOOL_SCHEMAS + server_tools()

    for iteration in range(MAX_ITERATIONS):
        response = _create(
            model=settings.model,
            max_tokens=MAX_TOKENS,
            system=system,
            messages=messages,
            tools=tools,
            thinking={"type": "adaptive"},
            output_config={"effort": settings.effort},
        )

        if response.stop_reason == "refusal":
            detail = getattr(response, "stop_details", None)
            log.warning("رفض النموذج الرد: %s", detail)
            return "ما أقدر أجاوب على هذا الطلب. جرّب تصيغه بشكل ثاني أو اسأل عن شي غيره."

        # النموذج استنفد دورات أداة الخادم — نعيد الإرسال ليكمل
        if response.stop_reason == "pause_turn":
            messages.append({"role": "assistant", "content": response.content})
            db.save_message(phone, "assistant", _serialize(response.content))
            continue

        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        messages.append({"role": "assistant", "content": response.content})
        db.save_message(phone, "assistant", _serialize(response.content))

        if not tool_blocks:
            text = _final_text(response)
            if text:
                return text
            log.warning("رد فارغ من النموذج (stop_reason=%s)", response.stop_reason)
            return "صار عندي خلل بسيط في التوليد. أعد السؤال لو سمحت."

        results = _run_tools(tool_blocks, phone)
        messages.append({"role": "user", "content": results})
        db.save_message(phone, "user", results)

    log.warning("بلغت الحلقة سقف %s دورات", MAX_ITERATIONS)
    return (
        "الطلب احتاج بحثاً أطول من المتوقع ووقفت عند حد معيّن. "
        "جزّئ السؤال لو سمحت — مثلاً اسأل عن رمز واحد في كل مرة."
    )


def _serialize(content) -> list[dict]:
    """يحوّل بلوكات الرد إلى JSON قابل للتخزين وإعادة الإرسال."""
    out = []
    for block in content:
        if hasattr(block, "model_dump"):
            out.append(block.model_dump(exclude_none=True))
        elif isinstance(block, dict):
            out.append(block)
    return out


def respond(phone: str, user_text: str, user_name: str | None = None) -> str:
    """الرد على رسالة واردة من المستخدم."""
    db.ensure_user(phone, user_name)
    history = db.load_history(phone, HISTORY_LIMIT)

    user_message = {"role": "user", "content": [{"type": "text", "text": user_text}]}
    db.save_message(phone, "user", user_message["content"], is_anchor=True)

    return _agent_loop(phone, user_name, history + [user_message])


def run_task(phone: str, task_prompt: str, user_name: str | None = None) -> str:
    """تنفيذ مهمة مجدولة (موجز صباحي، تنبيه، صدمة إخبارية) بنفس العقل والأدوات.

    تُحفظ في نفس سجل المحادثة حتى يقدر المستخدم يسأل «ليش نبهتني؟» ويفهم الوكيل.
    """
    db.ensure_user(phone, user_name)
    history = db.load_history(phone, HISTORY_LIMIT)

    task_message = {"role": "user", "content": [{"type": "text", "text": task_prompt}]}
    db.save_message(phone, "user", task_message["content"], is_anchor=True)

    return _agent_loop(phone, user_name, history + [task_message])

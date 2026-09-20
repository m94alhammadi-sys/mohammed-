"""واجهة واتساب عبر WhatsApp Cloud API من Meta (اختيارية).

تحتاج: حساب Meta Business، رقم واتساب معتمد، ورابط HTTPS عام (أو ngrok).
لو ما عندك هذا كله، بوت تيليجرام يكفي ويشتغل بدون أي إعداد خارجي.
"""

from __future__ import annotations

import logging

import httpx
from fastapi import BackgroundTasks, FastAPI, Query, Request, Response

from advisor.brain import AdvisorBrain
from advisor.config import settings
from advisor.service import AdvisorService
from advisor.storage import Storage
from advisor.text import split_message

log = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v21.0/{phone_id}/messages"
WHATSAPP_LIMIT = 3800

app = FastAPI(title="المستشار المالي — واتساب")

_storage = Storage(settings.db_path)
_service = AdvisorService(_storage, AdvisorBrain()) if settings.anthropic_api_key else None


@app.get("/webhook")
async def verify(
    mode: str = Query("", alias="hub.mode"),
    token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
) -> Response:
    """تحقق Meta من ملكية الـ webhook."""
    if mode == "subscribe" and token and token == settings.whatsapp_verify_token:
        return Response(content=challenge, media_type="text/plain")
    return Response(content="forbidden", status_code=403)


@app.post("/webhook")
async def incoming(request: Request, background: BackgroundTasks) -> dict:
    """يستقبل الرسائل ويردّ في الخلفية (Meta تتوقع رد 200 خلال ثوانٍ)."""
    payload = await request.json()
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            for message in (change.get("value") or {}).get("messages", []) or []:
                if message.get("type") != "text":
                    continue
                sender = message.get("from", "")
                text = (message.get("text") or {}).get("body", "").strip()
                if sender and text:
                    background.add_task(_handle, sender, text)
    return {"status": "ok"}


async def _handle(sender: str, text: str) -> None:
    if _service is None:
        await _send(sender, "الخدمة غير مهيّأة: ANTHROPIC_API_KEY مفقود.")
        return
    try:
        # رقم الواتساب يُستخدم كمعرّف مستخدم دائم.
        user_id = int("".join(ch for ch in sender if ch.isdigit()) or "0")
        profile = await _storage.ensure_user(user_id, display_name=sender, channel="whatsapp")

        command = text.lower().lstrip("/")
        if command in ("brief", "إحاطة", "تقرير"):
            reply = await _service.daily_brief(profile)
        elif command in ("news", "أخبار"):
            reply = await _service.news_digest(profile)
        elif command in ("portfolio", "محفظة", "محفظتي"):
            reply = await _service.portfolio_review(profile)
        elif command in ("market", "أسعار", "السوق"):
            await _send(sender, _strip_html(await _service.market_snapshot_text()))
            return
        else:
            reply = await _service.chat(profile, text)

        await _send(sender, reply.formatted())
    except Exception as exc:
        log.exception("فشل معالجة رسالة واتساب: %s", exc)
        await _send(sender, "صار خطأ تقني. جرّب مرة أخرى بعد قليل.")


async def _send(to: str, text: str) -> None:
    if not (settings.whatsapp_token and settings.whatsapp_phone_number_id):
        log.warning("إعدادات واتساب ناقصة — لم تُرسل الرسالة إلى %s", to)
        return
    url = GRAPH_URL.format(phone_id=settings.whatsapp_phone_number_id)
    headers = {"Authorization": f"Bearer {settings.whatsapp_token}"}
    async with httpx.AsyncClient(timeout=30.0) as client:
        for chunk in split_message(text, WHATSAPP_LIMIT):
            body = {
                "messaging_product": "whatsapp",
                "to": to,
                "type": "text",
                "text": {"body": chunk},
            }
            resp = await client.post(url, headers=headers, json=body)
            if resp.status_code >= 400:
                log.warning("رفض واتساب الرسالة (%s): %s", resp.status_code, resp.text[:300])


def _strip_html(text: str) -> str:
    return text.replace("<b>", "*").replace("</b>", "*")

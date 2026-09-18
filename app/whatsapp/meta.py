"""مزوّد Meta WhatsApp Cloud API (الرسمي)."""

from __future__ import annotations

import logging

import httpx

from ..config import normalize_phone, settings
from .base import InboundMessage, WhatsAppProvider, split_message, to_whatsapp_markdown

log = logging.getLogger(__name__)

GRAPH_VERSION = "v21.0"


class MetaProvider(WhatsAppProvider):
    name = "meta"

    def __init__(self, token: str | None = None, phone_number_id: str | None = None) -> None:
        self.token = token or settings.meta_access_token
        self.phone_number_id = phone_number_id or settings.meta_phone_number_id
        self.base_url = f"https://graph.facebook.com/{GRAPH_VERSION}/{self.phone_number_id}/messages"

    # ---------------------------------------------------------------- الإرسال

    def _post(self, body: dict) -> str | None:
        if not self.token or not self.phone_number_id:
            log.error("إعدادات Meta ناقصة (META_ACCESS_TOKEN / META_PHONE_NUMBER_ID)")
            return None
        headers = {"Authorization": f"Bearer {self.token}", "Content-Type": "application/json"}
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.base_url, json=body, headers=headers)
            if response.status_code >= 400:
                log.error("رفض من واتساب (%s): %s", response.status_code, response.text[:500])
                return None
            data = response.json()
            return (data.get("messages") or [{}])[0].get("id")
        except httpx.HTTPError as exc:
            log.error("فشل الاتصال بواتساب: %s", exc)
            return None

    def send_text(self, phone: str, text: str) -> list[str]:
        phone = normalize_phone(phone)
        ids: list[str] = []
        for chunk in split_message(to_whatsapp_markdown(text)):
            message_id = self._post({
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": phone,
                "type": "text",
                "text": {"preview_url": False, "body": chunk},
            })
            if message_id:
                ids.append(message_id)
        return ids

    def send_template(self, phone: str, template: str, params: list[str]) -> str | None:
        return self._post({
            "messaging_product": "whatsapp",
            "to": normalize_phone(phone),
            "type": "template",
            "template": {
                "name": template,
                "language": {"code": settings.meta_template_lang},
                "components": [{
                    "type": "body",
                    "parameters": [{"type": "text", "text": p} for p in params],
                }] if params else [],
            },
        })

    # ---------------------------------------------------------------- الاستقبال

    def verify_webhook(self, mode: str, token: str, challenge: str) -> str | None:
        """تحقق Meta من الـ webhook عند الربط الأولي."""
        if mode == "subscribe" and token == settings.meta_verify_token:
            return challenge
        return None

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        messages: list[InboundMessage] = []
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                # خريطة الأرقام إلى الأسماء من حقل contacts
                names = {
                    c.get("wa_id"): (c.get("profile") or {}).get("name")
                    for c in value.get("contacts", [])
                }
                for message in value.get("messages", []):
                    phone = normalize_phone(message.get("from", ""))
                    kind = message.get("type", "unsupported")
                    if kind == "text":
                        text = (message.get("text") or {}).get("body", "")
                    elif kind == "button":
                        text = (message.get("button") or {}).get("text", "")
                    elif kind == "interactive":
                        interactive = message.get("interactive") or {}
                        text = (
                            (interactive.get("button_reply") or {}).get("title")
                            or (interactive.get("list_reply") or {}).get("title")
                            or ""
                        )
                    else:
                        text = ""
                    messages.append(InboundMessage(
                        phone=phone,
                        text=text,
                        name=names.get(message.get("from")),
                        message_id=message.get("id"),
                        kind=kind if kind in ("text", "audio", "image") else "unsupported",
                    ))
        return messages

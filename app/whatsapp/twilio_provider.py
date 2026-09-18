"""مزوّد Twilio لواتساب — بديل سريع للتجربة (Sandbox)."""

from __future__ import annotations

import logging

import httpx

from ..config import normalize_phone, settings
from .base import InboundMessage, WhatsAppProvider, split_message, to_whatsapp_markdown

log = logging.getLogger(__name__)


class TwilioProvider(WhatsAppProvider):
    name = "twilio"

    def __init__(self, sid: str | None = None, token: str | None = None, sender: str | None = None) -> None:
        self.sid = sid or settings.twilio_account_sid
        self.token = token or settings.twilio_auth_token
        self.sender = sender or settings.twilio_whatsapp_from
        self.base_url = f"https://api.twilio.com/2010-04-01/Accounts/{self.sid}/Messages.json"

    def _post(self, data: dict) -> str | None:
        if not (self.sid and self.token and self.sender):
            log.error("إعدادات Twilio ناقصة (SID / TOKEN / FROM)")
            return None
        try:
            with httpx.Client(timeout=30.0) as client:
                response = client.post(self.base_url, data=data, auth=(self.sid, self.token))
            if response.status_code >= 400:
                log.error("رفض من Twilio (%s): %s", response.status_code, response.text[:500])
                return None
            return response.json().get("sid")
        except httpx.HTTPError as exc:
            log.error("فشل الاتصال بـ Twilio: %s", exc)
            return None

    def send_text(self, phone: str, text: str) -> list[str]:
        to = f"whatsapp:+{normalize_phone(phone)}"
        ids: list[str] = []
        for chunk in split_message(to_whatsapp_markdown(text), limit=1550):   # حد Twilio أقل
            message_id = self._post({"From": self.sender, "To": to, "Body": chunk})
            if message_id:
                ids.append(message_id)
        return ids

    def send_template(self, phone: str, template: str, params: list[str]) -> str | None:
        """Twilio يستخدم ContentSid للقوالب؛ ``template`` هنا هو الـ ContentSid."""
        import json

        variables = {str(i + 1): p for i, p in enumerate(params)}
        return self._post({
            "From": self.sender,
            "To": f"whatsapp:+{normalize_phone(phone)}",
            "ContentSid": template,
            "ContentVariables": json.dumps(variables, ensure_ascii=False),
        })

    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        """Twilio يرسل نموذجاً مسطّحاً (form-encoded) لا JSON متداخل."""
        sender = payload.get("From", "")
        if not sender:
            return []
        return [InboundMessage(
            phone=normalize_phone(sender),
            text=payload.get("Body", "") or "",
            name=payload.get("ProfileName"),
            message_id=payload.get("MessageSid"),
            kind="text" if payload.get("Body") else "unsupported",
        )]

"""الواجهة المشتركة لمزوّدي واتساب."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass

# حد واتساب لرسالة نصية واحدة
MAX_LEN = 4000


@dataclass
class InboundMessage:
    """رسالة واردة بعد توحيد شكلها بين المزوّدين."""

    phone: str
    text: str
    name: str | None = None
    message_id: str | None = None
    kind: str = "text"       # text | audio | image | unsupported


def split_message(text: str, limit: int = MAX_LEN) -> list[str]:
    """يقسّم الرسائل الطويلة عند حدود الفقرات/الأسطر بدل القطع العشوائي."""
    text = text.strip()
    if len(text) <= limit:
        return [text] if text else []

    chunks: list[str] = []
    remaining = text
    while len(remaining) > limit:
        window = remaining[:limit]
        # نبحث عن أفضل نقطة قطع: فقرة، ثم سطر، ثم نهاية جملة، ثم مسافة
        cut = -1
        for sep in ("\n\n", "\n", ". ", "، ", " "):
            found = window.rfind(sep)
            if found > limit * 0.5:
                cut = found + len(sep)
                break
        if cut <= 0:
            cut = limit
        chunks.append(remaining[:cut].strip())
        remaining = remaining[cut:].lstrip()
    if remaining:
        chunks.append(remaining)
    return [c for c in chunks if c]


def to_whatsapp_markdown(text: str) -> str:
    """يحوّل ماركداون الشائع إلى تنسيق واتساب (*عريض* و _مائل_)."""
    text = re.sub(r"(?<!\*)\*\*(?!\*)(.+?)(?<!\*)\*\*(?!\*)", r"*\1*", text, flags=re.S)
    text = re.sub(r"^#{1,6}\s*(.+)$", r"*\1*", text, flags=re.M)
    text = re.sub(r"^\s*[-*]\s+", "• ", text, flags=re.M)
    return text.strip()


class WhatsAppProvider(ABC):
    """عقد موحّد: إرسال نص، إرسال قالب، تحليل الـ webhook."""

    name: str = "base"

    @abstractmethod
    def send_text(self, phone: str, text: str) -> list[str]:
        """يرسل رسالة نصية (مقسّمة تلقائياً). يعيد معرّفات الرسائل."""

    @abstractmethod
    def send_template(self, phone: str, template: str, params: list[str]) -> str | None:
        """يرسل قالباً معتمداً — مطلوب خارج نافذة الـ 24 ساعة."""

    @abstractmethod
    def parse_webhook(self, payload: dict) -> list[InboundMessage]:
        """يحوّل حمولة الـ webhook إلى رسائل موحّدة."""

    def send(self, phone: str, text: str, in_window: bool = True, template: str | None = None) -> list[str]:
        """إرسال ذكي: نص حر داخل النافذة، وقالب خارجها."""
        if in_window or not template:
            return self.send_text(phone, text)
        preview = text.strip().replace("\n", " ")[:900]
        message_id = self.send_template(phone, template, [preview])
        return [message_id] if message_id else []

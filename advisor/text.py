"""أدوات نصية مشتركة بين قنوات المحادثة."""

from __future__ import annotations


def split_message(text: str, limit: int) -> list[str]:
    """تقسيم نص طويل على رسائل ضمن الحد، مع تفضيل القطع عند نهاية سطر.

    مضمون الانتهاء: لو لم يوجد سطر أو مسافة مناسبة، يُقطع عند الحد مباشرة.
    """
    if limit <= 0:
        raise ValueError("limit يجب أن يكون أكبر من صفر")
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    remaining = text
    while len(remaining) > limit:
        cut = remaining.rfind("\n", 0, limit)
        if cut < limit // 2:
            cut = remaining.rfind(" ", 0, limit)
        if cut <= 0:
            cut = limit
        parts.append(remaining[:cut])
        remaining = remaining[cut:].lstrip()
    if remaining:
        parts.append(remaining)
    return parts

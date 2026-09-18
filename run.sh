#!/usr/bin/env bash
# تشغيل المستشار الاقتصادي محلياً
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
    echo "لا يوجد ملف .env — انسخ القالب أولاً:"
    echo "  cp .env.example .env"
    exit 1
fi

if [ ! -d .venv ]; then
    echo "==> إنشاء البيئة الافتراضية"
    python3 -m venv .venv
    .venv/bin/pip install --quiet --upgrade pip
    .venv/bin/pip install --quiet -r requirements.txt
fi

PORT="${PORT:-8000}"
echo "==> المستشار الاقتصادي يعمل على المنفذ ${PORT}"
exec .venv/bin/uvicorn app.main:app --host 0.0.0.0 --port "${PORT}" "$@"

#!/usr/bin/env bash
# تشغيل «مجلس القرار» محلياً.
set -euo pipefail

cd "$(dirname "$0")"

if [ ! -f .env ]; then
  cp .env.example .env
  echo "أُنشئ ملف .env — أضف ANTHROPIC_API_KEY لتشغيل التحليل الحقيقي."
fi

python3 -m pip install -q -r requirements.txt
exec python3 -m uvicorn backend.main:app --reload \
  --host "${HOST:-127.0.0.1}" --port "${PORT:-8000}"

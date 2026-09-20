#!/usr/bin/env python3
"""نقطة تشغيل واجهة واتساب:  python run_whatsapp.py  (المنفذ 8080)"""

import os

import uvicorn

if __name__ == "__main__":
    uvicorn.run(
        "bots.whatsapp_webhook:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8080")),
    )

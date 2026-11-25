"""Send a concise Telegram alert when a scheduled pipeline fails."""
from __future__ import annotations

import json
import os
from urllib import request


def main() -> None:
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    run_url = os.environ.get("GITHUB_RUN_URL", "").strip()
    if not token or not chat_id or not run_url:
        raise RuntimeError("Failure alert configuration incomplete; check Action secrets and run URL.")

    payload = json.dumps({
        "chat_id": chat_id,
        "text": f"⚠️ আজকের দৈনিক তথ্য তৈরি বা টেলিগ্রামে পাঠানোর সময় সমস্যা হয়েছে।\nবিস্তারিত দেখুন: {run_url}",
        "disable_web_page_preview": True,
    }).encode("utf-8")
    req = request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=20) as response:
            result = json.load(response)
        if result.get("ok") is not True:
            raise RuntimeError("Telegram rejected the failure alert.")
    except Exception as exc:
        # urllib exceptions can include the URL, which includes the token.
        raise RuntimeError(f"Could not send Telegram failure alert ({type(exc).__name__}); credentials hidden.") from None
    print("Daily AI Agent failure alert sent.")


if __name__ == "__main__":
    main()

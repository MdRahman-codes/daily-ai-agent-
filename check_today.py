"""Skip repeated scheduled deliveries when today's briefing is already live."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib import request

BDT = timezone(timedelta(hours=6))


def is_current_day(payload: object, now: datetime | None = None) -> bool:
    if not isinstance(payload, dict):
        return False
    now = now or datetime.now(BDT)
    expected = now.astimezone(BDT).strftime("%A, %d %B %Y")
    return payload.get("date") == expected and bool(payload.get("business_idea"))


def should_skip(url: str, event: str) -> bool:
    if event != "schedule" or not url.startswith("https://"):
        return False
    try:
        req = request.Request(url, headers={"User-Agent": "DailyAIStudyAgent/2.0", "Cache-Control": "no-cache"})
        with request.urlopen(req, timeout=7) as response:
            payload = json.load(response)
        return is_current_day(payload)
    except (OSError, ValueError, TypeError):
        return False


def main() -> None:
    skip = should_skip(os.getenv("BRIEFING_URL", ""), os.getenv("GITHUB_EVENT_NAME", ""))
    print("Already published today; skipping duplicate." if skip else "Today's briefing needs publishing.")
    output = os.getenv("GITHUB_OUTPUT", "")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()

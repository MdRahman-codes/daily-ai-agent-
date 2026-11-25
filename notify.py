"""প্রতিদিনের তিনটি বাংলা তথ্যবার্তা টেলিগ্রামে পাঠানো হয়; চ্যাট ব্যবস্থা নেই।"""
from __future__ import annotations

import html
import json
import os
import time
from pathlib import Path

import requests


DIGITS = str.maketrans("0123456789", "০১২৩৪৫৬৭৮৯")


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Required secret missing: {name}")
    return value


def esc(value: object) -> str:
    return html.escape(str(value if value is not None else "তথ্য দেওয়া হয়নি"), quote=True)


def safe_text(value: object, limit: int = 1000) -> str:
    content = str(value if value is not None else "তথ্য দেওয়া হয়নি").strip()
    if len(content) > limit:
        content = content[:limit - 1].rstrip() + "…"
    return esc(content)


def money(value: object) -> str:
    if type(value) not in (int, float):
        return "হিসাব পাওয়া যায়নি"
    return "৳" + f"{value:,.0f}".translate(DIGITS)


def percentage(value: object) -> str:
    if type(value) not in (int, float):
        return "হিসাব পাওয়া যায়নি"
    return f"{value:.1f}".translate(DIGITS) + "%"


def build_messages(data: dict) -> list[str]:
    business = data.get("business_idea") or {}
    paper = data.get("research_paper") or {}
    facts = data.get("facts") or []
    if not isinstance(facts, list) or len(facts) != 2:
        raise RuntimeError("Two facts are required")
    summary = paper.get("summary") or {}
    day = safe_text(data.get("date_bn") or "সর্বশেষ প্রকাশিত তথ্য", 70)
    cost = f"{money(business.get('startup_cost_bdt_min'))} – {money(business.get('startup_cost_bdt_max'))}"
    source = str(paper.get("url") or "")
    if not source.startswith("https://"):
        source = "https://arxiv.org"
    messages = [
        (
            "💡 <b>আজকের ব্যবসার ধারণা</b>\n"
            f"📅 {day}\n"
            f"<b>{safe_text(business.get('title'), 180)}</b>\n\n"
            f"{safe_text(business.get('overview'), 800)}\n\n"
            f"<b>সম্ভাব্য ক্রেতা:</b> {safe_text(business.get('target_customer'), 250)}\n"
            f"<b>আয়ের উৎস:</b> {safe_text(business.get('revenue_model'), 240)}\n"
            f"<b>প্রাথমিক বিনিয়োগ:</b> {cost} (আনুমানিক)\n"
            f"<b>চাহিদার সম্ভাবনা:</b> {safe_text(business.get('demand_reason'), 250)}\n"
            f"<b>মাসিক আনুমানিক লাভের হার:</b> {percentage(business.get('illustrative_monthly_roi_percent'))}\n"
            f"<b>মাসিক আনুমানিক নিট লাভ বা ক্ষতি:</b> {money(business.get('illustrative_monthly_net_profit_bdt'))}\n\n"
            "<i>এগুলো কেবল সম্ভাব্য আয় ও ব্যয়ের হিসাব। লাভ নিশ্চিত নয়।</i>"
        ),
        (
            "🔬 <b>আজকের তথ্যপ্রযুক্তি গবেষণা</b>\n"
            f"📅 {day}\n"
            f"<b>{safe_text(paper.get('title_bn') or summary.get('title_bn'), 550)}</b>\n\n"
            f"{safe_text(summary.get('overview'), 1150)}\n\n"
            f"<b>গবেষণার ক্ষেত্র:</b> {safe_text(summary.get('field'), 100)}\n"
            f"<a href=\"{esc(source)}\">মূল গবেষণাপত্র দেখুন</a>"
        ),
        (
            "✨ <b>আজকের দুটি আকর্ষণীয় তথ্য</b>\n"
            f"📅 {day}\n\n"
            f"<b>১. প্রাত্যহিক জীবনের তথ্য:</b> {safe_text(facts[0].get('claim'), 550)}\n"
            f"{safe_text(facts[0].get('explanation'), 900)}\n\n"
            f"<b>২. অন্য একটি আকর্ষণীয় তথ্য:</b> {safe_text(facts[1].get('claim'), 550)}\n"
            f"{safe_text(facts[1].get('explanation'), 900)}"
        )
    ]
    if any(len(message) > 3900 for message in messages):
        raise RuntimeError("Telegram messages exceed the safe character limit")
    return messages


def send_message(api_url: str, chat_id: str, message: str) -> None:
    """Retry temporary Telegram errors; never reveal the bot token."""
    if len(message) > 3900:
        raise RuntimeError("Telegram message is too long")
    payload = {
        "chat_id": chat_id, "text": message,
        "parse_mode": "HTML", "disable_web_page_preview": True
    }
    for attempt in range(1, 4):
        try:
            response = requests.post(api_url, json=payload, timeout=(10, 30))
        except requests.RequestException as exc:
            if attempt == 3:
                raise RuntimeError(f"Telegram network failure ({type(exc).__name__}); secret hidden") from None
            time.sleep(2 ** (attempt - 1))
            continue
        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.ok and isinstance(data, dict) and data.get("ok") is True:
            return
        code = data.get("error_code", response.status_code) if isinstance(data, dict) else response.status_code
        if code not in {429, 500, 502, 503, 504} or attempt == 3:
            raise RuntimeError(f"Telegram API returned HTTP {code}; secret hidden")
        params = data.get("parameters", {}) if isinstance(data, dict) else {}
        retry_after = params.get("retry_after", 0) if isinstance(params, dict) else 0
        time.sleep(min(retry_after, 30) if isinstance(retry_after, int) and retry_after > 0
                   else 2 ** (attempt - 1))


def main() -> None:
    token = required_env("TELEGRAM_BOT_TOKEN")
    chat_id = required_env("TELEGRAM_CHAT_ID")
    content = Path(__file__).resolve().parent / "site" / "content.json"
    if not content.is_file():
        raise RuntimeError("Daily briefing content not found")
    briefing = json.loads(content.read_text(encoding="utf-8"))
    messages = build_messages(briefing)
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    for index, message in enumerate(messages, start=1):
        send_message(url, chat_id, message)
        print(f"Telegram message {index}/3 sent.")
    print("Sent all three Telegram notifications.")


if __name__ == "__main__":
    main()

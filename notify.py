"""Send the generated briefing to Telegram without leaking tokens into logs."""
from __future__ import annotations

import html
import json
import os
import time
from pathlib import Path

import requests


def required_env(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(
            f"Missing {name}. Add it in GitHub repository Settings > Secrets and variables > Actions."
        )
    return value


def esc(value: object) -> str:
    return html.escape(str(value or "Not specified"), quote=True)


def safe_text(value: object, max_length: int = 1200) -> str:
    text = str(value or "Not specified").strip()
    if len(text) > max_length:
        text = text[: max_length - 1].rstrip() + "…"
    return esc(text)


def send_message(api_url: str, chat_id: str, message: str, keyboard: dict) -> None:
    """Retry transient Telegram errors without logging the bot token."""
    if len(message) > 3900:
        raise RuntimeError("Telegram message is too long; refusing to truncate HTML markup.")
    for attempt in range(1, 4):
        response = None
        try:
            response = requests.post(
                api_url,
                json={
                    "chat_id": chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                    "disable_web_page_preview": True,
                    "reply_markup": keyboard,
                },
                timeout=(10, 30),
            )
        except requests.RequestException as exc:
            if attempt >= 3:
                raise RuntimeError(
                    f"Telegram request failed ({type(exc).__name__}); token hidden."
                ) from None
        else:
            try:
                payload = response.json()
            except ValueError:
                payload = {}
            if response.ok and isinstance(payload, dict) and payload.get("ok") is True:
                return
            code = response.status_code
            if isinstance(payload, dict) and isinstance(payload.get("error_code"), int):
                code = payload["error_code"]
            if code not in {429, 500, 502, 503, 504} or attempt >= 3:
                raise RuntimeError(f"Telegram API failed (HTTP {code}); check bot permissions and chat ID.")
            parameters = payload.get("parameters", {}) if isinstance(payload, dict) else {}
            retry_after = parameters.get("retry_after", 0) if isinstance(parameters, dict) else 0
            if isinstance(retry_after, int) and 0 < retry_after <= 30:
                time.sleep(retry_after)
                continue
        if attempt < 3:
            time.sleep(2 ** (attempt - 1))
    raise RuntimeError("Telegram message failed after retries.")

def main() -> None:
    token = required_env("TELEGRAM_BOT_TOKEN")
    chat_id = required_env("TELEGRAM_CHAT_ID")
    site_url = required_env("SITE_URL").rstrip("/")
    content_path = Path(__file__).resolve().parent / "site" / "content.json"
    if not content_path.is_file():
        raise RuntimeError(f"Generated content not found at {content_path}. The build artifact may be missing.")
    try:
        content = json.loads(content_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Could not read generated content.json ({type(exc).__name__}).") from exc

    business = content.get("business_idea", {})
    paper = content.get("research_paper", {})
    facts = content.get("facts", [])
    if not isinstance(facts, list) or len(facts) != 2:
        raise RuntimeError("content.json must contain exactly two facts before Telegram messages can be sent.")
    paper_url = str(paper.get("url", ""))
    if not paper_url.startswith("https://"):
        paper_url = "https://arxiv.org"
    miniapp_url = site_url + "/"  # Older dates are not archived; do not imply deep links work.
    api_url = f"https://api.telegram.org/bot{token}/sendMessage"

    messages = [
        (
            "💡 <b>Daily Business Idea</b>\n"
            f"<b>{safe_text(business.get('title'), 240)}</b>\n\n"
            f"{safe_text(business.get('overview'), 1000)}\n\n"
            f"<b>Target customer:</b> {safe_text(business.get('target_customer'), 400)}\n"
            f"<b>Revenue model:</b> {safe_text(business.get('revenue_model'), 400)}\n"
            f"<b>Estimated startup cost:</b> ৳{business.get('startup_cost_bdt_min', 0):,}–৳{business.get('startup_cost_bdt_max', 0):,} (indicative, not a quotation)\n"
            f"<b>Demand:</b> {safe_text(business.get('demand_reason'), 280)}\n\n"
            "Want the costs and pilot plan? Open the briefing and tap <b>Interested</b>."
        ),
        (
            "🔬 <b>Research Paper of the Day</b>\n"
            f"<b>{safe_text(paper.get('title'), 700)}</b>\n\n"
            f"{safe_text((paper.get('summary') or {}).get('overview', 'Summary unavailable'), 1000)}\n\n"
            f"<b>Field:</b> {safe_text((paper.get('summary') or {}).get('field', 'CSE'), 80)}\n"
            f"<a href=\"{esc(paper_url)}\">Open original research source</a>"
        ),
        (
            "✨ <b>Two Interesting Facts</b>\n\n"
            f"<b>Daily life:</b> {safe_text(facts[0].get('claim'), 550)}\n"
            f"{safe_text(facts[0].get('explanation'), 950)}\n\n"
            f"<b>Any topic:</b> {safe_text(facts[1].get('claim'), 550)}\n"
            f"{safe_text(facts[1].get('explanation'), 950)}\n\n"
            "Tap <b>Open briefing</b> to explore vocabulary and sources."
        ),
    ]
    keyboard = {
        "inline_keyboard": [[{
            "text": "📖 Open briefing & tap any word",
            "web_app": {"url": miniapp_url},
        }]]
    }
    for index, message in enumerate(messages, start=1):
        send_message(api_url, chat_id, message, keyboard)
        print(f"Telegram message {index}/3 sent.")
    print("Sent all three Telegram notifications.")


if __name__ == "__main__":
    main()

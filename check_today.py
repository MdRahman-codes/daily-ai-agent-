"""Skip a scheduled run ONLY if today's scheduled Telegram messages were delivered.

Publishing content.json (including a nighttime demo) is not proof of a morning
Telegram delivery. This checker uses the actual GitHub Actions notify job outcome.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib import request, error
from urllib.parse import quote

BDT = timezone(timedelta(hours=6))
GITHUB_API = "https://api.github.com"


def bangladesh_day(timestamp: str) -> str:
    """GitHub Actions UTC timestamps converted to the Bangladesh calendar date."""
    moment = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return moment.astimezone(BDT).strftime("%Y-%m-%d")


def api_json(url: str, token: str) -> dict:
    headers = {
        "User-Agent": "DailyAIStudyAgent/3.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=10) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected GitHub Actions API response")
    return data


def should_skip(event: str, repository: str, token: str, current_run_id: str,
                now: datetime | None = None) -> bool:
    """True only when a previous scheduled run completed the notify job today.

    Ignore manual demo/dispatch runs, even if they published today's briefing
    or sent messages last night. On API outage prefer attempting delivery
    instead of silently skipping it.
    """
    if event != "schedule" or "/" not in repository:
        return False
    today = (now or datetime.now(BDT)).astimezone(BDT).strftime("%Y-%m-%d")
    owner_repo = quote(repository, safe="/")
    list_url = f"{GITHUB_API}/repos/{owner_repo}/actions/runs?event=schedule&per_page=50"
    try:
        runs = api_json(list_url, token).get("workflow_runs", [])
        if not isinstance(runs, list):
            return False
        for run in runs:
            if not isinstance(run, dict):
                continue
            if (run.get("name") != "Daily AI Agent"
                    or run.get("event") != "schedule"
                    or str(run.get("id", "")) == str(current_run_id)
                    or run.get("status") != "completed"
                    or not run.get("created_at")):
                continue
            if bangladesh_day(run["created_at"]) != today:
                continue
            run_id = run.get("id")
            if type(run_id) is not int:
                continue
            job_url = f"{GITHUB_API}/repos/{owner_repo}/actions/runs/{run_id}/jobs?per_page=100"
            jobs = api_json(job_url, token).get("jobs", [])
            if any(isinstance(job, dict) and job.get("name") == "notify"
                   and job.get("conclusion") == "success"
                   for job in jobs if isinstance(jobs, list)):
                return True
    except (OSError, ValueError, KeyError, TypeError, RuntimeError) as exc:
        print(f"Delivery history unavailable ({type(exc).__name__}); proceeding rather than missing messages.")
    return False


def main() -> None:
    skip = should_skip(
        os.getenv("GITHUB_EVENT_NAME", ""),
        os.getenv("GITHUB_REPOSITORY", ""),
        os.getenv("GITHUB_TOKEN", ""),
        os.getenv("GITHUB_RUN_ID", ""),
    )
    if skip:
        print("Today's scheduled Telegram delivery is confirmed; avoiding duplicate notifications.")
    else:
        print("No successful scheduled Telegram delivery recorded today; generating and delivering briefing.")
    output = os.getenv("GITHUB_OUTPUT", "")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()

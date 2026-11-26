"""Guard the 07:00–07:30 Bangladesh delivery window and prevent duplicates.

Daily reminder pushes are initiated by an external exact-time scheduler, not
by the unreliable GitHub Actions cron. The cron remains as a backup.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from urllib import request
from urllib.parse import quote

BDT = timezone(timedelta(hours=6))
GITHUB_API = "https://api.github.com"


def bangladesh_day(timestamp: str) -> str:
    when = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    return when.astimezone(BDT).strftime("%Y-%m-%d")


def in_delivery_window(now: datetime | None = None) -> bool:
    """Accept 07:00:00 through 07:29:59 Bangladesh time."""
    when = (now or datetime.now(BDT)).astimezone(BDT)
    return when.hour == 7 and 0 <= when.minute < 30


def api_json(url: str, token: str) -> dict:
    headers = {
        "User-Agent": "DailyAIStudyAgent/4.0",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = request.Request(url, headers=headers)
    with request.urlopen(req, timeout=8) as response:
        data = json.load(response)
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected GitHub API format")
    return data


def should_skip(event: str, repository: str, token: str, current_run_id: str,
                now: datetime | None = None) -> bool:
    """Skip if outside the window or another *scheduled/push* run sent today.

    Explicit workflow_dispatch is for manual recovery and is never suppressed.
    The checker does NOT treat publishing a website as successful Telegram delivery.
    """
    if event == "workflow_dispatch":
        return False
    if event not in ("schedule", "push"):
        return True
    if not in_delivery_window(now):
        print("Outside 07:00–07:30 Bangladesh; no late or premature Telegram delivery.")
        return True
    if "/" not in repository:
        return False

    today = (now or datetime.now(BDT)).astimezone(BDT).strftime("%Y-%m-%d")
    owner_repo = quote(repository, safe="/")
    list_url = f"{GITHUB_API}/repos/{owner_repo}/actions/workflows/daily.yml/runs?per_page=40"
    try:
        runs = api_json(list_url, token).get("workflow_runs", [])
        if not isinstance(runs, list):
            return False
        for run in runs:
            if not isinstance(run, dict):
                continue
            if (run.get("name") != "Daily AI Agent"
                    or run.get("event") not in ("schedule", "push")
                    or str(run.get("id", "")) == str(current_run_id)
                    or run.get("status") != "completed"
                    or not run.get("created_at")):
                continue
            if bangladesh_day(run["created_at"]) != today:
                continue
            run_id = run.get("id")
            if type(run_id) is not int:
                continue
            jobs_url = f"{GITHUB_API}/repos/{owner_repo}/actions/runs/{run_id}/jobs?per_page=100"
            jobs = api_json(jobs_url, token).get("jobs", [])
            if isinstance(jobs, list) and any(
                isinstance(job, dict) and job.get("name") == "notify" and
                job.get("conclusion") == "success" for job in jobs
            ):
                print("Today's Telegram notification job already succeeded.")
                return True
    except (OSError, ValueError, TypeError, KeyError, RuntimeError) as exc:
        # Failing open may create a duplicate when GitHub's API is unavailable,
        # but is preferable to suppressing the only scheduled morning briefing.
        print(f"Unable to confirm delivery history ({type(exc).__name__}); trying delivery.")
    return False


def main() -> None:
    skip = should_skip(
        os.getenv("GITHUB_EVENT_NAME", ""),
        os.getenv("GITHUB_REPOSITORY", ""),
        os.getenv("GITHUB_TOKEN", ""),
        os.getenv("GITHUB_RUN_ID", ""),
    )
    print("Briefing skipped." if skip else "Starting morning briefing and Telegram delivery.")
    output = os.getenv("GITHUB_OUTPUT", "")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"skip={'true' if skip else 'false'}\n")


if __name__ == "__main__":
    main()

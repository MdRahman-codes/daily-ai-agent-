"""Generate the daily briefing with retry + model failover for Gemini API."""
from __future__ import annotations

import json
import ipaddress
import os
import random
import re
import shutil
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests

ROOT = Path(__file__).resolve().parent
SITE = ROOT / "site"
API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash").strip()
FALLBACK_MODELS = os.environ.get(
    "GEMINI_FALLBACK_MODELS", "gemini-3.6-flash,gemini-3.5-flash-lite"
)
RETRIES_PER_MODEL = max(1, min(int(os.environ.get("GEMINI_RETRIES_PER_MODEL", "3")), 5))
RETRYABLE_STATUSES = {408, 429, 500, 502, 503, 504}
HEADERS = {"User-Agent": "DailyAIStudyAgent/2.0"}


def model_chain() -> list[str]:
    """Return the configured primary model and unique fallbacks in order."""
    candidates = [MODEL] + [item.strip() for item in FALLBACK_MODELS.split(",")]
    result: list[str] = []
    for candidate in candidates:
        if candidate and candidate not in result:
            result.append(candidate)
    if not result:
        raise RuntimeError("No Gemini model configured. Set GEMINI_MODEL.")
    return result


def _api_error(response: requests.Response) -> str:
    """Extract a short API error without ever including request headers/API keys."""
    try:
        payload = response.json()
        message = payload.get("error", {}).get("message", "")
        status = payload.get("error", {}).get("status", "")
        details = f" {status}" if status else ""
        return (f"{message}{details}".strip() or response.text[:300]).replace("\n", " ")[:450]
    except (ValueError, AttributeError):
        return response.text[:300].replace("\n", " ")


def _retry_delay(response: requests.Response | None, attempt: int) -> float:
    """Respect Retry-After when possible; otherwise use short exponential backoff."""
    if response is not None:
        retry_after = response.headers.get("Retry-After", "").strip()
        try:
            if retry_after:
                return min(20.0, max(1.0, float(retry_after))) + random.uniform(0, 0.8)
        except ValueError:
            pass
    return min(16.0, 3.0 * (2 ** (attempt - 1))) + random.uniform(0, 0.8)


def gemini(prompt: str, temperature: float | None = None) -> str:
    """Call Gemini using bounded retries and fall back across configured models.

    `temperature` is accepted for compatibility with older callers but deliberately
    not sent: Gemini 3.6+ deprecates sampling parameters such as temperature.
    """
    del temperature
    if not API_KEY:
        raise RuntimeError(
            "Missing GEMINI_API_KEY. Add it under GitHub repository Settings > "
            "Secrets and variables > Actions. Do not put it in source code."
        )

    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json"},
    }
    last_problem = "No request was attempted."
    models = model_chain()

    for model_index, model in enumerate(models):
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        model_switch = False
        for attempt in range(1, RETRIES_PER_MODEL + 1):
            response: requests.Response | None = None
            try:
                response = requests.post(
                    url,
                    headers={
                        "x-goog-api-key": API_KEY,
                        "Content-Type": "application/json",
                    },
                    json=payload,
                    timeout=(15, 120),
                )
                if response.status_code < 400:
                    try:
                        data = response.json()
                    except ValueError as exc:
                        last_problem = f"{model} returned non-JSON response content."
                    else:
                        candidates = data.get("candidates") or []
                        parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
                        result = "".join(
                            part.get("text", "") for part in parts if isinstance(part, dict)
                        ).strip()
                        if result:
                            print(f"Gemini request succeeded with model {model}.")
                            return result
                        feedback = data.get("promptFeedback", {}).get("blockReason")
                        finish = candidates[0].get("finishReason", "") if candidates else ""
                        last_problem = (
                            f"{model} returned no text (blockReason={feedback or 'none'}, "
                            f"finishReason={finish or 'none'})."
                        )
                    # A non-HTTP malformed/empty response may be temporary; retry it.
                else:
                    detail = _api_error(response)
                    last_problem = f"{model} returned HTTP {response.status_code}: {detail}"
                    if response.status_code == 404:
                        print(f"Gemini model {model} was not found/available; trying fallback model.")
                        model_switch = True
                        break
                    if response.status_code not in RETRYABLE_STATUSES:
                        raise RuntimeError(
                            f"Gemini API configuration/request error: HTTP {response.status_code}: "
                            f"{detail}. Check model access, API key, and Google AI Studio project settings."
                        )
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_problem = f"{model} network/timeout error: {type(exc).__name__}."
            except requests.RequestException as exc:
                last_problem = f"{model} HTTP client error: {type(exc).__name__}."

            if attempt < RETRIES_PER_MODEL and not model_switch:
                delay = _retry_delay(response, attempt)
                print(
                    f"Gemini {model} attempt {attempt}/{RETRIES_PER_MODEL} failed; "
                    f"retrying in {delay:.1f}s. Reason: {last_problem}"
                )
                time.sleep(delay)
            elif not model_switch:
                print(f"Gemini model {model} exhausted retries. {last_problem}")

        if model_index < len(models) - 1:
            next_model = models[model_index + 1]
            print(f"Switching Gemini model from {model} to fallback {next_model}.")

    raise RuntimeError(
        "Gemini API failed on all configured models after retries. "
        f"Models tried: {', '.join(models)}. Last issue: {last_problem}. "
        "A 503 usually means temporary service overload; rerun the workflow later if all fallbacks fail."
    )


def json_from(raw_text: str) -> dict:
    """Parse model JSON, tolerating a code fence or harmless text around the object."""
    cleaned = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", raw_text.strip(), flags=re.IGNORECASE)
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start < 0 or end <= start:
            raise RuntimeError("Gemini returned invalid JSON; refusing to publish malformed content.")
        try:
            parsed = json.loads(cleaned[start : end + 1])
        except json.JSONDecodeError as exc:
            raise RuntimeError("Gemini returned invalid JSON; refusing to publish malformed content.") from exc
    if not isinstance(parsed, dict):
        raise RuntimeError("Gemini output must be a JSON object.")
    return parsed


def gemini_json(prompt: str) -> dict:
    """Try once more if the model returns malformed or non-object JSON.

    Do not retry API errors here; the Gemini client already handles those.
    """
    last_error = None
    for attempt in range(2):
        answer = gemini(prompt if attempt == 0 else prompt + "\nIMPORTANT: Return exactly one valid JSON object, not an array or prose.")
        try:
            return json_from(answer)
        except RuntimeError as exc:
            last_error = exc
            print(f"Gemini returned malformed JSON on attempt {attempt + 1}/2.")
    raise RuntimeError("Gemini returned malformed JSON twice; refusing to publish.") from last_error


def clean_https_url(value: object) -> str:
    """Reject private-network and malformed URLs from untrusted model output."""
    if not isinstance(value, str) or len(value) > 2048:
        return ""
    url = value.strip()
    try:
        p = urlparse(url)
        host = (p.hostname or "").rstrip(".").lower()
        if p.scheme != "https" or not host or p.username or p.password or p.port not in (None, 443):
            return ""
        if host in {"localhost", "localhost.localdomain"} or "." not in host:
            return ""
        try:
            ipaddress.ip_address(host)
            return ""  # Never accept IP literals supplied by an AI.
        except ValueError:
            pass
    except ValueError:
        return ""
    return url


def safe_probe(url: str) -> bool:
    """Probe only fixed trusted hosts, with redirects disabled (SSRF defense)."""
    host = (urlparse(url).hostname or "").lower()
    trusted = ("arxiv.org", "doi.org", "nasa.gov", "noaa.gov", "nih.gov", "cdc.gov",
               "nist.gov", "usgs.gov", "who.int", "nature.com", "science.org",
               "britannica.com", "si.edu", "nationalgeographic.com")
    return any(host == domain or host.endswith("." + domain) for domain in trusted)


def validate_fact_review(facts: list[dict], result: dict) -> list[dict]:
    """Do not quietly publish facts rejected by the secondary review."""
    reviews = result.get("facts")
    allowed = {"plausible; source still needs human review", "uncertain", "likely inaccurate"}
    if not isinstance(reviews, list) or len(reviews) != 2:
        raise RuntimeError("Fact review must return exactly two results; refusing to publish.")
    for index, review in enumerate(reviews):
        if not isinstance(review, dict) or review.get("status") not in allowed:
            raise RuntimeError("Fact review has invalid status; refusing to publish.")
        if review["status"] == "likely inaccurate":
            raise RuntimeError(f"Fact {index + 1} was flagged likely inaccurate; refusing to publish.")
        for field in ("reason", "safer_wording"):
            if not isinstance(review.get(field), str):
                review[field] = ""
        if review["status"] == "uncertain" and review["safer_wording"].strip():
            facts[index]["claim"] = review["safer_wording"].strip()
        facts[index]["source_verified"] = False  # URL response + AI opinion is not verification.
    return reviews


def reconstruct_abstract(inverted_index: object) -> str:
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""
    words: dict[int, str] = {}
    for word, positions in inverted_index.items():
        if isinstance(positions, list):
            for position in positions:
                if isinstance(position, int) and position >= 0:
                    words[position] = str(word)
    return " ".join(words[position] for position in sorted(words))


def get_arxiv_paper() -> dict | None:
    queries = [
        "all:cybersecurity OR all:computer_security",
        "cat:cs.SE",
        "all:machine_learning OR all:artificial_intelligence",
    ]
    query = random.choice(queries)
    url = "https://export.arxiv.org/api/query"
    for attempt in range(2):
        try:
            response = requests.get(
                url,
                params={
                    "search_query": query,
                    "start": 0,
                    "max_results": 10,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                },
                timeout=(10, 30),
                headers=HEADERS,
            )
            if response.status_code == 429:
                if attempt == 0:
                    time.sleep(5)
                    continue
                return None
            response.raise_for_status()
            root = ET.fromstring(response.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            for entry in root.findall("a:entry", ns):
                title = " ".join(entry.findtext("a:title", default="", namespaces=ns).split())
                abstract = " ".join(entry.findtext("a:summary", default="", namespaces=ns).split())
                paper_url = entry.findtext("a:id", default="", namespaces=ns).strip()
                if not title or not abstract or not paper_url.startswith(("https://arxiv.org/abs/", "http://arxiv.org/abs/")):
                    continue
                authors = [a.findtext("a:name", default="", namespaces=ns) for a in entry.findall("a:author", ns)]
                published = entry.findtext("a:published", default="", namespaces=ns)[:10]
                paper_url = paper_url.replace("http://", "https://", 1)
                return {
                    "title": title,
                    "abstract": abstract,
                    "url": paper_url,
                    "authors": authors[:6],
                    "published": published,
                    "metadata_source": "arXiv API",
                }
            return None
        except (requests.RequestException, ET.ParseError) as exc:
            print(f"arXiv request {attempt + 1}/2 failed: {type(exc).__name__}.")
            if attempt == 0:
                time.sleep(3)
    return None


def get_openalex_paper() -> dict | None:
    queries = [
        "cybersecurity computer security",
        "web development software engineering",
        "machine learning artificial intelligence",
    ]
    response = requests.get(
        "https://api.openalex.org/works",
        params={
            "search": random.choice(queries),
            "filter": "has_abstract:true",
            "sort": "publication_date:desc",
            "per-page": 10,
        },
        timeout=(10, 30),
        headers=HEADERS,
    )
    response.raise_for_status()
    for item in response.json().get("results", []):
        title = (item.get("title") or "").strip()
        abstract = reconstruct_abstract(item.get("abstract_inverted_index"))
        if not title or not abstract:
            continue
        location = item.get("primary_location") or {}
        paper_url = location.get("landing_page_url") or item.get("doi") or ""
        if paper_url.startswith("http://"):
            paper_url = paper_url.replace("http://", "https://", 1)
        if not paper_url.startswith("https://"):
            continue
        authors = []
        for authorship in item.get("authorships", [])[:6]:
            author = (authorship.get("author") or {}).get("display_name")
            if author:
                authors.append(author)
        return {
            "title": title,
            "abstract": abstract,
            "url": paper_url,
            "authors": authors,
            "published": item.get("publication_date") or "",
            "metadata_source": "OpenAlex API",
        }
    return None


def summarize_paper(title: str, abstract: str) -> dict:
    prompt = f"""Summarize this real research paper for a learner interested in CSE, cybersecurity, web development and AI.
Use ONLY the title and abstract supplied below. Do not invent results, statistics, or claims.
Return valid JSON with keys: overview (2 sentences), key_findings (2 concise bullet points), limitations (one cautious sentence; if not stated, say the abstract does not specify), practical_relevance (one sentence), field (one of CSE/Cybersecurity/Web Development/AI/Software Engineering), reading_level (beginner/intermediate/advanced).
Clearly distinguish abstract claims from interpretation.
TITLE: {title}
ABSTRACT: {abstract}"""
    result = gemini_json(prompt)
    result.setdefault("overview", "Summary unavailable; please open the original paper.")
    result.setdefault("key_findings", [])
    result.setdefault("limitations", "The abstract does not specify the limitations clearly.")
    result.setdefault("practical_relevance", "Review the original paper to assess practical relevance.")
    result.setdefault("field", "CSE")
    result.setdefault("reading_level", "intermediate")
    if not isinstance(result["overview"], str) or not isinstance(result["key_findings"], list):
        raise RuntimeError("Paper summary contains invalid types; refusing to publish.")
    result["key_findings"] = [item for item in result["key_findings"] if isinstance(item, str)][:4]
    for field in ("field", "reading_level", "limitations", "practical_relevance"):
        if not isinstance(result[field], str):
            result[field] = "Not specified"
    return result


def get_research_paper() -> dict:
    paper = None
    try:
        paper = get_arxiv_paper()
    except Exception as exc:  # fallback is deliberate; don't fabricate a record
        print(f"arXiv unavailable: {type(exc).__name__}.")
    if paper is None:
        print("Trying OpenAlex as a research-paper fallback.")
        try:
            paper = get_openalex_paper()
        except Exception as exc:
            raise RuntimeError(
                "Neither arXiv nor OpenAlex returned a usable paper. "
                f"Fallback error: {type(exc).__name__}. No paper will be fabricated."
            ) from exc
    if paper is None:
        raise RuntimeError("No paper with a usable title, abstract and source link was found. Try again later.")

    paper["source_reachable"] = False
    try:
        paper["url"] = clean_https_url(paper["url"])
        if paper["url"] and safe_probe(paper["url"]):
            check = requests.get(paper["url"], timeout=(10, 15), allow_redirects=False, headers=HEADERS)
            paper["source_reachable"] = check.status_code < 400
    except requests.RequestException:
        pass
    paper["summary"] = summarize_paper(paper["title"], paper["abstract"])
    paper["verification_note"] = (
        f"Title and abstract were retrieved from {paper['metadata_source']}. Source reachability only shows "
        "whether the URL responded; it does not independently verify all claims or the AI summary."
    )
    return paper


def check_fact_sources(facts: list[dict]) -> None:
    """Check HTTPS link reachability only; never present that as proof of a claim."""
    for fact in facts:
        source = clean_https_url(fact.get("source_url", ""))
        fact["source_url"] = source
        fact["source_verified"] = False
        fact["source_reachable"] = False
        if not source or not safe_probe(source):
            continue
        try:
            response = requests.get(source, timeout=(5, 10), allow_redirects=False, headers=HEADERS)
            fact["source_reachable"] = response.status_code < 400
        except requests.RequestException:
            pass


def main() -> None:
    SITE.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=6)))
    date_label = now.strftime("%A, %d %B %Y")
    paper = get_research_paper()
    prompt = f"""Create one daily briefing for a learner interested in CSE, cybersecurity, web development, AI and business.
Today's date in Bangladesh: {date_label}.
Return valid JSON only with keys business_idea and facts.
business_idea must have: title, overview (max 45 words), problem, target_customer, revenue_model, first_step, risks, confidence_note (do not promise profit).
Give exactly two facts. Each fact must have claim, explanation (one or two sentences), source_url, source_verified (boolean).
facts[0] must concern everyday life, habits, perception, sleep, learning or technology use. facts[1] may concern animals, space, science, history or any topic.
Prefer reputable primary or established sources. Do not invent statistics or URLs. If unsure, use empty source_url and source_verified false. Avoid myths, exaggerated claims, medical advice and generic repeated ideas. Do not include the research paper because it is supplied separately."""
    generated = gemini_json(prompt)
    business_idea = generated.get("business_idea")
    facts = generated.get("facts")
    if not isinstance(business_idea, dict):
        raise RuntimeError("Gemini did not return a valid business_idea object; refusing to publish.")
    if not isinstance(facts, list) or len(facts) != 2 or not all(isinstance(f, dict) for f in facts):
        raise RuntimeError("Gemini must return exactly two valid fact objects; refusing to publish.")
    required_business = ("title", "overview", "problem", "target_customer", "revenue_model", "first_step", "risks", "confidence_note")
    for field in required_business:
        if not isinstance(business_idea.get(field), str) or not business_idea[field].strip():
            business_idea[field] = "Not specified"
    for index, fact in enumerate(facts):
        for field in ("claim", "explanation"):
            if not isinstance(fact.get(field), str):
                fact[field] = ""
        if not fact["claim"].strip() or not fact["explanation"].strip():
            raise RuntimeError(f"Fact {index + 1} is missing its claim or explanation; refusing to publish.")
    check_fact_sources(facts)

    review_prompt = f"""Review these two proposed daily facts for factual accuracy, misleading wording, and whether each source URL is plausibly relevant.
Do not pretend you independently browsed URLs. source_reachable only means the web request received a response, not that the source supports the claim.
Return JSON with exactly two objects in facts, each having status (one of 'plausible; source still needs human review', 'uncertain', or 'likely inaccurate'), safer_wording, and reason. Be cautious and explicit about uncertainty.
FACTS: {json.dumps(facts, ensure_ascii=False)}"""
    fact_review_result = gemini_json(review_prompt)
    fact_review = validate_fact_review(facts, fact_review_result)

    payload = {
        "date": date_label,
        "business_idea": business_idea,
        "research_paper": paper,
        "facts": facts,
        "fact_review": fact_review,
        "verification_note": (
            "Research metadata was fetched from the named source and the URL was checked for reachability. "
            "AI summaries and facts receive a second-model review, but this is not a guarantee of correctness. "
            "Open the cited sources to verify important claims."
        ),
    }
    output = SITE / "content.json"
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    shutil.copy2(ROOT / "web" / "index.html", SITE / "index.html")
    shutil.copy2(ROOT / "web" / "config.js", SITE / "config.js")
    print(f"Daily content generated for {date_label}: {output}")


if __name__ == "__main__":
    main()

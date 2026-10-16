
import os
import json
import re
import shutil
import time
import random
import requests
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / "site"
SITE.mkdir(exist_ok=True)

API_KEY = os.environ.get("GEMINI_API_KEY", "").strip()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

HEADERS = {
    "User-Agent": "DailyAIStudyAgent/1.0"
}



def gemini(prompt, temperature=0.6):
    import time

    if not API_KEY:
        raise RuntimeError(
            "Missing GEMINI_API_KEY. Check GitHub Actions secrets."
        )

    url = (
        "https://generativelanguage.googleapis.com/v1beta/"
        f"models/{MODEL}:generateContent"
    )

    headers = {
        "x-goog-api-key": API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "contents": [
            {"parts": [{"text": prompt}]}
        ],
        "generationConfig": {
            "temperature": temperature,
            "responseMimeType": "application/json",
        },
    }

    last_error = None

    for attempt in range(4):
        try:
            response = requests.post(
                url,
                headers=headers,
                json=payload,
                timeout=(15, 180),
            )

            if response.status_code in (429, 500, 502, 503, 504):
                response.raise_for_status()

            response.raise_for_status()
            data = response.json()

            candidates = data.get("candidates", [])
            if not candidates:
                raise RuntimeError(
                    "Gemini returned no candidates. Check API response."
                )

            parts = candidates[0].get("content", {}).get("parts", [])
            result = "".join(
                part.get("text", "") for part in parts
            ).strip()

            if not result:
                raise RuntimeError(
                    "Gemini returned an empty response."
                )

            return result

        except (requests.Timeout, requests.ConnectionError) as exc:
            last_error = exc

        except requests.HTTPError as exc:
            status = exc.response.status_code

            if status not in (429, 500, 502, 503, 504):
                raise RuntimeError(
                    f"Gemini API HTTP {status}: "
                    f"{exc.response.text[:1000]}"
                ) from exc

            last_error = exc

        if attempt < 3:
            wait_seconds = 10 * (attempt + 1)
            print(
                f"Gemini request failed on attempt {attempt + 1}/4. "
                f"Retrying in {wait_seconds} seconds..."
            )
            time.sleep(wait_seconds)

    raise RuntimeError(
        "Gemini API failed after 4 attempts. "
        f"Last error: {last_error}"
    )



def json_from(text):
    text = re.sub(
        r"^```(?:json)?\s*|\s*```$",
        "",
        text.strip()
    )
    return json.loads(text)


def summarize_paper(title, abstract):
    prompt = f"""
Summarize this research paper for a learner interested in CSE,
cybersecurity, web development and AI.

Use ONLY the title and abstract supplied below. Do not invent
experimental results, statistics, or conclusions.

Return valid JSON with these keys:
overview: 2 sentences
key_findings: 2 concise bullet points
limitations: one cautious sentence. If not stated, say the abstract
does not specify.
practical_relevance: one sentence
field: one of CSE, Cybersecurity, Web Development, AI,
Software Engineering
reading_level: beginner, intermediate, or advanced

Clearly distinguish claims in the abstract from your interpretation.

TITLE: {title}

ABSTRACT: {abstract}
"""
    return json_from(gemini(prompt, 0.2))


def get_arxiv_paper():
    queries = [
        "all:cybersecurity OR all:computer_security",
        "cat:cs.SE",
        "all:machine_learning OR all:artificial_intelligence"
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
                    "sortOrder": "descending"
                },
                timeout=(10, 30),
                headers=HEADERS
            )

            if response.status_code == 429:
                if attempt == 0:
                    time.sleep(10)
                    continue
                return None

            response.raise_for_status()

            root = ET.fromstring(response.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entries = root.findall("a:entry", ns)

            for entry in entries:
                title = " ".join(
                    entry.findtext(
                        "a:title", default="", namespaces=ns
                    ).split()
                )
                abstract = " ".join(
                    entry.findtext(
                        "a:summary", default="", namespaces=ns
                    ).split()
                )
                paper_url = entry.findtext(
                    "a:id", default="", namespaces=ns
                ).strip()

                if not (
                    title
                    and abstract
                    and paper_url.startswith(
                        "https://arxiv.org/abs/"
                    )
                    or title
                    and abstract
                    and paper_url.startswith(
                        "http://arxiv.org/abs/"
                    )
                ):
                    continue

                authors = [
                    author.findtext(
                        "a:name", default="", namespaces=ns
                    )
                    for author in entry.findall("a:author", ns)
                ]

                published = entry.findtext(
                    "a:published", default="", namespaces=ns
                )[:10]

                paper_url = paper_url.replace(
                    "http://", "https://", 1
                )

                return {
                    "title": title,
                    "abstract": abstract,
                    "url": paper_url,
                    "authors": authors[:6],
                    "published": published,
                    "metadata_source": "arXiv API"
                }

            return None

        except (requests.RequestException, ET.ParseError):
            if attempt == 0:
                time.sleep(5)

    return None


def reconstruct_abstract(inverted_index):
    if not isinstance(inverted_index, dict) or not inverted_index:
        return ""

    words = {}

    for word, positions in inverted_index.items():
        if not isinstance(positions, list):
            continue

        for position in positions:
            if isinstance(position, int) and position >= 0:
                words[position] = word

    if not words:
        return ""

    return " ".join(
        words[position]
        for position in sorted(words)
    )


def get_openalex_paper():
    queries = [
        "cybersecurity computer security",
        "web development software engineering",
        "machine learning artificial intelligence"
    ]

    query = random.choice(queries)

    response = requests.get(
        "https://api.openalex.org/works",
        params={
            "search": query,
            "filter": "has_abstract:true",
            "sort": "publication_date:desc",
            "per-page": 10
        },
        timeout=(10, 30),
        headers=HEADERS
    )
    response.raise_for_status()

    results = response.json().get("results", [])

    for item in results:
        title = (item.get("title") or "").strip()
        abstract = reconstruct_abstract(
            item.get("abstract_inverted_index")
        )

        if not title or not abstract:
            continue

        location = item.get("primary_location") or {}
        paper_url = location.get("landing_page_url") or item.get("doi")

        if not paper_url:
            continue

        if paper_url.startswith("https://doi.org/"):
            pass
        elif paper_url.startswith("http://"):
            paper_url = paper_url.replace(
                "http://", "https://", 1
            )
        elif not paper_url.startswith("https://"):
            continue

        authors = []
        for authorship in item.get("authorships", [])[:6]:
            author = authorship.get("author") or {}
            name = author.get("display_name")
            if name:
                authors.append(name)

        return {
            "title": title,
            "abstract": abstract,
            "url": paper_url,
            "authors": authors,
            "published": item.get("publication_date") or "",
            "metadata_source": "OpenAlex API"
        }

    return None


def get_research_paper():
    paper = None

    # Try arXiv first. If it is rate-limited or unavailable,
    # use OpenAlex as an alternative metadata source.
    try:
        paper = get_arxiv_paper()
    except Exception as error:
        print("arXiv unavailable:", type(error).__name__)

    if paper is None:
        print("Trying OpenAlex as a research-paper fallback.")

        try:
            paper = get_openalex_paper()
        except Exception as error:
            raise RuntimeError(
                "Neither arXiv nor OpenAlex returned a usable paper. "
                "No unverified paper will be fabricated. "
                f"Fallback error: {type(error).__name__}"
            ) from error

    if paper is None:
        raise RuntimeError(
            "No paper with a usable title, abstract and original-source "
            "link was found. Please try again later."
        )

    # A URL responding successfully is a reachability check only.
    # It does not independently prove every research claim.
    paper["source_reachable"] = False

    try:
        check = requests.get(
            paper["url"],
            timeout=(10, 15),
            allow_redirects=True,
            headers=HEADERS
        )
        paper["source_reachable"] = check.status_code < 400
    except requests.RequestException:
        pass

    paper["summary"] = summarize_paper(
        paper["title"],
        paper["abstract"]
    )

    paper["verification_note"] = (
        "Title and abstract were retrieved from "
        + paper["metadata_source"]
        + ". Source reachability indicates only whether the URL responded; "
          "it does not guarantee that all claims in the paper or its "
          "AI-generated summary have been independently verified."
    )

    return paper


def main():
    now = datetime.now(timezone.utc).astimezone(
        timezone(timedelta(hours=6))
    )
    date_label = now.strftime("%A, %d %B %Y")

    paper = get_research_paper()

    prompt = f"""
Create one daily briefing for a learner interested in CSE,
cybersecurity, web development, AI and business.

Today's date in Bangladesh: {date_label}

Return valid JSON only with these keys:

business_idea:
- title
- overview (maximum 45 words)
- problem
- target_customer
- revenue_model
- first_step
- risks
- confidence_note (never promise guaranteed profit)

facts: exactly two items.
Each item must have:
- claim
- explanation (one or two sentences)
- source_url
- source_verified (boolean)

The first fact must concern day-to-day life, habits, perception,
learning, sleep or technology use.
The second fact may cover animals, space, science, history or another
topic.

Prefer primary or reputable sources. Do not invent URLs or statistics.
If you cannot confidently identify a source, use an empty source_url
and set source_verified to false. Do not give medical advice.
Avoid myths, exaggerated claims and repeated generic ideas.

Return JSON only.
"""

    generated = json_from(gemini(prompt, 0.5))

    if not isinstance(generated.get("business_idea"), dict):
        raise RuntimeError(
            "Gemini did not return a valid business idea."
        )

    facts = generated.get("facts", [])

    if not isinstance(facts, list) or len(facts) != 2:
        raise RuntimeError(
            "AI output did not contain exactly two facts."
        )

    for fact in facts:
        source = fact.get("source_url", "")
        fact["source_reachable"] = False

        # Reachability is not proof that a source supports a claim.
        if source.startswith("https://"):
            try:
                response = requests.get(
                    source,
                    timeout=(5, 10),
                    allow_redirects=True,
                    headers=HEADERS
                )
                fact["source_reachable"] = (
                    response.status_code < 400
                )
            except requests.RequestException:
                pass

    review_prompt = f"""
Review these two proposed facts for accuracy and misleading wording.

Do not pretend you independently browsed the sources.
A reachable URL does not prove that it supports the claim.

Return JSON with exactly two items in "facts".
Each item must contain:
- status: "plausible; source still needs human review",
  "uncertain", or "likely inaccurate"
- safer_wording
- reason

If a claim is uncertain, say so.

FACTS:
{json.dumps(facts, ensure_ascii=False)}
"""

    fact_review = json_from(gemini(review_prompt, 0.1))

    payload = {
        "date": date_label,
        "business_idea": generated["business_idea"],
        "research_paper": paper,
        "facts": facts,
        "fact_review": fact_review.get("facts", []),
        "verification_note": (
            "Research metadata came from the source identified for "
            "the paper. Source reachability is checked separately and "
            "does not prove that every claim is correct. AI-generated "
            "summaries and facts receive a second-model review, but "
            "important claims should still be checked against the "
            "original source."
        )
    }

    (SITE / "content.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )

    shutil.copy(ROOT / "web" / "index.html", SITE / "index.html")
    shutil.copy(ROOT / "web" / "config.js", SITE / "config.js")

    print("Daily content generated for", date_label)


if __name__ == "__main__":
    main()

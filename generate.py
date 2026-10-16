import os, json, re, shutil, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).parent
SITE = ROOT / 'site'
SITE.mkdir(exist_ok=True)
API_KEY = os.environ.get('GEMINI_API_KEY', '').strip()
MODEL = os.environ.get('GEMINI_MODEL', 'gemini-2.5-flash')


def gemini(prompt, temperature=0.6):
    if not API_KEY:
        raise RuntimeError('Missing GEMINI_API_KEY. Add it in GitHub repository Actions secrets.')
    url = f'https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={API_KEY}'
    r = requests.post(url, json={
        'contents': [{'parts': [{'text': prompt}]}],
        'generationConfig': {'temperature': temperature, 'responseMimeType': 'application/json'}
    }, timeout=90)
    r.raise_for_status()
    data = r.json()
    return data['candidates'][0]['content']['parts'][0]['text']


def json_from(text):
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip())
    return json.loads(text)



def get_research_paper():
    import random
    import time

    queries = [
        'all:cybersecurity OR all:computer_security',
        'all:web_development OR cat:cs.SE',
        'all:machine_learning OR all:artificial_intelligence'
    ]

    query = random.choice(queries)
    url = 'https://export.arxiv.org/api/query'

    response = None

    # Retry if arXiv is temporarily slow.
    for attempt in range(3):
        try:
            response = requests.get(
                url,
                params={
                    'search_query': query,
                    'start': 0,
                    'max_results': 20,
                    'sortBy': 'submittedDate',
                    'sortOrder': 'descending'
                },
                timeout=(10, 60),
                headers={
                    'User-Agent': 'DailyAIStudyAgent/1.0'
                }
            )
            response.raise_for_status()
            break
        except requests.RequestException:
            if attempt == 2:
                raise RuntimeError(
                    'Could not retrieve research papers from arXiv '
                    'after 3 attempts. Please try again later.'
                )
            time.sleep(15 * (attempt + 1))

    root = ET.fromstring(response.text)
    ns = {'a': 'http://www.w3.org/2005/Atom'}
    entries = root.findall('a:entry', ns)

    if not entries:
        raise RuntimeError('arXiv returned no papers for this query.')

    entry = entries[0]

    title = ' '.join(
        entry.findtext('a:title', default='', namespaces=ns).split()
    )
    abstract = ' '.join(
        entry.findtext('a:summary', default='', namespaces=ns).split()
    )
    paper_url = entry.findtext('a:id', default='', namespaces=ns)
    authors = [
        x.findtext('a:name', default='', namespaces=ns)
        for x in entry.findall('a:author', ns)
    ]
    published = entry.findtext(
        'a:published', default='', namespaces=ns
    )[:10]

    if not (
        title
        and abstract
        and paper_url.startswith('https://arxiv.org/abs/')
    ):
        raise RuntimeError(
            'Incomplete or unexpected arXiv record; refusing to publish.'
        )

    # Check the original paper URL, but do not fail the entire workflow
    # if the website is temporarily unreachable.
    source_verified = False

    try:
        check = requests.get(
            paper_url,
            timeout=(10, 20),
            allow_redirects=True,
            headers={'User-Agent': 'DailyAIStudyAgent/1.0'}
        )
        source_verified = check.status_code < 400
    except requests.RequestException:
        source_verified = False

    prompt = f'''Summarize this real research paper for a learner interested
in CSE, cybersecurity, web development and AI. Use only the metadata and
abstract below. Do not invent results or claims. Return JSON with keys:
overview (2 sentences), key_findings (2 concise bullets), limitations
(one cautious sentence; if not stated, say the abstract does not specify),
practical_relevance (one sentence), field (one of CSE/Cybersecurity/
Web Development/AI/Software Engineering), reading_level
(beginner/intermediate/advanced). Clearly distinguish abstract claims
from interpretation.
TITLE: {title}
ABSTRACT: {abstract}'''

    summary = json_from(gemini(prompt, 0.2))

    return {
        'title': title,
        'authors': authors[:6],
        'published': published,
        'url': paper_url,
        'abstract': abstract,
        'summary': summary,
        'source_verified': source_verified
    }



def main():
    now = datetime.now(timezone.utc).astimezone(timezone(timedelta(hours=6)))
    date_label = now.strftime('%A, %d %B %Y')
    paper = get_research_paper()
    prompt = f'''Create one daily briefing for a learner interested in CSE, cybersecurity, web development, AI and business. Today's date in Bangladesh: {date_label}. Return valid JSON only with keys: business_idea, facts. business_idea must have title, overview (max 45 words), problem, target_customer, revenue_model (short), first_step (short), risks (short), confidence_note (do not claim guaranteed profit). Give exactly two facts: facts[0] must be about ordinary day-to-day life, habits, perception, sleep, learning or technology use; facts[1] may be about any topic such as animals, space, science or history. Each fact must have claim, explanation (one or two sentences), and source_url. Use reputable primary or well-established sources; if you cannot confidently provide a direct source URL, put an empty string and set source_verified false. Avoid myths, exaggerated claims, medical advice, repeated generic ideas, and fabricated statistics. Do not include research paper; it is supplied separately.\nFor each fact, use an evidence-based claim that can be checked.\nReturn JSON.'''
    generated = json_from(gemini(prompt, 0.5))
    if len(generated.get('facts', [])) != 2:
        raise RuntimeError('AI output did not contain exactly two facts; refusing to publish.')
    # Check supplied source URLs for reachability. This does not prove the page supports the claim.
    for fact in generated['facts']:
        source = fact.get('source_url', '')
        fact['source_reachable'] = False
        if source.startswith('https://'):
            try:
                sr = requests.get(source, timeout=12, allow_redirects=True, headers={'User-Agent': 'DailyAIStudyAgent/1.0'})
                fact['source_reachable'] = sr.status_code < 400
            except requests.RequestException:
                fact['source_reachable'] = False
    # Independent second-pass model review; it does not replace source verification.
    check_prompt = f'''Review the following proposed daily facts for factual accuracy, misleading wording, and whether each source URL is plausibly relevant. Do not pretend you independently browsed URLs. The source_reachable field only means an HTTP request responded, not that the page supports the claim. Return JSON with exactly two items in facts, each with status ("plausible; source still needs human review", "uncertain", or "likely inaccurate"), safer_wording, and reason. If a claim is uncertain, say so. Facts: {json.dumps(generated['facts'], ensure_ascii=False)}'''
    fact_review = json_from(gemini(check_prompt, 0.1))
    payload = {
        'date': date_label,
        'business_idea': generated['business_idea'],
        'research_paper': paper,
        'facts': generated['facts'],
        'fact_review': fact_review.get('facts', []),
        'verification_note': 'The research metadata and arXiv URL were fetched from arXiv and the URL was checked for a successful response. AI-generated summaries and facts are additionally reviewed by a second model pass, but this is not a guarantee of correctness. Open the cited sources to confirm important claims.'
    }
    (SITE / 'content.json').write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copy(ROOT / 'web' / 'index.html', SITE / 'index.html')
    shutil.copy(ROOT / 'web' / 'config.js', SITE / 'config.js')
    print('Daily content generated for', date_label)

if __name__ == '__main__':
    main()

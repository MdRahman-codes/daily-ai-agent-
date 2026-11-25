# Daily AI Agent — Gemini + GitHub Actions + Telegram

এই project প্রতিদিন বাংলাদেশ সময় সকাল ৭টায় (UTC 01:00) একটি briefing তৈরি করে, GitHub Pages-এ publish করে, এবং Telegram-এ ৩টি message পাঠায়: business idea, একটি real research paper, ও দুটি interesting fact। Mini App-এ English word চাপলে Bangla meaning ও grammar explanation পাওয়া যায়।

## কী fix করা হয়েছে

- Gemini API `503 UNAVAILABLE`, `429`, timeout ও সাময়িক server error-এ retry/backoff করবে; primary model ব্যর্থ হলে fallback model try করবে।
- Default model `gemini-3.8-flash`; fallback `gemini-3.6-flash` এবং `gemini-3.5-flash-lite`। এগুলো environment variable দিয়ে পরিবর্তন করা যায়।
- Gemini 3.6+ request থেকে `temperature` সরানো হয়েছে। API key URL-এ না পাঠিয়ে `x-goog-api-key` header-এ যায়।
- arXiv API ব্যর্থ/empty হলে OpenAlex-এ research-paper metadata fallback চেষ্টা হয়; paper কল্পনা করে বানানো হয় না।
- Telegram content HTML-escape করা হয়, secrets/logs সুরক্ষিত রাখা হয়, আর missing secrets/artifacts-এর জন্য স্পষ্ট error আসে।
- Cloudflare Worker-এও model fallback/retry আছে এবং key browser-এর মধ্যে রাখা হয় না।
- Workflow build-এর আগে offline unit tests চালায়; Python cache files আর Git metadata archive-এ রাখা হয়নি।

> `503` সাধারণত Gemini service সাময়িকভাবে overloaded/unavailable থাকার লক্ষণ; এটা একা API key ভুল হওয়ার প্রমাণ নয়। Retry + fallback সবসময়ই সফল হবে এমন নিশ্চয়তা নেই। Google-এর API service সব fallback model-এ unavailable থাকলে workflow আবার চালাতে হবে।

## 1. GitHub Secrets সেট করো

Repository → **Settings → Secrets and variables → Actions → New repository secret**-এ এই তিনটি secret থাকতে হবে:

| Secret name | Value |
|---|---|
| `GEMINI_API_KEY` | Google AI Studio API key |
| `TELEGRAM_BOT_TOKEN` | BotFather থেকে পাওয়া bot token |
| `TELEGRAM_CHAT_ID` | তোমার Telegram chat ID |

কোনো secret কোডে লিখবে না বা Actions log/chat-এ paste করবে না। যদি আগে কখনও key/token public repository-তে commit করে থাকো, provider dashboard থেকে rotate/revoke করে নতুন secret বসাও।

## 2. GitHub Pages সেট করো

Repository → **Settings → Pages → Build and deployment → Source: GitHub Actions** নির্বাচন করো। তারপর **Actions → Daily AI Agent → Run workflow** দিয়ে manual test করো। Schedule প্রতিদিন `01:00 UTC`, অর্থাৎ বাংলাদেশে `07:00`-এ চলে; GitHub scheduled workflow কিছুটা দেরি করতে পারে।

## 3. Telegram bot

1. Telegram-এ `@BotFather` দিয়ে bot তৈরি করো।
2. Bot-এ `/start` পাঠাও এবং `TELEGRAM_CHAT_ID` নিশ্চিত করো।
3. Publish সফল হলে `notify` job থেকে Telegram message আসার কথা। Bot Mini App button-এর domain configuration প্রয়োজন হতে পারে; BotFather-এর `/setdomain` দিয়ে GitHub Pages-এর hostname সেট করো।

## 4. Word explanation API (Cloudflare Worker)

1. Cloudflare Dashboard → **Workers & Pages**-এ Worker তৈরি করে `worker.js` deploy করো।
2. Worker **Settings → Variables and Secrets**-এ secret `GEMINI_API_KEY` যোগ করো।
3. Optional variables:
   - `GEMINI_MODEL` — default `gemini-3.8-flash`
   - `GEMINI_FALLBACK_MODELS` — default `gemini-3.6-flash,gemini-3.5-flash-lite`
   - `ALLOWED_ORIGINS` — GitHub Pages origin allowlist. এই repository-এর Pages origin সাধারণত `https://mdrahman-codes.github.io`; comma-separated একাধিক origin-ও দেওয়া যায়।
4. `web/config.js`-এ `PASTE_YOUR_CLOUDFLARE_WORKER_URL_HERE`-এর জায়গায় deploy করা Worker-এর HTTPS base URL বসাও, `/explain` যোগ না করে। Commit/push করলে Pages update হবে।

Worker URL configure না করা থাকলে briefing site load হবে, কিন্তু word explanation কাজ করবে না—এটা Gemini generation/build error থেকে আলাদা।

## 5. Run locally

Python 3.11+ দরকার:

```bash
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
```

Workflow locally generator চালাতে হলে environment-এ `GEMINI_API_KEY` দিতে হবে। API key shell history-তে লিখে ফেলা এড়িয়ে চলো; local environment variable/secret manager ব্যবহার করো।

## 6. Fixes নিজের existing GitHub repository-তে পাঠানো

1. এই fixed package extract করো।
2. তোমার existing repository folder-এর backup রেখে fixed package-এর ফাইলগুলো copy করে overwrite করো; hidden `.github/workflows/daily.yml`-টিও include করো। `.git` folder overwrite/replace করার দরকার নেই। পুরোনো `__pycache__` folder থাকলে delete করো; আগে Git-এ tracked থাকলে `git rm -r --cached __pycache__` দিয়ে untrack করো।
3. Terminal-এ repository folder থেকে:

```bash
git status
git add .
git commit -m "Fix Gemini retries and Telegram workflow"
git push
```

4. GitHub → Actions → **Daily AI Agent → Run workflow** চালাও। `Generate daily briefing` step-এ এখন সফল হলে পরের step deploy করবে; Telegram credentials ভুল হলে শুধু `Send Telegram notifications` job-এ error হবে।

## Important accuracy note

arXiv/OpenAlex response থেকে paper metadata নেওয়া হয়; URL reachable হওয়া paper claims যাচাইয়ের সমান নয়। AI fact-review দ্বিতীয় model pass মাত্র, authoritative fact-check নয়। Important claims-এর জন্য source নিজে খুলে দেখো.


## Reliability hardening (2026-11-26)

- Invalid Gemini JSON objects receive one extra model request; invalid summaries/fact-review shape fail closed instead of silently publishing broken data.
- A fact marked `likely inaccurate` by the secondary review is **not published**. This can cause a daily run to fail rather than send a questionable briefing. This AI review is not authoritative fact verification.
- AI supplied URLs are never probed if they are IP literals, malformed, or outside a constrained set of reputable hosts; redirects are not followed. Source reachability is not proof of factual correctness.
- Telegram sends retry transient 429/5xx and network errors (up to 3 attempts), and malformed HTML is never silently truncated.
- A separate `alert-on-failure` job attempts to send a short Telegram failure message if build/deploy/notify fails. It cannot alert when GitHub itself never starts a scheduled run, or when Telegram credentials/network are unavailable.
- The previous `?date=` mini-app link was misleading because no archive exists; the link now opens the latest briefing. Historical content still needs a storage design.
- Pull requests get independent Python/Worker syntax checks and unit tests, without generating content or sending Telegram messages.

**Outstanding manual setup:** `web/config.js` still needs a deployed Cloudflare Worker HTTPS URL, and the Worker needs a properly configured origin allowlist and real rate limiting. GitHub Actions schedule starts are best-effort and can be hours late; this PR cannot guarantee 07:00 Bangladesh-time delivery. A reliable exact-time schedule needs an external scheduler/trigger and an idempotence strategy.


## Adhuri Telegram Inbox (2026-11-26) — Latest Behavior

This section supersedes the old "Tap any word" and Cloudflare vocabulary frontend notes above.

- Normal daily Telegram Business, Research, and Facts SMS messages **do not include any buttons**.
- Business SMS and website show **illustrative monthly ROI percentage**, calculated from the AI's stated monthly revenue/operating-expense assumptions divided by initial startup cost, not an audited return or success probability.
- The previous word-tap vocabulary widget and disconnected website chat panel have been removed. The bottom-right Adhuri icon on the site simply takes Telegram Mini App users back to their native bot inbox.
- In the Telegram bot's private chat, send an English word (e.g., `secure`), or `/word secure`. Adhuri responds in exactly this order: (1) বাংলা অর্থ, (2) Parts of Speech, (3) Grammatical Function, (4) বাস্তব জীবনে ব্যবহার, (5) বাক্যে ব্যবহার ও প্রসঙ্গ. Other questions get Bengali answers, not English-only paragraphs.
- The bot answers **only** the configured `TELEGRAM_CHAT_ID` private inbox and never records messages in the repository.
- For now, bot replies use GitHub Actions `.github/workflows/adhuri-inbox.yml`, checking for Telegram updates roughly every five minutes **when GitHub runs the scheduled job**. This is an available free-tier workaround, NOT an always-online, instant webhook. GitHub may delay or skip scheduled Actions; a live Worker webhook would be necessary for timely real-time chat.
- The polling job detects an existing Telegram webhook and refuses to disrupt it. `getUpdates` and webhooks cannot serve the same bot simultaneously.
- The Cloudflare Worker code remains in the repo as a future, faster alternative, but Cloudflare credentials are still missing. There is no need to expose the Gemini key to the browser.

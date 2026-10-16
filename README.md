# Free Daily AI Agent (Telegram + English vocabulary Mini App)

This starter project sends three separate Telegram messages every day at **07:00 Bangladesh time (UTC+6)**: one short business idea, one real arXiv research paper summary, and two interesting facts. Each message opens a small web app where you can tap words in the English content. Word explanations use the requested format: Bangla meaning, meaning in this sentence, one everyday example, grammar structure, and a transparent verification note.

## Important accuracy note
- Research-paper metadata and the paper URL are fetched from arXiv; the URL is checked for a successful response. This verifies the record/link, not the correctness of every AI interpretation.
- AI summaries and facts receive a second model review. That is a useful safeguard, not independent proof. Fact source URLs are shown when supplied, but the script does not automatically prove every source supports its claim. Open the source for important claims.
- Vocabulary explanations receive a second AI review, but are not checked against a licensed dictionary/authoritative grammar reference. The UI must label uncertainty rather than imply guaranteed correctness.
- Gemini API free-tier availability, quotas and model access can change. GitHub Actions has usage limits and scheduled workflows may be delayed. “Free” is subject to those services' current terms and quotas.

## Setup overview
You need a GitHub account, Telegram account, Google AI Studio API key, and a free Cloudflare account. Do not paste tokens or API keys into chat, source code, or public repositories.

### 1. Create your Telegram bot
1. In Telegram, open **@BotFather** and send `/newbot`.
2. Follow the prompts and copy the bot token privately.
3. Open your new bot and press **Start**.
4. Find your chat ID by opening `https://api.telegram.org/botYOUR_TOKEN/getUpdates` in a browser after sending `/start` to your bot. Replace `YOUR_TOKEN` locally; never share the URL or token. Find `message.chat.id` in the response.
5. In BotFather, use `/setdomain` and set the domain of your published GitHub Pages site once you know it (for example `yourname.github.io`). Mini App buttons need HTTPS and the domain configured.

### 2. Get a Gemini API key
1. Create an API key in Google AI Studio.
2. Check the current model access and free-tier limits for your account. Never commit the key.

### 3. Put this project in a GitHub repository
1. Create a new **public** repository if you want to use GitHub Pages on the free plan. Do not commit secrets.
2. Upload all project files while preserving `.github/workflows/daily.yml`.
3. In repository **Settings → Secrets and variables → Actions**, add these repository secrets:
   - `GEMINI_API_KEY` = your Google AI Studio key
   - `TELEGRAM_BOT_TOKEN` = your BotFather token
   - `TELEGRAM_CHAT_ID` = your Telegram chat ID
4. Go to **Settings → Pages** and set the publishing source to **GitHub Actions**.
5. Go to **Actions → Daily AI Agent → Run workflow** to test. If it fails, open the failed step logs; never print secrets into logs.
6. Your Pages URL is normally `https://OWNER.github.io/REPOSITORY/`. Use the actual URL from the successful deploy job.
7. Set the Mini App domain through BotFather `/setdomain` to the hostname, such as `OWNER.github.io`.

### 4. Deploy the vocabulary API securely (Cloudflare Worker)
The API key must stay on the server, not in `web/config.js`.
1. In Cloudflare Dashboard, open **Workers & Pages**, create a Worker, and paste the contents of `worker.js`.
2. In the Worker settings, add a secret named `GEMINI_API_KEY` with your AI Studio key.
3. Deploy the Worker and copy its HTTPS URL, e.g. `https://your-worker.your-subdomain.workers.dev`.
4. Edit `web/config.js`: replace `PASTE_YOUR_CLOUDFLARE_WORKER_URL_HERE` with the Worker URL, then commit the change to GitHub.
5. Run the GitHub Actions workflow again to publish the updated Mini App.

### 5. Test
- Send `/start` to your Telegram bot.
- Run the workflow manually from GitHub Actions.
- Check that three messages arrive and that the Mini App opens from the button.
- Tap words in the displayed English content and confirm that the meaning panel loads.
- Tap **Interested · show full plan** to reveal the longer business plan.

## Schedule
The workflow cron is `0 1 * * *`, which corresponds to 07:00 in Bangladesh (UTC+6). GitHub may delay scheduled runs during busy periods. Use **Run workflow** for immediate testing.

## Files
- `generate.py`: retrieves an arXiv record, asks AI for the daily idea/facts and creates the content JSON.
- `notify.py`: sends three separate Telegram messages.
- `web/index.html`: Mini App with tappable words and business-plan expansion.
- `web/config.js`: public Worker URL only; never put secrets here.
- `worker.js`: secure server-side vocabulary API with a second AI review.
- `.github/workflows/daily.yml`: scheduled generation, GitHub Pages deploy, Telegram delivery.

import os, json, requests
from pathlib import Path

TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
SITE_URL = os.environ['SITE_URL'].rstrip('/')
content = json.loads((Path(__file__).parent / 'site' / 'content.json').read_text(encoding='utf-8'))
api = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
miniapp_url = SITE_URL + '/?date=' + requests.utils.quote(content['date'])

business = content['business_idea']
paper = content['research_paper']
facts = content['facts']
messages = [
    ('💡 <b>Daily Business Idea</b>\n<b>' + business['title'] + '</b>\n\n' + business['overview'] + '\n\n<b>Target customer:</b> ' + business.get('target_customer','Not specified') + '\n<b>Revenue model:</b> ' + business.get('revenue_model','Not specified') + '\n\nWant the full plan? Open the briefing and tap <b>Interested</b>.'),
    ('🔬 <b>Research Paper of the Day</b>\n<b>' + paper['title'] + '</b>\n\n' + paper['summary'].get('overview','Summary unavailable') + '\n\n<b>Field:</b> ' + paper['summary'].get('field','CSE') + '\n<a href="' + paper['url'] + '">Open original paper on arXiv</a>'),
    ('✨ <b>Two Interesting Facts</b>\n\n<b>Daily life:</b> ' + facts[0]['claim'] + '\n' + facts[0]['explanation'] + '\n\n<b>Any topic:</b> ' + facts[1]['claim'] + '\n' + facts[1]['explanation'] + '\n\nTap <b>Open briefing</b> to explore vocabulary and sources.')
]
keyboard = {'inline_keyboard': [[{'text': '📖 Open briefing & tap any word', 'web_app': {'url': miniapp_url}}]]}
for msg in messages:
    r = requests.post(api, json={'chat_id': CHAT_ID, 'text': msg, 'parse_mode': 'HTML', 'disable_web_page_preview': True, 'reply_markup': keyboard}, timeout=30)
    r.raise_for_status()
    if not r.json().get('ok'):
        raise RuntimeError('Telegram API error: ' + r.text)
print('Sent 3 Telegram notifications.')

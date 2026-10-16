# Code review summary (Bangla)

## মূল সমস্যা
GitHub Actions error-এর `503 Service Unavailable` মানে Gemini সার্ভার request নিতে না পারা/সাময়িক overload। বর্তমান model ID `gemini-3.6-flash` বৈধ; শুধু নাম পাল্টালেই সবসময় সমাধান হবে না। পুরোনো code একই model-এ retry করত, তারপর কাজ থেমে যেত।

## যে পরিবর্তন করা হয়েছে
- Gemini primary/fallback model chain ও exponential backoff retry যোগ করা হয়েছে।
- Gemini 3.6+ request থেকে deprecated `temperature` parameter বাদ।
- API key request header-এ নেওয়া হয়েছে, URL query-তে নয়।
- arXiv ব্যর্থ হলে OpenAlex metadata fallback; research record মিথ্যা করে তৈরি নয়।
- JSON validation/error handling উন্নত।
- Telegram message-এ generated text HTML-escape, text length bounded, missing secrets/artifacts-এর জন্য পরিষ্কার error।
- Worker-এর পুরোনো model call-ও update, retry/fallback যোগ, optional origin allowlist যোগ।
- Mini App-এর `clickableText()` JavaScript syntax error ঠিক।
- `requirements.txt`, `.gitignore`, automated tests যোগ; Python bytecode ও `.git` archive-এ রাখা হয়নি।

## যাচাইয়ের ফল
- ৮টি Python unit tests সফল।
- Python syntax compilation সফল।
- Worker JavaScript syntax check সফল।
- Mini App inline JavaScript syntax check সফল।
- Live Gemini/Telegram API request চালানো হয়নি; তাই actual secret, model availability/quota, Telegram delivery বা GitHub Pages deployment আলাদাভাবে workflow চালিয়ে নিশ্চিত করতে হবে।

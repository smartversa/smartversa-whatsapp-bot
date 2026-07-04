# SmartVersa AI CRM — Tranche 1 (secure modular foundation)

Refactors the original single-file `app.py` into a clean, secure, modular Flask
app that deploys on Railway and **preserves the existing WhatsApp bot, Google
Sheets, and dashboard** while fixing the biggest issues.

## What changed vs. the original
- **Security (top priority):** dashboard/`send_manual` no longer use
  `password`-in-URL. Real session login with **hashed** credentials, **multiple
  admins**, logout, **CSRF** on POSTs, **login rate-limiting**, and optional
  **Meta webhook signature** verification.
- **Multilingual bot:** Hindi / English / Hinglish (menu + auto-detect).
- **Intent + FAQ engine:** price, fees, duration, syllabus, certificate,
  internship, refund, placement, timing, payment, prerequisites — answered at
  any step, with **lead scoring** (price +10, certificate +15, payment +40, …).
- **Restart anytime** (`menu` / `restart`) and **counsellor handoff**.
- **Optional AI counsellor** (`ai.py`): OpenAI **or** Anthropic over REST, no
  extra SDK. Off by default (`AI_PROVIDER=none`) — bot runs fully rule-based.
- **Human override:** admin can **pause AI** on a lead and take over, then resume.
- **CRM upgrades:** search + stage filter, lead score/priority, notes, analytics
  cards (total / today / hot / sales / revenue / conversion), **CSV export**.
- **Ops:** central config from env, structured logging, crash-safe handlers,
  **Sheets read caching** (fewer API calls), non-destructive header auto-add.
- Fixed `requirements.txt` — the original pinned `requests==2.34.0`, which does
  not exist on PyPI and would fail to install.

## File structure
```
app.py            Flask routes (webhook, login, dashboard, actions, export)
config.py         All settings from environment variables
logger.py         Logging + @safe crash-guard
sheets.py         Google Sheets layer (cache, header-ensure, CRUD)
whatsapp.py       WhatsApp Cloud API send + signature verify
knowledge.py      Course KB, FAQ, intent detection, scoring, language detect
ai.py             Optional AI counsellor (OpenAI/Anthropic via REST)
bot.py            Conversation engine (onboarding + FAQ + AI takeover)
auth.py           Session auth, hashing, CSRF, rate limit
crm.py            Lead listing, chat, analytics, export, AI pause/resume
templates/        login.html, dashboard.html
requirements.txt  Procfile  .env.example
```

## Deploy on Railway
1. Push these files to your repo (root of the service).
2. In Railway → **Variables**, set everything in `.env.example` (real values).
   - `SECRET_KEY`: long random string.
   - `ADMIN_CREDENTIALS`: e.g. `admin:StrongPass,anita:AnotherPass`.
   - `GOOGLE_CREDENTIALS_JSON`: full service-account JSON (one line).
   - Keep `VERIFY_TOKEN`, `PHONE_NUMBER_ID` as your live values (defaults match).
3. Railway uses the `Procfile` (gunicorn). Deploy.
4. Meta webhook: callback `https://<your-app>/webhook`, verify token =
   `VERIFY_TOKEN`. (Set `META_APP_SECRET` to enable signature checks.)
5. Follow-ups: schedule a daily hit to
   `https://<your-app>/followup?token=<VERIFY_TOKEN>` (Railway cron / any cron).

## Notes & migration
- The Sheets header row is auto-extended with the new columns (Lead Score, Tags,
  Priority, AI Paused, Last Contact, Followup3/4 Sent). Nothing is deleted.
- Sessions are in-memory (as in the original). For multi-worker persistence,
  Tranche 2 moves sessions + the AI counsellor's memory to a store (Redis/DB).

## Enable the AI counsellor (optional)
Set `AI_PROVIDER=openai` (or `anthropic`) and `AI_API_KEY=...`. After onboarding,
free-form messages are answered by the AI closer, grounded in the same KB; if the
API fails, it silently falls back to the FAQ engine.

## CONTINUE FROM: ai.py (Tranche 2)
Next build: AI admin assistant ("show hottest leads", "summarise this lead",
"suggest a reply"), AI accountant (revenue breakdowns), Razorpay webhook →
auto-mark Converted, sales-page tracking + abandoned-checkout recovery, richer
analytics charts, and Redis/DB-backed sessions + AI memory.

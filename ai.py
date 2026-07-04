"""
Optional AI Counsellor.

Provider-agnostic (OpenAI or Anthropic) over plain HTTPS using `requests`,
so no extra SDK is needed. If AI is not configured, `reply()` returns None and
the bot falls back to the rule-based + FAQ engine — the app runs fine either way.

Enable by setting:  AI_PROVIDER=openai|anthropic  and  AI_API_KEY=...
"""

import requests

from config import Config
from logger import log
from knowledge import COURSES

_DEFAULT_MODELS = {
    "openai": "gpt-4o-mini",
    "anthropic": "claude-sonnet-4-5",
}

SYSTEM_PROMPT = f"""You are the SmartVersa AI Counsellor — a warm, human-sounding
sales counsellor for an AI-education + internship company in India. You speak to
college students, freshers and career switchers over WhatsApp.

Style: short WhatsApp-length messages (1–4 sentences), friendly, never robotic.
Mirror the user's language: reply in Hindi, English, or Hinglish to match them.
Ask ONE question at a time. Build rapport, understand goals/budget, handle
objections (too expensive, no time, need parents' approval, trust, "later")
with empathy and honest value — never pushy or dishonest. Nudge toward enrolment
only when it genuinely fits the person.

Programs (be accurate, never invent features or discounts):
1) AI & Data Science — ₹{COURSES['1']['price']} — {COURSES['1']['level']}.
   Modules: {', '.join(COURSES['1']['modules'])}. Best for technical/analytics goals.
2) Digital Marketing — ₹{COURSES['2']['price']} — {COURSES['2']['level']}.
   Modules: {', '.join(COURSES['2']['modules'])}. Best for beginners/freelancing/business.

Both include real projects and an internship-style certificate (issued manually
with company stamp & signature). Enrolment link: {Config.PAYMENT_URL}

Rules: Do not promise guaranteed jobs or salaries. Do not invent refund terms —
offer to connect a human counsellor for refund/cancellation. If the user is angry,
confused, or explicitly asks for a human, suggest a counsellor handoff.
Keep replies concise and end with a gentle question or clear next step."""


def _build_messages(memory: dict, history: list, user_text: str):
    ctx_lines = []
    for k in ("name", "language", "college", "goal", "budget", "interest"):
        v = memory.get(k)
        if v:
            ctx_lines.append(f"{k}: {v}")
    context = ("Known about this lead — " + "; ".join(ctx_lines)) if ctx_lines else \
              "Nothing known about this lead yet."

    msgs = [{"role": "user", "content": context}]
    for turn in history[-10:]:
        role = "assistant" if turn.get("role") == "bot" else "user"
        msgs.append({"role": role, "content": turn.get("text", "")})
    msgs.append({"role": "user", "content": user_text})
    return msgs


def _call_openai(messages, model):
    url = "https://api.openai.com/v1/chat/completions"
    payload = {
        "model": model,
        "max_tokens": Config.AI_MAX_TOKENS,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + messages,
    }
    headers = {"Authorization": f"Bearer {Config.AI_API_KEY}",
               "Content-Type": "application/json"}
    r = requests.post(url, json=payload, headers=headers, timeout=Config.AI_TIMEOUT)
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"].strip()


def _call_anthropic(messages, model):
    url = "https://api.anthropic.com/v1/messages"
    payload = {
        "model": model,
        "max_tokens": Config.AI_MAX_TOKENS,
        "system": SYSTEM_PROMPT,
        "messages": messages,
    }
    headers = {
        "x-api-key": Config.AI_API_KEY,
        "anthropic-version": "2023-06-01",
        "Content-Type": "application/json",
    }
    r = requests.post(url, json=payload, headers=headers, timeout=Config.AI_TIMEOUT)
    r.raise_for_status()
    data = r.json()
    return "".join(b.get("text", "") for b in data.get("content", []) if b.get("type") == "text").strip()


def reply(memory: dict, history: list, user_text: str):
    """Return an AI reply string, or None if AI is disabled/unavailable."""
    if not Config.ai_enabled():
        return None
    model = Config.AI_MODEL or _DEFAULT_MODELS.get(Config.AI_PROVIDER)
    messages = _build_messages(memory or {}, history or [], user_text)
    try:
        if Config.AI_PROVIDER == "openai":
            return _call_openai(messages, model)
        if Config.AI_PROVIDER == "anthropic":
            return _call_anthropic(messages, model)
    except Exception:
        log.exception("AI counsellor call failed; falling back to rule-based")
        return None
    return None

"""
SmartVersa — central configuration.

All secrets and environment-specific values are loaded from environment
variables. Defaults are provided ONLY for non-secret values that must match
the currently-live Meta / bot configuration, so an existing deployment keeps
working after this refactor. Never hardcode tokens or passwords here.
"""

import os


def _get(key, default=None):
    val = os.getenv(key)
    return val if val not in (None, "") else default


def _get_bool(key, default=False):
    val = os.getenv(key)
    if val is None:
        return default
    return val.strip().lower() in ("1", "true", "yes", "on")


class Config:
    # ---- Flask ----
    # SECRET_KEY is REQUIRED in production (session signing). A random dev key
    # is generated if missing so local runs don't crash, but sessions won't
    # survive a restart in that case.
    SECRET_KEY = _get("SECRET_KEY") or os.urandom(32).hex()
    SECRET_KEY_FROM_ENV = bool(_get("SECRET_KEY"))
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    # Set to True on Railway (HTTPS). Toggle via env for local http testing.
    SESSION_COOKIE_SECURE = _get_bool("SESSION_COOKIE_SECURE", True)
    PERMANENT_SESSION_LIFETIME_HOURS = int(_get("SESSION_LIFETIME_HOURS", "12"))

    # ---- Admin auth ----
    # Preferred: ADMIN_CREDENTIALS = "user1:pass1,user2:pass2" (multiple admins)
    # Fallback (backward compat): ADMIN_PASSWORD -> user "admin"
    ADMIN_CREDENTIALS = _get("ADMIN_CREDENTIALS", "")
    ADMIN_PASSWORD = _get("ADMIN_PASSWORD", "")

    # ---- WhatsApp Cloud API (Meta) ----
    # Defaults match the previously-live values so the webhook keeps verifying.
    VERIFY_TOKEN = _get("VERIFY_TOKEN", "smartversa_bot_2026")
    WHATSAPP_TOKEN = _get("WHATSAPP_TOKEN")
    PHONE_NUMBER_ID = _get("PHONE_NUMBER_ID", "1207113965816609")
    WHATSAPP_API_VERSION = _get("WHATSAPP_API_VERSION", "v23.0")
    # Optional: Meta app secret enables X-Hub-Signature-256 verification.
    META_APP_SECRET = _get("META_APP_SECRET")

    # ---- Google Sheets ----
    GOOGLE_CREDENTIALS_JSON = _get("GOOGLE_CREDENTIALS_JSON")
    GOOGLE_SHEET_NAME = _get("GOOGLE_SHEET_NAME")
    LEADS_WORKSHEET = _get("LEADS_WORKSHEET", "Sheet1")   # sheet1 in old code
    MESSAGES_WORKSHEET = _get("MESSAGES_WORKSHEET", "Messages")
    SHEETS_CACHE_TTL = int(_get("SHEETS_CACHE_TTL", "20"))  # seconds
    # Auto-add any missing header columns (non-destructive; never removes).
    ENSURE_HEADERS = _get_bool("ENSURE_HEADERS", True)

    # ---- Business ----
    COMPANY = "SmartVersa"
    WEBSITE_URL = _get("WEBSITE_URL", "https://smartversa.in")
    PAYMENT_URL = _get("PAYMENT_URL", "https://pay.smartversa.in/orderform")
    AI_IMAGE_URL = _get(
        "AI_IMAGE_URL",
        "https://images.unsplash.com/photo-1551288049-bebda4e38f71",
    )
    DM_IMAGE_URL = _get(
        "DM_IMAGE_URL",
        "https://images.unsplash.com/photo-1552664730-d307ca884978",
    )

    # ---- AI Counsellor (optional) ----
    # Provider: "openai" | "anthropic" | "none". When "none" or no key is set,
    # the bot runs fully on the rule-based + FAQ engine (zero AI cost).
    AI_PROVIDER = _get("AI_PROVIDER", "none").strip().lower()
    AI_API_KEY = _get("AI_API_KEY")
    AI_MODEL = _get("AI_MODEL")  # sensible default chosen per-provider in ai.py
    AI_MAX_TOKENS = int(_get("AI_MAX_TOKENS", "600"))
    AI_TIMEOUT = int(_get("AI_TIMEOUT", "30"))

    # ---- Ops ----
    LOG_LEVEL = _get("LOG_LEVEL", "INFO")
    RATE_LIMIT_LOGIN = int(_get("RATE_LIMIT_LOGIN", "8"))       # attempts / window
    RATE_LIMIT_WINDOW = int(_get("RATE_LIMIT_WINDOW", "300"))   # seconds

    @classmethod
    def ai_enabled(cls):
        return cls.AI_PROVIDER in ("openai", "anthropic") and bool(cls.AI_API_KEY)

    @classmethod
    def validate(cls):
        """Return a list of fatal misconfiguration messages (empty = OK)."""
        problems = []
        if not cls.GOOGLE_CREDENTIALS_JSON:
            problems.append("GOOGLE_CREDENTIALS_JSON is not set")
        if not cls.GOOGLE_SHEET_NAME:
            problems.append("GOOGLE_SHEET_NAME is not set")
        if not cls.WHATSAPP_TOKEN:
            problems.append("WHATSAPP_TOKEN is not set (outbound messages will fail)")
        if not cls.ADMIN_CREDENTIALS and not cls.ADMIN_PASSWORD:
            problems.append("No admin login configured (set ADMIN_CREDENTIALS)")
        return problems

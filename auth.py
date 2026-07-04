"""
Secure admin authentication — replaces password-in-URL.

- Credentials from env (ADMIN_CREDENTIALS="user1:pass1,user2:pass2"), hashed in
  memory at startup. Falls back to ADMIN_PASSWORD (user "admin") for compat.
- Server-side Flask sessions (signed cookies), logout, multi-admin.
- Per-form CSRF tokens for state-changing POSTs.
- Simple in-memory rate limiting on login attempts.
"""

import time
import secrets
import functools

from flask import session, redirect, request, abort
from werkzeug.security import generate_password_hash, check_password_hash

from config import Config
from logger import log

# username -> password hash
_ADMINS = {}


def _load_admins():
    if Config.ADMIN_CREDENTIALS:
        for pair in Config.ADMIN_CREDENTIALS.split(","):
            pair = pair.strip()
            if not pair or ":" not in pair:
                continue
            user, pwd = pair.split(":", 1)
            _ADMINS[user.strip()] = generate_password_hash(pwd.strip())
    if not _ADMINS and Config.ADMIN_PASSWORD:
        _ADMINS["admin"] = generate_password_hash(Config.ADMIN_PASSWORD)
    if not _ADMINS:
        log.warning("No admin credentials configured — dashboard login disabled.")
    else:
        log.info("Loaded %d admin account(s).", len(_ADMINS))


_load_admins()

# ---- Rate limiting (per client IP) ----
_attempts = {}  # ip -> [timestamps]


def _client_ip():
    fwd = request.headers.get("X-Forwarded-For", "")
    return fwd.split(",")[0].strip() if fwd else (request.remote_addr or "unknown")


def rate_limited() -> bool:
    ip = _client_ip()
    now = time.time()
    window = Config.RATE_LIMIT_WINDOW
    hits = [t for t in _attempts.get(ip, []) if now - t < window]
    _attempts[ip] = hits
    return len(hits) >= Config.RATE_LIMIT_LOGIN


def _record_attempt():
    _attempts.setdefault(_client_ip(), []).append(time.time())


def authenticate(username: str, password: str) -> bool:
    _record_attempt()
    h = _ADMINS.get((username or "").strip())
    if h and check_password_hash(h, password or ""):
        session.permanent = True
        session["user"] = username.strip()
        session["csrf"] = secrets.token_hex(16)
        log.info("Admin '%s' logged in from %s", username, _client_ip())
        return True
    log.warning("Failed login for '%s' from %s", username, _client_ip())
    return False


def logout():
    session.clear()


def current_user():
    return session.get("user")


def is_authenticated() -> bool:
    return bool(session.get("user"))


def csrf_token() -> str:
    if "csrf" not in session:
        session["csrf"] = secrets.token_hex(16)
    return session["csrf"]


def verify_csrf(token: str) -> bool:
    good = session.get("csrf")
    return bool(good) and secrets.compare_digest(good, token or "")


def login_required(view):
    @functools.wraps(view)
    def wrapper(*args, **kwargs):
        if not is_authenticated():
            return redirect("/login")
        return view(*args, **kwargs)
    return wrapper


def csrf_protect():
    """Call inside POST handlers to reject requests with a bad/missing token."""
    token = request.form.get("csrf_token", "")
    if not verify_csrf(token):
        abort(403)

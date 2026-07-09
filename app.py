"""
SmartVersa — Flask application entry point.

Routes:
  GET  /                 health/status
  GET  /login            login form
  POST /login            authenticate
  GET  /logout           end session
  GET|POST /webhook      WhatsApp Cloud API webhook
  GET  /followup         run follow-up cadence (protect with ?token=VERIFY_TOKEN)
  GET  /dashboard        CRM dashboard (login required)
  POST /send_manual      send a manual WhatsApp message (login required + CSRF)
  POST /lead_action      stage / note / AI pause-resume (login required + CSRF)
  GET  /export           download leads CSV (login required)
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from flask import (
    Flask, request, redirect, render_template, session, Response, abort
)

from config import Config
from logger import log
import auth
import crm
import bot
import whatsapp
import sheets

app = Flask(__name__)
app.config.update(
    SECRET_KEY=Config.SECRET_KEY,
    SESSION_COOKIE_HTTPONLY=Config.SESSION_COOKIE_HTTPONLY,
    SESSION_COOKIE_SAMESITE=Config.SESSION_COOKIE_SAMESITE,
    SESSION_COOKIE_SECURE=Config.SESSION_COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(hours=Config.PERMANENT_SESSION_LIFETIME_HOURS),
)

for problem in Config.validate():
    log.warning("CONFIG: %s", problem)
if not Config.SECRET_KEY_FROM_ENV:
    log.warning("SECRET_KEY not set from env — using a random key (sessions reset on restart).")


# --------------------------------------------------------------------------- #
# Timezone helpers — all "now" values used for follow-up scheduling are
# anchored to Asia/Kolkata, since that's the timezone the leads themselves
# are logged in (sheets.py / bot.py write DD-MM-YYYY HH:MM local timestamps).
# --------------------------------------------------------------------------- #
IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Current time in IST, tz-aware."""
    return datetime.now(IST)


def _parse_sheet_dt(date_str, time_str):
    """Parse a 'DD-MM-YYYY' + 'HH:MM' pair (as written by sheets.py/bot.py)
    into a tz-aware IST datetime. Returns None if unparseable/blank."""
    if not date_str or not time_str:
        return None
    try:
        naive = datetime.strptime(f"{date_str} {time_str}", "%d-%m-%Y %H:%M")
        return naive.replace(tzinfo=IST)
    except (ValueError, TypeError):
        return None


# --------------------------------------------------------------------------- #
@app.route("/")
def home():
    return "SmartVersa AI CRM is running."


# ---- Auth ----
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        if auth.rate_limited():
            return render_template("login.html", error="Too many attempts. Try again shortly."), 429
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if auth.authenticate(username, password):
            return redirect("/dashboard")
        return render_template("login.html", error="Invalid username or password."), 401
    if auth.is_authenticated():
        return redirect("/dashboard")
    return render_template("login.html", error=None)


@app.route("/logout")
def logout():
    auth.logout()
    return redirect("/login")


# ---- WhatsApp webhook ----
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")
        if mode == "subscribe" and token == Config.VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403

    raw = request.get_data()
    try:
        signature_ok = whatsapp.verify_signature(
            raw, request.headers.get("X-Hub-Signature-256", "")
        )
    except Exception:
        log.exception("Webhook: signature verification raised an exception")
        return "Forbidden", 403

    if not signature_ok:
        log.warning("Rejected webhook: bad signature")
        return "Forbidden", 403

    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        log.warning("Webhook: request body is missing or not valid JSON")
        return "OK", 200

    try:
        entries = data.get("entry") or []
        if not entries:
            return "OK", 200
        changes = entries[0].get("changes") or []
        if not changes:
            return "OK", 200
        value = changes[0].get("value") or {}

        messages = value.get("messages") or []
        if not messages:
            # Status callbacks (sent/delivered/read) land here too — not an error.
            return "OK", 200

        msg = messages[0]
        phone = msg.get("from")
        if not phone:
            log.warning("Webhook: message missing sender phone number")
            return "OK", 200

        wa_name = ""
        contacts = value.get("contacts") or []
        if contacts:
            wa_name = (contacts[0].get("profile") or {}).get("name", "")

        if "text" not in msg:
            # Non-text messages (image/audio/etc.) aren't handled by the bot yet.
            return "OK", 200

        text = (msg.get("text") or {}).get("body", "").strip()
        if not text:
            return "OK", 200

        # Always persist the incoming message for the dashboard.
        try:
            sheets.append_message(phone, "User", text)
        except Exception:
            log.exception("Webhook: failed to log incoming message for %s", phone)

        # Human override: if an admin paused AI for this lead, don't auto-reply.
        if crm.is_ai_paused(phone):
            log.info("AI paused for %s — message logged, no auto-reply.", phone)
            return "OK", 200

        bot.handle(phone, text, wa_name)
    except Exception:
        log.exception("Webhook processing error")

    return "OK", 200


# ---- Follow-up cadence ----
@app.route("/followup")
def followup():
    # Protect the endpoint: require the Meta verify token as a shared secret,
    # OR an authenticated admin session.
    token = request.args.get("token", "")
    if token != Config.VERIFY_TOKEN and not auth.is_authenticated():
        return "Forbidden", 403
    sent = run_followups()
    return f"Follow-up completed. Messages sent: {sent}"


# Hours since lead creation at which each follow-up fires.
_CADENCE = [
    (24, "Followup1 Sent", "_fu_soft"),
    (72, "Followup2 Sent", "_fu_urgency"),
    (168, "Followup3 Sent", "_fu_final"),
    (360, "Followup4 Sent", "_fu_reactivate"),
]

# Don't message a lead that has been in touch (either direction) more
# recently than this — they're actively engaged, a follow-up would be noise
# or a duplicate/interruption. Configurable via Config if present.
_ACTIVE_CHAT_WINDOW_HOURS = getattr(Config, "FOLLOWUP_ACTIVE_CHAT_WINDOW_HOURS", 1)

_SKIP_STAGES = ("Converted", "Not Interested")


def run_followups():
    try:
        rows = sheets.get_leads(use_cache=False)
    except Exception:
        log.exception("Follow-up: could not read leads")
        return 0

    now = now_ist()
    sent = 0
    for row in rows:
        try:
            if _should_skip_row(row, now):
                continue

            phone = row.get("Phone")
            if not phone:
                continue
            name = row.get("Name", "there")

            lead_dt = _parse_sheet_dt(row.get("Date", ""), row.get("Time", ""))
            if lead_dt is None:
                continue
            hours_since_created = (now - lead_dt).total_seconds() / 3600

            for min_hours, flag, builder_name in _CADENCE:
                if hours_since_created < min_hours:
                    continue
                if str(row.get(flag, "")).strip() == "Yes":
                    continue
                builder = globals()[builder_name]
                whatsapp.send_message(phone, builder(name))
                sheets.update_lead(phone, {flag: "Yes"})
                sent += 1
                break
        except Exception:
            log.exception("Follow-up row error for %s", row.get("Phone", "<unknown>"))
    return sent


def _should_skip_row(row, now):
    """True if this lead should not receive a follow-up right now."""
    stage = str(row.get("Stage", "")).strip()
    if stage in _SKIP_STAGES:
        return True
    if str(row.get("Payment Status", "")).strip().lower() == "paid":
        return True

    # Never interrupt an active conversation: if the lead has been in
    # contact (bot or admin) within the active-chat window, skip this run —
    # the cadence will re-check on the next /followup run.
    last_contact = _parse_sheet_dt(*_split_last_contact(row.get("Last Contact", "")))
    if last_contact is not None:
        idle_hours = (now - last_contact).total_seconds() / 3600
        if idle_hours < _ACTIVE_CHAT_WINDOW_HOURS:
            return True

    return False


def _split_last_contact(value):
    """'Last Contact' is stored as a single 'DD-MM-YYYY HH:MM' string;
    split it into (date, time) parts for _parse_sheet_dt."""
    value = str(value or "").strip()
    if not value or " " not in value:
        return "", ""
    date_part, _, time_part = value.partition(" ")
    return date_part, time_part


def _fu_soft(name):
    return f"Hi {name} 👋 Need any help with your SmartVersa enrollment? I'm here 😊"


def _fu_urgency(name):
    return (f"{name}, seats for our upcoming batch are filling fast ⏳\n"
            f"Enroll here: {Config.PAYMENT_URL}")


def _fu_final(name):
    return (f"Final reminder, {name} 😊 Don't miss your internship-style program.\n"
            f"Enroll: {Config.PAYMENT_URL}")


def _fu_reactivate(name):
    return (f"Hey {name}! Still thinking about upskilling? "
            f"Reply *menu* and I'll help you pick the right program.")


# ---- Dashboard ----
@app.route("/dashboard")
@auth.login_required
def dashboard():
    search = request.args.get("search", "").strip()
    stage = request.args.get("stage", "").strip()
    selected = request.args.get("phone", "").strip()

    leads = crm.list_leads(search=search, stage=stage)
    chat = crm.get_chat(selected) if selected else []
    lead = crm.get_lead(selected) if selected else None
    stats = crm.analytics()

    return render_template(
        "dashboard.html",
        user=auth.current_user(),
        leads=leads,
        chat=chat,
        lead=lead,
        selected=selected,
        search=search,
        stage_filter=stage,
        stages=crm.STAGES,
        stats=stats,
        payment_url=Config.PAYMENT_URL,
        csrf_token=auth.csrf_token(),
    )


@app.route("/send_manual", methods=["POST"])
@auth.login_required
def send_manual():
    auth.csrf_protect()
    phone = request.form.get("phone", "").strip()
    msg = request.form.get("msg", "").strip()
    if not phone or not msg:
        return redirect("/dashboard")
    whatsapp.send_message(phone, msg, sender="Admin")
    return redirect(f"/dashboard?phone={phone}")


@app.route("/lead_action", methods=["POST"])
@auth.login_required
def lead_action():
    auth.csrf_protect()
    phone = request.form.get("phone", "").strip()
    action = request.form.get("action", "")
    if not phone:
        return redirect("/dashboard")

    if action == "set_stage":
        crm.set_stage(phone, request.form.get("stage", ""))
    elif action == "add_note":
        note = request.form.get("note", "").strip()
        if note:
            crm.add_note(phone, note)
    elif action == "pause_ai":
        crm.set_ai_paused(phone, True)
    elif action == "resume_ai":
        crm.set_ai_paused(phone, False)

    return redirect(f"/dashboard?phone={phone}")


@app.route("/export")
@auth.login_required
def export():
    data = crm.export_csv()
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=smartversa_leads.csv"},
    )


if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

"""
SmartVersa — Flask application entry point.

Routes:
  GET  /                 health/status
  GET  /login            login form
  POST /login            authenticate
  GET  /logout           end session
  GET|POST /webhook      WhatsApp Cloud API webhook
  GET  /followup         run follow-up cadence (protect with ?token=VERIFY_TOKEN)
  GET  /dashboard        CRM admin control panel (login required) — Dashboard,
                         Leads, Messages, AI Training, New Message, Analytics
                         and Settings all live as tabs on this one route/page
                         (see templates/dashboard.html), so no existing URL
                         changes and no new pages are introduced.
  POST /send_manual      send a manual WhatsApp message (login required + CSRF)
                         — also powers the "New Message" tab; the phone
                         number does not need to belong to an existing lead.
  POST /lead_action      stage / note / AI pause-resume (login required + CSRF)
  POST /faq_action       AI Training panel: add / edit / delete / enable /
                         disable an FAQ entry (login required + CSRF)
  GET  /export           download leads CSV (login required)

  --- Phase 6 — Google Sheets Manager (see the "Google Sheets" dashboard
      tab; every route below is login-required, and every mutating one is
      CSRF-protected the same way as the routes above) ---
  GET  /api/sheets                          list every worksheet by name
  GET  /api/sheets/<name>                   paginated/searched/sorted rows
  POST /api/sheets/<name>/cell              edit one cell
  POST /api/sheets/<name>/row               add a row
  POST /api/sheets/<name>/row/<row>/duplicate
  POST /api/sheets/<name>/row/<row>/delete
  GET  /api/sheets/<name>/export.csv
  GET  /api/sheets/<name>/export.xlsx
  POST /api/sheets/leads/import             import a CSV into Leads
"""

import json
from datetime import timedelta
from urllib.parse import urlencode

from flask import (
    Flask, request, redirect, render_template, session, Response, abort, jsonify
)

from config import Config
from logger import log
import auth
import crm
import bot
import whatsapp
import sheets
from sheets import now_ist, parse_ist_dt  # single shared IST "now"/parser — see sheets.py

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
# Timezone helpers — all "now"/parsing values used for follow-up scheduling
# are anchored to Asia/Kolkata (the timezone leads are logged in), via the
# single shared implementation in sheets.py rather than a local copy here.
# --------------------------------------------------------------------------- #
_parse_sheet_dt = parse_ist_dt


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

        # Always persist the incoming message for the dashboard. This also
        # bumps Last Contact (sheets.append_message is the single choke
        # point for that — see sheets.py).
        try:
            sheets.append_message(phone, "User", text)
        except Exception:
            log.exception("Webhook: failed to log incoming message for %s", phone)

        # Behavioural scoring/tagging (fees, placement, payment intent,
        # etc.) — never duplicates points for a repeated intent, and never
        # blocks the reply if it fails.
        try:
            crm.track_intent(phone, text)
        except Exception:
            log.exception("Webhook: failed to track intent for %s", phone)

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
                message_text = builder(name)
                whatsapp.send_message(phone, message_text)
                # Logging also bumps Last Contact — keep the flag update
                # separate so it never gets clobbered by that write.
                try:
                    sheets.append_message(phone, "Bot", message_text)
                except Exception:
                    log.exception("Follow-up: failed to log outgoing message for %s", phone)
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


# ---- Small helper: build a redirect URL carrying a toast message ----
def _toast_redirect(path, params=None, message="", kind="success"):
    params = dict(params or {})
    if message:
        params["toast"] = message
        params["toast_type"] = kind
    qs = urlencode(params)
    return redirect(f"{path}?{qs}" if qs else path)


# ---- Dashboard (single-page Admin Control Panel — all tabs, one route) ----
@app.route("/dashboard")
@auth.login_required
def dashboard():
    # ---- Leads tab ----
    search = request.args.get("search", "").strip()
    stage = request.args.get("stage", "").strip()
    selected = request.args.get("phone", "").strip()
    active_tab = request.args.get("tab", "overview").strip() or "overview"

    leads = crm.list_leads(search=search, stage=stage)

    # Global search (Feature 5): also surface leads that only match on
    # message content, not on the lead-record fields crm.list_leads already
    # searches (Name/Phone/Email/Course Interest/Stage/Tags).
    if search:
        have = {str(l.get("Phone", "")).strip() for l in leads}
        for phone in crm.global_search_phones(search):
            if phone in have:
                continue
            extra = crm.get_lead(phone)
            if extra:
                row = dict(extra)
                row["_unread"] = False
                leads.append(row)
                have.add(phone)

    chat = crm.get_chat(selected) if selected else []
    lead = crm.get_lead(selected) if selected else None
    stats = crm.analytics()

    # ---- Messages Center tab ----
    msearch = request.args.get("msearch", "").strip()
    mdate = request.args.get("mdate", "").strip()
    msender = request.args.get("msender", "").strip()
    conversations = crm.list_conversations(search=msearch, date_filter=mdate, sender_filter=msender)

    # ---- AI Training tab ----
    fsearch = request.args.get("fsearch", "").strip()
    fcategory = request.args.get("fcategory", "").strip()
    fstatus = request.args.get("fstatus", "").strip()
    faqs = crm.list_faqs(search=fsearch, category=fcategory, status=fstatus)
    faq_categories = crm.faq_categories()
    edit_faq = crm.get_faq(request.args.get("faq_id", "").strip()) if request.args.get("faq_id") else None

    # ---- Analytics tab ----
    followup_stats = crm.followup_breakdown()

    # ---- Google Sheets Manager tab (Phase 6) ----
    # Just the sheet list + which one is selected — the grid itself (rows,
    # search, sort, pagination) is fetched client-side via /api/sheets/...
    # so switching sheets/searching/sorting never triggers a full page
    # reload (Feature 2/3/8).
    sheet_names = crm.list_sheet_names()
    selected_sheet = request.args.get("sheet", "").strip() or (sheet_names[0] if sheet_names else "")

    # ---- Toast (post-redirect flash, no server-side session needed) ----
    toast = request.args.get("toast", "").strip()
    toast_type = request.args.get("toast_type", "success").strip()

    return render_template(
        "dashboard.html",
        user=auth.current_user(),
        active_tab=active_tab,
        # Leads
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
        # Messages Center
        conversations=conversations,
        msearch=msearch,
        mdate=mdate,
        msender=msender,
        # AI Training
        faqs=faqs,
        faq_categories=faq_categories,
        faq_search=fsearch,
        faq_category_filter=fcategory,
        faq_status_filter=fstatus,
        edit_faq=edit_faq,
        # Analytics
        followup_stats=followup_stats,
        # Google Sheets Manager
        sheet_names=sheet_names,
        selected_sheet=selected_sheet,
        leads_sheet_name=Config.LEADS_WORKSHEET,
        messages_sheet_name=Config.MESSAGES_WORKSHEET,
        # Toast
        toast=toast,
        toast_type=toast_type,
    )


@app.route("/send_manual", methods=["POST"])
@auth.login_required
def send_manual():
    auth.csrf_protect()
    phone = request.form.get("phone", "").strip()
    msg = request.form.get("msg", "").strip()
    name = request.form.get("name", "").strip()
    # Posted explicitly by whichever tab's send form this came from (Leads
    # chat box, Messages Center chat box, or the New Message form), so the
    # redirect lands back on the right tab. Defaults to "leads" for safety.
    tab = request.form.get("tab", "leads").strip() or "leads"

    # The phone number does not need to belong to an existing lead — this is
    # what powers the "New Message" tab. append_message/update_lead below
    # already handle an unknown phone gracefully (the Last Contact update is
    # a silent no-op with no matching lead row); the conversation simply
    # appears in Messages Center, and if that number later messages in via
    # the webhook, bot.py picks the conversation up normally since it's
    # keyed on the same phone.
    if not phone or not msg:
        return _toast_redirect("/dashboard", {"tab": tab}, "Phone and message are both required.", "error")

    # New Contact (Feature 7): the "New Message" tab optionally takes a name.
    # If this phone has no lead yet, create one before sending so the
    # conversation immediately shows up as a real lead (Analytics, Leads
    # tab, Google Sheets Manager) rather than an orphaned message thread.
    if tab == "newmsg":
        try:
            crm.ensure_lead(phone, name)
        except Exception:
            log.exception("send_manual: failed to ensure lead exists for %s", phone)

    try:
        whatsapp.send_message(phone, msg, sender="Admin")
    except Exception:
        log.exception("send_manual: failed to send WhatsApp message to %s", phone)
        return _toast_redirect("/dashboard", {"tab": tab}, "Failed to send message — please try again.", "error")

    # Log it so conversation history stays complete and Last Contact
    # reflects this outgoing message too.
    try:
        sheets.append_message(phone, "Admin", msg)
    except Exception:
        log.exception("send_manual: failed to log outgoing admin message for %s", phone)

    return _toast_redirect("/dashboard", {"phone": phone, "tab": tab}, "Message sent.", "success")


@app.route("/lead_action", methods=["POST"])
@auth.login_required
def lead_action():
    auth.csrf_protect()
    phone = request.form.get("phone", "").strip()
    action = request.form.get("action", "")
    if not phone:
        return redirect("/dashboard?tab=leads")

    ok = True
    if action == "set_stage":
        ok = crm.set_stage(phone, request.form.get("stage", ""))
    elif action == "add_note":
        note = request.form.get("note", "").strip()
        ok = crm.add_note(phone, note) if note else False
    elif action == "pause_ai":
        ok = crm.set_ai_paused(phone, True)
    elif action == "resume_ai":
        ok = crm.set_ai_paused(phone, False)
    elif action == "mark_paid":
        ok = crm.set_payment_status(phone, "Paid")
    elif action == "delete_lead":
        # Lead Quick Action: Delete Lead (Feature 5). The confirmation
        # dialog happens client-side before this request is ever sent.
        ok = crm.delete_lead(phone)
        if ok:
            return _toast_redirect("/dashboard", {"tab": "leads"}, "Lead deleted.", "success")

    msg = "Updated." if ok else "That didn't go through — please try again."
    return _toast_redirect("/dashboard", {"phone": phone, "tab": "leads"}, msg, "success" if ok else "error")


# ---- AI Training panel ----
@app.route("/faq_action", methods=["POST"])
@auth.login_required
def faq_action():
    auth.csrf_protect()
    action = request.form.get("action", "")
    faq_id = request.form.get("faq_id", "").strip()

    def field(name, default=""):
        return request.form.get(name, default).strip()

    ok = False
    msg = "Something went wrong — please try again."

    if action == "add":
        new_id = crm.add_faq(
            question=field("question"),
            answer=field("answer"),
            category=field("category"),
            keywords=field("keywords"),
            language=field("language", "English") or "English",
            status=field("status", "Active") or "Active",
        )
        ok = bool(new_id)
        msg = "FAQ added." if ok else "Question and answer are both required."
    elif action == "edit" and faq_id:
        ok = crm.update_faq(faq_id, {
            "Question": field("question"),
            "Answer": field("answer"),
            "Category": field("category"),
            "Keywords": field("keywords"),
            "Language": field("language"),
        })
        msg = "FAQ updated." if ok else "Couldn't update that FAQ."
    elif action == "delete" and faq_id:
        ok = crm.delete_faq(faq_id)
        msg = "FAQ deleted." if ok else "Couldn't delete that FAQ."
    elif action == "enable" and faq_id:
        ok = crm.set_faq_status(faq_id, "Active")
        msg = "FAQ enabled." if ok else "Couldn't enable that FAQ."
    elif action == "disable" and faq_id:
        ok = crm.set_faq_status(faq_id, "Inactive")
        msg = "FAQ disabled." if ok else "Couldn't disable that FAQ."

    return _toast_redirect("/dashboard", {"tab": "training"}, msg, "success" if ok else "error")


# --------------------------------------------------------------------------- #
# Google Sheets Manager — JSON API (Phase 6)
#
# Generic view/search/sort/filter/paginate/edit over EVERY worksheet in the
# spreadsheet, driven entirely by sheets.list_worksheet_titles() — no sheet
# names hardcoded. Leads/Messages/FAQs keep working through their existing
# dedicated routes above completely unchanged; this is additive and powers
# only the new "Google Sheets" dashboard tab.
# --------------------------------------------------------------------------- #
def _known_sheet(name):
    return name in sheets.list_worksheet_titles()


@app.route("/api/sheets")
@auth.login_required
def api_sheets_list():
    return jsonify({"sheets": sheets.list_worksheet_titles(use_cache=False)})


@app.route("/api/sheets/<name>")
@auth.login_required
def api_sheet_view(name):
    if not _known_sheet(name):
        return jsonify({"error": "Unknown worksheet."}), 404

    filters = {}
    raw_filters = request.args.get("filters", "")
    if raw_filters:
        try:
            parsed = json.loads(raw_filters)
            if isinstance(parsed, dict):
                filters = {str(k): str(v) for k, v in parsed.items()}
        except (ValueError, TypeError):
            pass

    data = crm.sheet_view(
        name,
        search=request.args.get("search", ""),
        sort_col=request.args.get("sort", ""),
        sort_dir=request.args.get("dir", "asc"),
        page=request.args.get("page", 1),
        per_page=request.args.get("per_page", crm.SHEET_PAGE_SIZE_DEFAULT),
        filters=filters,
        use_cache=request.args.get("fresh", "") != "1",
    )
    return jsonify(data)


@app.route("/api/sheets/<name>/cell", methods=["POST"])
@auth.login_required
def api_sheet_cell(name):
    auth.csrf_protect()
    if not _known_sheet(name):
        return jsonify({"ok": False, "error": "Unknown worksheet."}), 404
    ok = crm.sheet_cell_update(
        name,
        request.form.get("row", ""),
        request.form.get("header", ""),
        request.form.get("value", ""),
    )
    return jsonify({"ok": ok})


@app.route("/api/sheets/<name>/row", methods=["POST"])
@auth.login_required
def api_sheet_row_add(name):
    auth.csrf_protect()
    if not _known_sheet(name):
        return jsonify({"ok": False, "error": "Unknown worksheet."}), 404
    values = {k: v for k, v in request.form.items() if k != "csrf_token"}
    ok = crm.sheet_row_add(name, values)
    return jsonify({"ok": ok})


@app.route("/api/sheets/<name>/row/<int:row>/duplicate", methods=["POST"])
@auth.login_required
def api_sheet_row_duplicate(name, row):
    auth.csrf_protect()
    if not _known_sheet(name):
        return jsonify({"ok": False, "error": "Unknown worksheet."}), 404
    return jsonify({"ok": crm.sheet_row_duplicate(name, row)})


@app.route("/api/sheets/<name>/row/<int:row>/delete", methods=["POST"])
@auth.login_required
def api_sheet_row_delete(name, row):
    auth.csrf_protect()
    if not _known_sheet(name):
        return jsonify({"ok": False, "error": "Unknown worksheet."}), 404
    return jsonify({"ok": crm.sheet_row_delete(name, row)})


@app.route("/api/sheets/<name>/export.csv")
@auth.login_required
def api_sheet_export_csv(name):
    if not _known_sheet(name):
        abort(404)
    data = crm.sheet_export_csv(name)
    fname = f"{name.strip().lower().replace(' ', '_')}.csv"
    return Response(
        data, mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.route("/api/sheets/<name>/export.xlsx")
@auth.login_required
def api_sheet_export_xlsx(name):
    if not _known_sheet(name):
        abort(404)
    data = crm.sheet_export_xlsx(name)
    if data is None:
        return _toast_redirect(
            "/dashboard", {"tab": "sheets", "sheet": name},
            "Excel export needs the 'openpyxl' package on the server "
            "(add it to requirements.txt) — CSV export works either way.",
            "error",
        )
    fname = f"{name.strip().lower().replace(' ', '_')}.xlsx"
    return Response(
        data,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


@app.route("/api/sheets/leads/import", methods=["POST"])
@auth.login_required
def api_leads_import():
    auth.csrf_protect()
    f = request.files.get("file")
    if not f or not f.filename:
        return _toast_redirect(
            "/dashboard", {"tab": "sheets", "sheet": Config.LEADS_WORKSHEET},
            "Choose a CSV file first.", "error",
        )
    added, updated, errors = crm.import_leads_csv(f.stream)
    msg = f"Import complete — {added} added, {updated} updated."
    if errors:
        msg += f" {len(errors)} row(s) skipped (see logs)."
        for e in errors[:20]:
            log.warning("Leads CSV import: %s", e)
    kind = "success" if (added or updated) else "error"
    return _toast_redirect("/dashboard", {"tab": "sheets", "sheet": Config.LEADS_WORKSHEET}, msg, kind)


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

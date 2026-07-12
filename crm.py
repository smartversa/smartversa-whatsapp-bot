"""CRM data layer — powers the dashboard, analytics, export, and AI override."""

import io
import csv
from datetime import datetime

import sheets
from sheets import now_ist  # single shared IST "now" — see sheets.py
from logger import log, safe

STAGES = [
    "New Lead", "Contacted", "Warm Lead", "Hot Lead",
    "Payment Sent", "Converted", "Not Interested", "Ghosted",
]

# AI Training panel (Phase 5) — FAQ entries admins manage from the dashboard.
FAQ_STATUSES = ("Active", "Inactive")
_FAQ_SEARCH_FIELDS = ("Question", "Answer", "Category", "Keywords", "Language")

# Course pricing used for revenue calc — kept in one place so it's easy to
# extend without touching the analytics loop itself.
_COURSE_PRICES = (
    ("digital", 4999),
    ("ai", 1299),
    ("data", 1299),
)

_SEARCH_FIELDS = ("Name", "Phone", "Email", "Course Interest", "Stage", "Tags")

# --------------------------------------------------------------------------- #
# Behavioural lead scoring & auto-tagging
#
# Each rule: (intent_key, keywords, score_points, tags_to_apply)
#   - intent_key is used to dedupe scoring — a lead is only ever awarded
#     `score_points` once for a given intent_key, no matter how many times
#     they repeat it (tracked via the "Scored Intents" column).
#   - tags_to_apply are added to "Tags" every time they match, but the tag
#     set itself is a set — reapplying a tag that's already there is a no-op.
#   - score_points of 0 means "tag-only" (no scoring, just categorisation).
# --------------------------------------------------------------------------- #
_INTENT_RULES = (
    ("fees", ("fee", "fees", "price", "cost", "charges", "how much"), 10, ("price",)),
    ("placement", ("placement", "placements", "job", "jobs", "career", "hire", "hiring"), 10, ("placement",)),
    ("certificate", ("certificate", "certificates", "certification", "certified"), 5, ("certificate",)),
    ("counsellor", ("counsellor", "counselor", "talk to someone", "speak to someone", "human", "call me", "callback"), 20, ("hot",)),
    ("payment", ("pay now", "payment", "buy now", "purchase", "enroll", "enrol", "checkout", "make payment"), 40, ("payment", "hot")),
    ("internship", ("intern", "internship", "internships"), 0, ("internship",)),
    ("parent", ("my son", "my daughter", "my child", "for my kid", "parent", "guardian"), 0, ("parent",)),
    ("beginner", ("beginner", "fresher", "no experience", "never coded", "new to coding", "not from cs", "non-tech"), 0, ("beginner",)),
    ("device", ("laptop", "device", "mobile phone", "smartphone", "no laptop", "using a phone"), 0, ("device",)),
    ("recommendation", ("recommend", "suggest", "which course", "confused", "not sure which"), 0, ("recommendation",)),
)


def _to_int(v, default=0):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default


def _parse_dt(date_str, time_str=""):
    """Parse 'DD-MM-YYYY' (+ optional 'HH:MM') into a datetime for sorting/
    comparison. Returns None if unparseable so callers can sort missing
    values safely (e.g. to the front/back) instead of crashing."""
    date_str = str(date_str or "").strip()
    time_str = str(time_str or "").strip()
    if not date_str:
        return None
    fmt = "%d-%m-%Y %H:%M" if time_str else "%d-%m-%Y"
    try:
        return datetime.strptime(f"{date_str} {time_str}".strip(), fmt)
    except ValueError:
        return None


# --------------------------------------------------------------------------- #
# Leads
# --------------------------------------------------------------------------- #
def _unread_phones():
    """Phones whose most recent message (either direction) came from the
    lead rather than the bot/admin. Used purely as a lightweight 'unread'
    signal on the lead list — derived from the existing Messages sheet, no
    new column or read-state tracking required. Best-effort: any failure
    just means no unread badges get shown, never breaks the lead list."""
    try:
        msgs = sheets.get_messages()
    except Exception:
        return set()
    latest = {}  # phone -> (dt, sender)
    for m in msgs:
        phone = str(m.get("Phone", "")).strip()
        if not phone:
            continue
        dt = _parse_dt(m.get("Date", ""), m.get("Time", "")) or datetime.min
        cur = latest.get(phone)
        if cur is None or dt >= cur[0]:
            latest[phone] = (dt, str(m.get("Sender", "")).strip())
    return {p for p, (_, sender) in latest.items() if sender == "User"}


@safe(default=[], label="crm.list_leads")
def list_leads(search="", stage="", min_score=0):
    """Return leads (list of dicts) filtered by search / stage / score, hottest
    first (ties broken by most recent). Search matches Name, Phone, Email,
    Course Interest, Stage, and Tags.

    Each returned dict is a shallow copy of the sheet row with one extra
    key, "_unread" (bool) — True when the lead's latest message hasn't had
    a bot/admin reply yet. This is additive only; every original column is
    still present and unchanged, so existing template/consumer code keeps
    working untouched."""
    search = (search or "").strip().lower()
    stage = (stage or "").strip()
    min_score = _to_int(min_score)

    rows = sheets.get_leads()
    unread = _unread_phones()
    out = []
    for r in rows:
        phone = str(r.get("Phone", "")).strip()
        if not phone:
            continue
        if stage and str(r.get("Stage", "")).strip() != stage:
            continue
        score = _to_int(r.get("Lead Score"))
        if score < min_score:
            continue
        if search:
            blob = " ".join(str(r.get(k, "")) for k in _SEARCH_FIELDS).lower()
            if search not in blob:
                continue
        row = dict(r)
        row["_unread"] = phone in unread
        out.append(row)

    out.sort(
        key=lambda r: (
            _to_int(r.get("Lead Score")),
            _parse_dt(r.get("Date", ""), r.get("Time", "")) or datetime.min,
        ),
        reverse=True,
    )
    return out


@safe(default=[], label="crm.get_chat")
def get_chat(phone):
    """All messages for a phone number, in chronological order. Messages with
    an unparsable/missing timestamp are kept (sorted to the end) rather than
    dropped, so nothing silently disappears from the dashboard."""
    phone = str(phone).strip()
    if not phone:
        return []
    msgs = [m for m in sheets.get_messages()
            if str(m.get("Phone", "")).strip() == phone]
    msgs.sort(key=lambda m: _parse_dt(m.get("Date", ""), m.get("Time", "")) or datetime.max)
    return msgs


@safe(default=None, label="crm.get_lead")
def get_lead(phone):
    phone = str(phone or "").strip()
    if not phone:
        return None
    return sheets.find_lead(phone)


@safe(default=False, label="crm.set_stage")
def set_stage(phone, stage):
    if stage not in STAGES:
        log.warning("crm.set_stage: rejected unknown stage %r for %s", stage, phone)
        return False
    return sheets.update_lead(phone, {
        "Stage": stage,
        "Last Contact": now_ist().strftime("%d-%m-%Y %H:%M"),
    })


@safe(default=False, label="crm.set_ai_paused")
def set_ai_paused(phone, paused: bool):
    return sheets.update_lead(phone, {"AI Paused": "Yes" if paused else "No"})


@safe(default=False, label="crm.is_ai_paused")
def is_ai_paused(phone):
    lead = sheets.find_lead(phone)
    return bool(lead) and str(lead.get("AI Paused", "")).strip().lower() == "yes"


@safe(default=False, label="crm.add_note")
def add_note(phone, note):
    note = (note or "").strip()
    if not note:
        return False
    lead = sheets.find_lead(phone)
    existing = str(lead.get("Notes", "")).strip() if lead else ""
    stamp = now_ist().strftime("%d-%m %H:%M")
    combined = (existing + "\n" if existing else "") + f"[{stamp}] {note}"
    # Only the Notes column is touched — set_stage/set_ai_paused/etc. remain
    # the only writers of their respective columns, so nothing here can
    # clobber unrelated fields.
    return sheets.update_lead(phone, {"Notes": combined})


@safe(default=False, label="crm.set_payment_status")
def set_payment_status(phone, status):
    """Lead Quick Action: Mark Paid (Feature 5). Not restricted to a fixed
    enum like Stage — Payment Status is free text on the sheet already
    ('Paid', 'Pending', 'Failed', etc.) — but this is the one path the
    dashboard's "Mark Paid" button uses, always writing 'Paid'."""
    status = (status or "").strip() or "Paid"
    return sheets.update_lead(phone, {
        "Payment Status": status,
        "Last Contact": now_ist().strftime("%d-%m-%Y %H:%M"),
    })


@safe(default=False, label="crm.delete_lead")
def delete_lead(phone):
    """Lead Quick Action: Delete Lead (Feature 5). Removes the row from the
    Leads sheet only — conversation history on the Messages sheet is left
    intact, so nothing about Feature 6 (Messages grouped by phone) breaks
    for a deleted lead's past chat."""
    phone = str(phone or "").strip()
    if not phone:
        return False
    return sheets.delete_lead_row(phone)


@safe(default=False, label="crm.ensure_lead")
def ensure_lead(phone, name=""):
    """New Contact (Feature 7): if this phone number has no lead row yet,
    create a minimal one so it shows up in Leads/Analytics like any other
    lead. No-op (and no duplicate) if the lead already exists — goes
    through the same append_lead() choke point as every other lead write,
    which itself re-checks by normalized phone before inserting."""
    phone = str(phone or "").strip()
    if not phone:
        return False
    if sheets.find_lead(phone):
        return True
    now = now_ist()
    sheets.append_lead({
        "Name": (name or "").strip(),
        "Phone": phone,
        "Lead Source": "Admin (New Contact)",
        "Stage": "New Lead",
        "Date": now.strftime("%d-%m-%Y"),
        "Time": now.strftime("%H:%M"),
        "Last Contact": now.strftime("%d-%m-%Y %H:%M"),
    })
    return True


@safe(default=False, label="crm.track_intent")
def track_intent(phone, text):
    """Scan an inbound message against _INTENT_RULES and, in a single
    write: bump Lead Score for any newly-matched scoring intent (never
    twice for the same intent — see "Scored Intents"), and add any newly-
    matched tags to Tags (deduped via a set). No-op if the lead is unknown
    or nothing matches, so it's safe to call on every inbound message."""
    text_l = str(text or "").strip().lower()
    if not text_l:
        return False

    lead = sheets.find_lead(phone)
    if not lead:
        return False

    scored = {t.strip() for t in str(lead.get("Scored Intents", "")).split(",") if t.strip()}
    tags = {t.strip() for t in str(lead.get("Tags", "")).split(",") if t.strip()}
    score = _to_int(lead.get("Lead Score"))

    newly_scored = set()
    score_delta = 0
    tags_changed = False

    for intent_key, keywords, points, add_tags in _INTENT_RULES:
        if not any(kw in text_l for kw in keywords):
            continue
        for tag in add_tags:
            if tag not in tags:
                tags.add(tag)
                tags_changed = True
        if points and intent_key not in scored:
            score_delta += points
            newly_scored.add(intent_key)

    if not score_delta and not tags_changed:
        return False

    updates = {}
    if score_delta:
        updates["Lead Score"] = score + score_delta
    if newly_scored:
        updates["Scored Intents"] = ",".join(sorted(scored | newly_scored))
    if tags_changed:
        updates["Tags"] = ",".join(sorted(tags))

    return sheets.update_lead(phone, updates)


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
@safe(default={}, label="crm.analytics")
def analytics():
    """Single pass over the leads sheet — avoids re-scanning `rows` once per
    metric like the old implementation did."""
    rows = sheets.get_leads()
    today = now_ist().strftime("%d-%m-%Y")

    total = 0
    today_leads = 0
    stage_counts = {stage: 0 for stage in STAGES}
    converted_rows = []
    hot_by_tag = 0  # behaviourally hot (Tags has "hot") but not yet staged as such

    for r in rows:
        if not str(r.get("Phone", "")).strip():
            continue
        total += 1

        if str(r.get("Date", "")).strip() == today:
            today_leads += 1

        stage = str(r.get("Stage", "")).strip()
        if stage in stage_counts:
            stage_counts[stage] += 1

        if stage not in ("Hot Lead", "Payment Sent"):
            tag_set = {t.strip().lower() for t in str(r.get("Tags", "")).split(",")}
            if "hot" in tag_set:
                hot_by_tag += 1

        is_converted = (stage == "Converted"
                         or str(r.get("Payment Status", "")).strip().lower() == "paid")
        if is_converted:
            converted_rows.append(r)

    sales = len(converted_rows)
    revenue = 0
    for r in converted_rows:
        interest = str(r.get("Course Interest", "")).lower()
        for keyword, price in _COURSE_PRICES:
            if keyword in interest:
                revenue += price
                break

    conv_rate = round((sales / total) * 100, 1) if total else 0.0

    return {
        "total": total,
        "today": today_leads,
        "new": stage_counts["New Lead"],
        "warm": stage_counts["Warm Lead"],
        "hot": stage_counts["Hot Lead"] + stage_counts["Payment Sent"] + hot_by_tag,
        "converted": stage_counts["Converted"],
        "not_interested": stage_counts["Not Interested"],
        "sales": sales,
        "revenue": revenue,
        "conversion_rate": conv_rate,
    }


@safe(default="", label="crm.export_csv")
def export_csv():
    rows = sheets.get_leads(use_cache=False)
    if not rows:
        return ""
    headers = list(rows[0].keys())
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers)
    writer.writeheader()
    for r in rows:
        writer.writerow(r)
    return buf.getvalue()


# --------------------------------------------------------------------------- #
# AI Training panel — FAQ management (Phase 5)
#
# A dashboard-managed knowledge base, kept in its own worksheet (see
# sheets.py). This is intentionally independent of knowledge.py's static,
# code-defined FAQ table — knowledge.py keeps working exactly as before and
# is not touched. This layer is the "future FAQ management" backend: it's
# fully functional CRUD today, ready to be wired into the live bot as a
# grounding source later without any further schema changes.
# --------------------------------------------------------------------------- #
@safe(default=[], label="crm.list_faqs")
def list_faqs(search="", category="", language="", status=""):
    search = (search or "").strip().lower()
    category = (category or "").strip()
    language = (language or "").strip()
    status = (status or "").strip()

    rows = sheets.get_faqs()
    out = []
    for r in rows:
        if not str(r.get("ID", "")).strip():
            continue
        if category and str(r.get("Category", "")).strip() != category:
            continue
        if language and str(r.get("Language", "")).strip() != language:
            continue
        if status and str(r.get("Status", "")).strip() != status:
            continue
        if search:
            blob = " ".join(str(r.get(k, "")) for k in _FAQ_SEARCH_FIELDS).lower()
            if search not in blob:
                continue
        out.append(dict(r))

    out.sort(key=lambda r: str(r.get("Updated At", "")), reverse=True)
    return out


@safe(default=None, label="crm.get_faq")
def get_faq(faq_id):
    faq_id = str(faq_id or "").strip()
    if not faq_id:
        return None
    return sheets.find_faq(faq_id)


@safe(default="", label="crm.add_faq")
def add_faq(question, answer, category="", keywords="", language="English", status="Active"):
    question = (question or "").strip()
    answer = (answer or "").strip()
    if not question or not answer:
        log.warning("crm.add_faq: rejected — question and answer are both required")
        return ""
    if status not in FAQ_STATUSES:
        status = "Active"
    return sheets.append_faq({
        "Question": question,
        "Answer": answer,
        "Category": (category or "").strip(),
        "Keywords": (keywords or "").strip(),
        "Language": (language or "English").strip() or "English",
        "Status": status,
    })


@safe(default=False, label="crm.update_faq")
def update_faq(faq_id, updates: dict):
    faq_id = str(faq_id or "").strip()
    if not faq_id or not updates:
        return False
    allowed = {"Question", "Answer", "Category", "Keywords", "Language", "Status"}
    clean = {k: v for k, v in updates.items() if k in allowed}
    if "Status" in clean and clean["Status"] not in FAQ_STATUSES:
        clean.pop("Status")
    if not clean:
        return False
    return sheets.update_faq(faq_id, clean)


@safe(default=False, label="crm.set_faq_status")
def set_faq_status(faq_id, status):
    if status not in FAQ_STATUSES:
        log.warning("crm.set_faq_status: rejected unknown status %r", status)
        return False
    return sheets.update_faq(faq_id, {"Status": status})


@safe(default=False, label="crm.delete_faq")
def delete_faq(faq_id):
    faq_id = str(faq_id or "").strip()
    if not faq_id:
        return False
    return sheets.delete_faq(faq_id)


@safe(default=[], label="crm.faq_categories")
def faq_categories():
    """Distinct categories currently in use — powers the filter dropdown
    without hardcoding a fixed category list."""
    cats = {str(r.get("Category", "")).strip() for r in sheets.get_faqs()}
    return sorted(c for c in cats if c)


# --------------------------------------------------------------------------- #
# Messages Center (Phase 5) — WhatsApp-style, phone-grouped conversation list
# built from the same Messages worksheet the dashboard chat already reads.
# Read-only aggregation; no new writes, no new worksheet.
# --------------------------------------------------------------------------- #
@safe(default=[], label="crm.list_conversations")
def list_conversations(search="", date_filter="", sender_filter=""):
    search = (search or "").strip().lower()
    date_filter = (date_filter or "").strip()  # expected "DD-MM-YYYY", matches the Date column verbatim
    sender_filter = (sender_filter or "").strip()  # "User" / "Admin" / "Bot" — matches latest message's sender

    msgs = sheets.get_messages()
    leads_by_phone = {}
    for l in sheets.get_leads():
        p = str(l.get("Phone", "")).strip()
        if p:
            leads_by_phone[p] = l

    latest = {}  # phone -> best-so-far dict
    for m in msgs:
        phone = str(m.get("Phone", "")).strip()
        if not phone:
            continue
        dt = _parse_dt(m.get("Date", ""), m.get("Time", "")) or datetime.min
        cur = latest.get(phone)
        if cur is not None and dt < cur["_dt"]:
            continue
        lead = leads_by_phone.get(phone)
        latest[phone] = {
            "phone": phone,
            "name": (lead.get("Name") if lead else "") or (lead.get("WhatsApp Name") if lead else "") or "",
            "last_message": str(m.get("Message", "")),
            "last_sender": str(m.get("Sender", "")),
            "last_date": str(m.get("Date", "")),
            "last_time": str(m.get("Time", "")),
            "is_lead": bool(lead),
            "_dt": dt,
        }

    out = list(latest.values())
    if search:
        out = [c for c in out if search in c["phone"].lower() or search in c["name"].lower()]
    if date_filter:
        out = [c for c in out if c["last_date"] == date_filter]
    if sender_filter:
        out = [c for c in out if c["last_sender"] == sender_filter]

    out.sort(key=lambda c: c["_dt"], reverse=True)
    for c in out:
        c.pop("_dt", None)
    return out


# --------------------------------------------------------------------------- #
# Global search (Feature 5) — Lead / Phone / Email / Message / Tags in one box.
# Returns the set of phone numbers that match, so callers (the dashboard
# route) can merge them into whatever list they're already rendering.
# --------------------------------------------------------------------------- #
@safe(default=set(), label="crm.global_search_phones")
def global_search_phones(query):
    query = (query or "").strip().lower()
    if not query:
        return set()

    matched = set()
    for l in sheets.get_leads():
        phone = str(l.get("Phone", "")).strip()
        if not phone:
            continue
        blob = " ".join(str(l.get(k, "")) for k in _SEARCH_FIELDS).lower()
        if query in blob:
            matched.add(phone)

    for m in sheets.get_messages():
        phone = str(m.get("Phone", "")).strip()
        if phone and query in str(m.get("Message", "")).lower():
            matched.add(phone)

    return matched


# --------------------------------------------------------------------------- #
# Follow-up signal breakdown — surfaces bot.py's Phase-4 "fu_<category>"
# lead tags (if present) as an Analytics widget. Purely read-only; if no
# such tags exist yet (bot.py hasn't been upgraded to Phase 4 in this
# deployment) this just returns an empty dict, so it's always safe to call.
# --------------------------------------------------------------------------- #
@safe(default={}, label="crm.followup_breakdown")
def followup_breakdown():
    counts = {}
    for r in sheets.get_leads():
        tags = {t.strip() for t in str(r.get("Tags", "")).split(",") if t.strip()}
        for t in tags:
            if t.startswith("fu_") and len(t) > 3:
                label = t[3:].replace("_", " ").title()
                counts[label] = counts.get(label, 0) + 1
    return dict(sorted(counts.items(), key=lambda kv: kv[1], reverse=True))


# =============================================================================
# Google Sheets Manager (Phase 6)
#
# A generic, spreadsheet-style view/search/sort/filter/paginate/edit layer
# over EVERY worksheet in the spreadsheet — Leads, Messages, FAQs, and any
# sheet added later — driven entirely by sheets.list_worksheet_titles().
# No sheet or column names are hardcoded here; Leads/Messages/FAQs keep
# using their existing dedicated functions above completely unchanged, this
# is purely additive.
# =============================================================================
SHEET_PAGE_SIZE_DEFAULT = 25
SHEET_PAGE_SIZE_MAX = 200


@safe(default=[], label="crm.list_sheet_names")
def list_sheet_names():
    """Every worksheet in the spreadsheet, for the Google Sheets tab's
    sheet picker (Feature 1) — no hardcoded names, so a new tab added in
    Google Sheets shows up here automatically."""
    return sheets.list_worksheet_titles()


def _sheet_sort_key(row, col):
    v = row.get(col, "")
    s = str(v).strip()
    try:
        return (0, float(s.replace(",", "")))
    except (TypeError, ValueError):
        pass
    dt = _parse_dt(s)
    if dt:
        return (1, dt)
    return (2, s.lower())


@safe(default={"headers": [], "rows": [], "total": 0, "page": 1, "pages": 1, "per_page": SHEET_PAGE_SIZE_DEFAULT},
      label="crm.sheet_view")
def sheet_view(title, search="", sort_col="", sort_dir="asc", page=1,
               per_page=SHEET_PAGE_SIZE_DEFAULT, filters=None, use_cache=True):
    """One page of a worksheet, spreadsheet-style (Feature 2): global text
    search across every column, optional single-column sort (numeric ->
    date -> text, in that order of preference), optional per-column exact-
    match filters, and pagination. Every returned row carries '_row' (the
    real sheet row number) so the frontend can edit/delete/duplicate it
    unambiguously regardless of sort/filter/page."""
    title = (title or "").strip()
    if not title:
        return {"headers": [], "rows": [], "total": 0, "page": 1, "pages": 1, "per_page": per_page}

    headers = sheets.get_worksheet_headers(title, use_cache=use_cache)
    rows = sheets.get_worksheet_rows_indexed(title, use_cache=use_cache)

    search = (search or "").strip().lower()
    if search:
        rows = [r for r in rows
                if search in " ".join(str(v) for k, v in r.items() if k != "_row").lower()]

    filters = filters or {}
    for col, val in filters.items():
        val = (val or "").strip()
        if not val or col not in headers:
            continue
        rows = [r for r in rows if str(r.get(col, "")).strip() == val]

    if sort_col and sort_col in headers:
        rows.sort(key=lambda r: _sheet_sort_key(r, sort_col), reverse=(sort_dir == "desc"))

    total = len(rows)
    per_page = max(1, min(_to_int(per_page, SHEET_PAGE_SIZE_DEFAULT), SHEET_PAGE_SIZE_MAX))
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(_to_int(page, 1), pages))
    start = (page - 1) * per_page
    page_rows = rows[start:start + per_page]

    return {
        "headers": headers, "rows": page_rows, "total": total,
        "page": page, "pages": pages, "per_page": per_page,
    }


@safe(default=False, label="crm.sheet_cell_update")
def sheet_cell_update(title, row, header, value):
    """Cell Editing (Feature 3) — writes straight through to Google Sheets,
    no manual refresh needed since the cache is invalidated on write."""
    title = (title or "").strip()
    header = (header or "").strip()
    row = _to_int(row)
    if not title or not header or row < 2:
        return False
    return sheets.update_worksheet_cell(title, row, header, value)


@safe(default=False, label="crm.sheet_row_add")
def sheet_row_add(title, values: dict):
    """Row Management: Add Row (Feature 4)."""
    title = (title or "").strip()
    if not title:
        return False
    return sheets.append_worksheet_row(title, values or {})


@safe(default=False, label="crm.sheet_row_delete")
def sheet_row_delete(title, row):
    """Row Management: Delete Row (Feature 4). Confirmation happens in the
    UI before this is ever called."""
    title = (title or "").strip()
    row = _to_int(row)
    if not title or row < 2:
        return False
    return sheets.delete_worksheet_row(title, row)


@safe(default=False, label="crm.sheet_row_duplicate")
def sheet_row_duplicate(title, row):
    """Row Management: Duplicate Row (Feature 4)."""
    title = (title or "").strip()
    row = _to_int(row)
    if not title or row < 2:
        return False
    return sheets.duplicate_worksheet_row(title, row)


@safe(default="", label="crm.sheet_export_csv")
def sheet_export_csv(title):
    """Import/Export: Export any sheet as CSV (Feature 10)."""
    title = (title or "").strip()
    headers = sheets.get_worksheet_headers(title, use_cache=False)
    if not headers:
        return ""
    rows = sheets.get_worksheet_records(title, use_cache=False)
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=headers, extrasaction="ignore")
    writer.writeheader()
    for r in rows:
        writer.writerow({h: r.get(h, "") for h in headers})
    return buf.getvalue()


def sheet_export_xlsx(title):
    """Import/Export: Export any sheet as Excel (Feature 10). Returns raw
    .xlsx bytes, or None if the optional 'openpyxl' dependency isn't
    installed — imported lazily here so its absence can never break app
    startup or any other route (Railway compatibility)."""
    title = (title or "").strip()
    try:
        from openpyxl import Workbook
    except ImportError:
        log.warning("sheet_export_xlsx: openpyxl not installed — Excel export unavailable")
        return None

    headers = sheets.get_worksheet_headers(title, use_cache=False)
    if not headers:
        return None
    rows = sheets.get_worksheet_records(title, use_cache=False)

    wb = Workbook()
    ws = wb.active
    ws.title = (title or "Sheet1")[:31]  # Excel sheet-name length limit
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])

    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


@safe(default=(0, 0, ["Import failed — please try again."]), label="crm.import_leads_csv")
def import_leads_csv(file_stream):
    """Import/Export: Import CSV into Leads (Feature 10), with validation
    (Feature 11 — never breaks existing columns, never duplicates a lead).
    Rows are matched/merged by Phone through the same append_lead() choke
    point every other lead write uses, so an imported row for an existing
    phone number updates that lead instead of creating a duplicate.
    Returns (added, updated, errors)."""
    raw = file_stream.read()
    if isinstance(raw, bytes):
        text = raw.decode("utf-8-sig", errors="replace")
    else:
        text = raw

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames or "Phone" not in reader.fieldnames:
        return (0, 0, ["CSV must include a 'Phone' column."])

    known_headers = set(sheets.LEAD_HEADERS)
    added = 0
    updated = 0
    errors = []

    for i, row in enumerate(reader, start=2):  # row 1 is the header
        phone = str(row.get("Phone", "")).strip()
        if not phone:
            errors.append(f"Row {i}: missing phone number — skipped.")
            continue
        # Only known Lead columns are imported; anything else in the CSV is
        # ignored rather than silently creating a mismatched column.
        clean = {k: (v or "").strip() for k, v in row.items() if k in known_headers and (v or "").strip()}
        clean["Phone"] = phone
        existed = bool(sheets.find_lead(phone))
        try:
            sheets.append_lead(clean)
        except Exception:
            log.exception("import_leads_csv: failed to save row %s (%s)", i, phone)
            errors.append(f"Row {i}: failed to save — skipped.")
            continue
        if existed:
            updated += 1
        else:
            added += 1

    return (added, updated, errors)

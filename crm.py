"""CRM data layer — powers the dashboard, analytics, export, and AI override."""

import io
import csv
from datetime import datetime
from zoneinfo import ZoneInfo

import sheets
from logger import log, safe

STAGES = [
    "New Lead", "Contacted", "Warm Lead", "Hot Lead",
    "Payment Sent", "Converted", "Not Interested", "Ghosted",
]

# Course pricing used for revenue calc — kept in one place so it's easy to
# extend without touching the analytics loop itself.
_COURSE_PRICES = (
    ("digital", 4999),
    ("ai", 1299),
    ("data", 1299),
)

# All leads are logged (by bot.py / sheets.py) in Indian local time, so CRM
# timestamps use the same zone rather than the server's own clock.
IST = ZoneInfo("Asia/Kolkata")

_SEARCH_FIELDS = ("Name", "Phone", "Email", "Course Interest", "Stage", "Tags")


def _now_ist() -> datetime:
    return datetime.now(IST)


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
@safe(default=[], label="crm.list_leads")
def list_leads(search="", stage="", min_score=0):
    """Return leads (list of dicts) filtered by search / stage / score, hottest
    first (ties broken by most recent). Search matches Name, Phone, Email,
    Course Interest, Stage, and Tags."""
    search = (search or "").strip().lower()
    stage = (stage or "").strip()
    min_score = _to_int(min_score)

    rows = sheets.get_leads()
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
        out.append(r)

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
        "Last Contact": _now_ist().strftime("%d-%m-%Y %H:%M"),
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
    stamp = _now_ist().strftime("%d-%m %H:%M")
    combined = (existing + "\n" if existing else "") + f"[{stamp}] {note}"
    # Only the Notes column is touched — set_stage/set_ai_paused/etc. remain
    # the only writers of their respective columns, so nothing here can
    # clobber unrelated fields.
    return sheets.update_lead(phone, {"Notes": combined})


# --------------------------------------------------------------------------- #
# Analytics
# --------------------------------------------------------------------------- #
@safe(default={}, label="crm.analytics")
def analytics():
    """Single pass over the leads sheet — avoids re-scanning `rows` once per
    metric like the old implementation did."""
    rows = sheets.get_leads()
    today = _now_ist().strftime("%d-%m-%Y")

    total = 0
    today_leads = 0
    stage_counts = {stage: 0 for stage in STAGES}
    converted_rows = []

    for r in rows:
        if not str(r.get("Phone", "")).strip():
            continue
        total += 1

        if str(r.get("Date", "")).strip() == today:
            today_leads += 1

        stage = str(r.get("Stage", "")).strip()
        if stage in stage_counts:
            stage_counts[stage] += 1

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
        "hot": stage_counts["Hot Lead"] + stage_counts["Payment Sent"],
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

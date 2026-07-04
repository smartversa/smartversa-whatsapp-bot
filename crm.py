"""CRM data layer — powers the dashboard, analytics, export, and AI override."""

import io
import csv
from datetime import datetime

import sheets
from logger import log, safe

STAGES = [
    "New Lead", "Contacted", "Warm Lead", "Hot Lead",
    "Payment Sent", "Converted", "Not Interested", "Ghosted",
]


def _to_int(v, default=0):
    try:
        return int(float(str(v).strip()))
    except (ValueError, TypeError):
        return default


@safe(default=[], label="crm.list_leads")
def list_leads(search="", stage="", min_score=0):
    """Return leads (list of dicts) filtered by search / stage / score, hottest first."""
    search = (search or "").strip().lower()
    stage = (stage or "").strip()
    rows = sheets.get_leads()
    out = []
    for r in rows:
        if not str(r.get("Phone", "")).strip():
            continue
        if stage and str(r.get("Stage", "")).strip() != stage:
            continue
        if _to_int(r.get("Lead Score")) < min_score:
            continue
        if search:
            blob = " ".join(str(r.get(k, "")) for k in
                            ("Name", "Phone", "Email", "Course Interest", "Tags")).lower()
            if search not in blob:
                continue
        out.append(r)
    out.sort(key=lambda r: _to_int(r.get("Lead Score")), reverse=True)
    return out


@safe(default=[], label="crm.get_chat")
def get_chat(phone):
    phone = str(phone).strip()
    msgs = [m for m in sheets.get_messages()
            if str(m.get("Phone", "")).strip() == phone]
    return msgs


@safe(default=None, label="crm.get_lead")
def get_lead(phone):
    return sheets.find_lead(phone)


@safe(default=False, label="crm.set_stage")
def set_stage(phone, stage):
    if stage not in STAGES:
        return False
    return sheets.update_lead(phone, {
        "Stage": stage,
        "Last Contact": datetime.now().strftime("%d-%m-%Y %H:%M"),
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
    lead = sheets.find_lead(phone)
    existing = str(lead.get("Notes", "")).strip() if lead else ""
    stamp = datetime.now().strftime("%d-%m %H:%M")
    combined = (existing + "\n" if existing else "") + f"[{stamp}] {note}"
    return sheets.update_lead(phone, {"Notes": combined})


@safe(default={}, label="crm.analytics")
def analytics():
    rows = sheets.get_leads()
    today = datetime.now().strftime("%d-%m-%Y")
    total = len(rows)
    today_leads = sum(1 for r in rows if str(r.get("Date", "")).strip() == today)
    hot = sum(1 for r in rows if str(r.get("Stage", "")).strip() in ("Hot Lead", "Payment Sent"))
    converted = [r for r in rows
                 if str(r.get("Stage", "")).strip() == "Converted"
                 or str(r.get("Payment Status", "")).strip().lower() == "paid"]
    sales = len(converted)

    revenue = 0
    for r in converted:
        interest = str(r.get("Course Interest", "")).lower()
        if "digital" in interest:
            revenue += 4999
        elif "ai" in interest or "data" in interest:
            revenue += 1299
    conv_rate = round((sales / total) * 100, 1) if total else 0.0

    return {
        "total": total,
        "today": today_leads,
        "hot": hot,
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

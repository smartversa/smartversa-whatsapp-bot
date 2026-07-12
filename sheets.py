"""
Google Sheets data-access layer.

- Lazy, cached client init (imported safely even without gspread installed).
- Short-TTL read cache to cut API calls (the old code re-read the whole sheet
  on every dashboard load / follow-up run).
- Non-destructive header management: missing columns are appended, never removed.
- Header-name-based writes so column order changes don't corrupt data.
- One WhatsApp number == one lead: phone numbers are normalized (spaces,
  '+', country-code prefixes stripped/ignored) so "+91XXXXXXXXXX",
  "91XXXXXXXXXX" and "XXXXXXXXXX" all resolve to the same row, and every
  write path (append_lead / update_lead) goes through that same lookup so a
  lead can never be silently duplicated.
"""

import re
import time
import json
import uuid
import threading
from datetime import datetime
from zoneinfo import ZoneInfo

from config import Config
from logger import log

# ---- Canonical schema (order matters for NEW sheets / appended headers) ----
# "Scored Intents" is an internal bookkeeping column (comma-separated intent
# keys) used to make Lead Score bumps idempotent — see crm.track_intent().
# It's appended at the end so existing sheets just get one more column
# rather than having anything reordered/removed (_ensure_headers below never
# deletes or reorders existing headers).
LEAD_HEADERS = [
    "Name", "Phone", "WhatsApp Name", "Email", "Preferred Language",
    "Course Interest", "Lead Source", "Inquiry Message", "Stage",
    "Date", "Time", "Follow-up Date", "Payment Status", "Notes",
    "Followup1 Sent", "Followup2 Sent", "Followup3 Sent", "Followup4 Sent",
    "Lead Score", "Tags", "Priority", "AI Paused", "Last Contact",
    "Scored Intents",
]

MESSAGE_HEADERS = ["Phone", "Sender", "Message", "Date", "Time"]

# FAQ / AI Training knowledge entries managed from the dashboard (Phase 5).
# This is a NEW, separate worksheet — additive only, doesn't touch the
# Leads/Messages sheets or knowledge.py's own static FAQ table. It exists so
# the dashboard has a real place to persist admin-authored FAQs; wiring the
# live bot to actually consult it is a future step (bot.py is untouched here).
FAQ_HEADERS = [
    "ID", "Question", "Answer", "Category", "Keywords", "Language",
    "Status", "Created At", "Updated At",
]

# --------------------------------------------------------------------------- #
# Timezone — single reusable "now" for the whole app.
#
# Every timestamp written to the sheet (lead creation, Last Contact,
# follow-up flags, message log) is Indian local time, so every module that
# needs "now" (app.py, crm.py, this module) should anchor to the same
# helper rather than each rolling its own datetime.now()/ZoneInfo(...).
# --------------------------------------------------------------------------- #
IST = ZoneInfo("Asia/Kolkata")


def now_ist() -> datetime:
    """Current time in IST, tz-aware. The one place 'now' is computed."""
    return datetime.now(IST)


def parse_ist_dt(date_str, time_str=""):
    """Parse a 'DD-MM-YYYY' (+ optional 'HH:MM') pair, as written by this
    module, into a tz-aware IST datetime. Returns None if blank/unparseable
    so callers can treat it as 'unknown' instead of crashing."""
    date_str = str(date_str or "").strip()
    time_str = str(time_str or "").strip()
    if not date_str:
        return None
    fmt = "%d-%m-%Y %H:%M" if time_str else "%d-%m-%Y"
    try:
        naive = datetime.strptime(f"{date_str} {time_str}".strip(), fmt)
        return naive.replace(tzinfo=IST)
    except ValueError:
        return None

_lock = threading.Lock()
_client = None
_spreadsheet = None
_ws_cache = {}          # title -> worksheet handle
_read_cache = {}        # title -> (timestamp, records)
_headers_cache = {}     # title -> header row (list)
_headers_checked = set()


# --------------------------------------------------------------------------- #
# Phone normalization
# --------------------------------------------------------------------------- #
def _normalize_phone(phone) -> str:
    """Canonicalize a phone number for matching.

    Strips everything but digits, then keeps only the last 10 digits so
    '+91XXXXXXXXXX', '91XXXXXXXXXX' and 'XXXXXXXXXX' all collapse to the
    same key. Case doesn't matter since only digits survive.
    """
    digits = re.sub(r"\D", "", str(phone or ""))
    if len(digits) > 10:
        digits = digits[-10:]
    return digits


# --------------------------------------------------------------------------- #
# Connection
# --------------------------------------------------------------------------- #
def _connect():
    global _client, _spreadsheet
    if _spreadsheet is not None:
        return _spreadsheet

    import gspread  # local import so module compiles without the dep
    from google.oauth2.service_account import Credentials

    if not Config.GOOGLE_CREDENTIALS_JSON:
        raise RuntimeError("Missing GOOGLE_CREDENTIALS_JSON environment variable")
    if not Config.GOOGLE_SHEET_NAME:
        raise RuntimeError("Missing GOOGLE_SHEET_NAME environment variable")

    scope = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(
        json.loads(Config.GOOGLE_CREDENTIALS_JSON), scopes=scope
    )
    _client = gspread.authorize(creds)
    _spreadsheet = _client.open(Config.GOOGLE_SHEET_NAME)
    log.info("Connected to Google Sheet '%s'", Config.GOOGLE_SHEET_NAME)
    return _spreadsheet


def _worksheet(title, headers=None):
    with _lock:
        if title in _ws_cache:
            return _ws_cache[title]
        ss = _connect()
        try:
            ws = ss.worksheet(title)
        except Exception:
            log.warning("Worksheet '%s' not found; creating it", title)
            ws = ss.add_worksheet(title=title, rows=1000, cols=max(26, len(headers or [])))
            if headers:
                ws.append_row(headers)
                _headers_cache[title] = list(headers)
        _ws_cache[title] = ws
    if headers and Config.ENSURE_HEADERS:
        _ensure_headers(ws, headers)
    return ws


def _get_headers(ws, use_cache=True):
    """Cached header-row read — avoids a fresh API call on every write."""
    title = ws.title
    if use_cache and title in _headers_cache:
        return _headers_cache[title]
    try:
        headers = ws.row_values(1)
    except Exception:
        log.exception("Failed to read headers for '%s'", title)
        headers = _headers_cache.get(title, [])
    _headers_cache[title] = headers
    return headers


def _ensure_headers(ws, wanted):
    """Append any missing header columns. Never deletes or reorders existing."""
    if ws.title in _headers_checked:
        return
    try:
        existing = ws.row_values(1)
    except Exception:
        log.exception("Failed to check headers for '%s'", ws.title)
        _headers_checked.add(ws.title)
        return
    if not existing:
        try:
            ws.update("A1", [wanted])
            _headers_cache[ws.title] = list(wanted)
        except Exception:
            log.exception("Failed to write initial headers for '%s'", ws.title)
        _headers_checked.add(ws.title)
        return
    missing = [h for h in wanted if h not in existing]
    if missing:
        new_row = existing + missing
        try:
            ws.update("A1", [new_row])
            existing = new_row
            log.info("Added missing headers to '%s': %s", ws.title, missing)
        except Exception:
            log.exception("Failed to append missing headers to '%s'", ws.title)
    _headers_cache[ws.title] = existing
    _headers_checked.add(ws.title)


def leads_ws():
    return _worksheet(Config.LEADS_WORKSHEET, LEAD_HEADERS)


def messages_ws():
    return _worksheet(Config.MESSAGES_WORKSHEET, MESSAGE_HEADERS)


def faqs_ws():
    # FAQS_WORKSHEET is optional in Config — default to "FAQs" so this works
    # without requiring a config.py change.
    title = getattr(Config, "FAQS_WORKSHEET", "FAQs")
    return _worksheet(title, FAQ_HEADERS)


# --------------------------------------------------------------------------- #
# Cached reads
# --------------------------------------------------------------------------- #
def _get_records(ws, use_cache=True):
    title = ws.title
    now = time.time()
    if use_cache and title in _read_cache:
        ts, records = _read_cache[title]
        if now - ts < Config.SHEETS_CACHE_TTL:
            return records
    try:
        records = ws.get_all_records()
    except Exception:
        log.exception("Failed to read records from '%s'", title)
        if title in _read_cache:
            return _read_cache[title][1]
        return []
    _read_cache[title] = (now, records)
    return records


def _invalidate(title):
    _read_cache.pop(title, None)


def get_leads(use_cache=True):
    return _get_records(leads_ws(), use_cache=use_cache)


def get_messages(use_cache=True):
    return _get_records(messages_ws(), use_cache=use_cache)


def get_faqs(use_cache=True):
    return _get_records(faqs_ws(), use_cache=use_cache)


def _build_phone_index(records):
    """normalized phone -> 1-based sheet row number, built from already-fetched
    records (no extra API call)."""
    index = {}
    for i, row in enumerate(records):
        norm = _normalize_phone(row.get("Phone", ""))
        if norm and norm not in index:  # keep the first (oldest) row on dupes
            index[norm] = i + 2  # +1 header row, +1 for 1-based indexing
    return index


def _locate_lead_row(phone, use_cache=True):
    """Return (row_number, record) for a phone, or (None, None) if not found.

    Tries the cached view first; if the phone isn't there (e.g. it was just
    added by another process) falls back to one fresh read before giving up.
    """
    norm = _normalize_phone(phone)
    if not norm:
        return None, None

    records = get_leads(use_cache=use_cache)
    row_number = _build_phone_index(records).get(norm)
    if row_number is not None:
        return row_number, records[row_number - 2]

    if use_cache:
        records = get_leads(use_cache=False)
        row_number = _build_phone_index(records).get(norm)
        if row_number is not None:
            return row_number, records[row_number - 2]

    return None, None


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def _header_index_map(ws):
    headers = _get_headers(ws)
    return {h: i + 1 for i, h in enumerate(headers)}  # 1-based column indexes


def append_lead(lead: dict):
    """Create a new lead row — unless this phone number already has one, in
    which case the existing row is updated instead. One WhatsApp number is
    always exactly one lead; this is the single choke point that guarantees
    it regardless of which caller (bot, dashboard, follow-up) hits it."""
    phone = str(lead.get("Phone", "")).strip()

    if phone:
        row_number, _existing = _locate_lead_row(phone, use_cache=False)
        if row_number is not None:
            log.info("append_lead: %s already exists — updating instead of duplicating", phone)
            update_lead(phone, lead)
            return

    lead = dict(lead)
    # Anchor creation/contact timestamps to IST if the caller didn't already
    # supply them, so every lead is timestamped consistently regardless of
    # which code path created it.
    now = now_ist()
    lead.setdefault("Date", now.strftime("%d-%m-%Y"))
    lead.setdefault("Time", now.strftime("%H:%M"))
    lead.setdefault("Last Contact", now.strftime("%d-%m-%Y %H:%M"))

    ws = leads_ws()
    headers = _get_headers(ws) or LEAD_HEADERS
    row = [str(lead.get(h, "")) for h in headers]
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("append_lead: failed to append row for %s", phone)
        return
    _invalidate(ws.title)


def update_lead(phone: str, updates: dict) -> bool:
    """Update only the given fields on the row matching this phone (by
    normalized number). Never touches unrelated columns, never adds a row.
    Returns True if a matching lead was found and updated."""
    if not updates:
        return False

    ws = leads_ws()
    row_number, _record = _locate_lead_row(phone, use_cache=True)
    if row_number is None:
        return False

    colmap = _header_index_map(ws)
    updates = {k: v for k, v in updates.items() if k in colmap}
    if not updates:
        return False

    try:
        import gspread
        cells = [
            gspread.Cell(row_number, colmap[key], str(value))
            for key, value in updates.items()
        ]
        ws.update_cells(cells, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("update_lead: failed to update row for %s", phone)
        return False

    _invalidate(ws.title)
    return True


def find_lead(phone: str):
    row_number, record = _locate_lead_row(phone, use_cache=True)
    return record


def append_message(phone, sender, message):
    """Log one chat line (never overwrites — every call adds a new row, so
    full conversation history is preserved) and bump the lead's Last
    Contact. This is the single choke point every caller (webhook, admin
    manual reply, follow-up cadence) goes through, so 'every incoming and
    outgoing message updates Last Contact' holds regardless of who's
    sending."""
    ws = messages_ws()
    now = now_ist()
    try:
        ws.append_row(
            [str(phone), sender, str(message),
             now.strftime("%d-%m-%Y"), now.strftime("%H:%M")],
            value_input_option="USER_ENTERED",
        )
    except Exception:
        log.exception("append_message: failed to append message for %s", phone)
        return
    _invalidate(ws.title)

    try:
        update_lead(phone, {"Last Contact": now.strftime("%d-%m-%Y %H:%M")})
    except Exception:
        log.exception("append_message: failed to update Last Contact for %s", phone)


# --------------------------------------------------------------------------- #
# FAQ / AI Training CRUD (Phase 5)
#
# Same shape as the lead write-path above (cached read -> build an index ->
# locate the row -> targeted header-based write) but indexed on a generated
# "ID" column instead of phone, since an FAQ has no natural unique key.
# --------------------------------------------------------------------------- #
def _build_id_index(records):
    index = {}
    for i, row in enumerate(records):
        rid = str(row.get("ID", "")).strip()
        if rid and rid not in index:
            index[rid] = i + 2  # +1 header row, +1 for 1-based indexing
    return index


def _locate_faq_row(faq_id, use_cache=True):
    faq_id = str(faq_id or "").strip()
    if not faq_id:
        return None, None
    records = get_faqs(use_cache=use_cache)
    row_number = _build_id_index(records).get(faq_id)
    if row_number is not None:
        return row_number, records[row_number - 2]
    if use_cache:
        records = get_faqs(use_cache=False)
        row_number = _build_id_index(records).get(faq_id)
        if row_number is not None:
            return row_number, records[row_number - 2]
    return None, None


def append_faq(faq: dict) -> str:
    """Create a new FAQ row. Returns the generated ID (empty string on
    failure) so the caller can confirm the write."""
    faq = dict(faq)
    faq_id = str(faq.get("ID", "")).strip() or uuid.uuid4().hex[:10]
    faq["ID"] = faq_id

    now = now_ist()
    faq.setdefault("Created At", now.strftime("%d-%m-%Y %H:%M"))
    faq.setdefault("Updated At", now.strftime("%d-%m-%Y %H:%M"))
    faq.setdefault("Status", "Active")

    ws = faqs_ws()
    headers = _get_headers(ws) or FAQ_HEADERS
    row = [str(faq.get(h, "")) for h in headers]
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("append_faq: failed to append FAQ row")
        return ""
    _invalidate(ws.title)
    return faq_id


def update_faq(faq_id: str, updates: dict) -> bool:
    """Update only the given fields on the FAQ row matching this ID. Never
    touches unrelated columns, never adds a row. Always stamps 'Updated At'."""
    if not updates:
        return False

    ws = faqs_ws()
    row_number, _record = _locate_faq_row(faq_id, use_cache=True)
    if row_number is None:
        return False

    updates = dict(updates)
    updates.setdefault("Updated At", now_ist().strftime("%d-%m-%Y %H:%M"))

    colmap = _header_index_map(ws)
    updates = {k: v for k, v in updates.items() if k in colmap}
    if not updates:
        return False

    try:
        import gspread
        cells = [
            gspread.Cell(row_number, colmap[key], str(value))
            for key, value in updates.items()
        ]
        ws.update_cells(cells, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("update_faq: failed to update FAQ row %s", faq_id)
        return False

    _invalidate(ws.title)
    return True


def delete_faq(faq_id: str) -> bool:
    """Permanently remove an FAQ row."""
    ws = faqs_ws()
    row_number, _record = _locate_faq_row(faq_id, use_cache=False)
    if row_number is None:
        return False
    try:
        ws.delete_rows(row_number)
    except Exception:
        log.exception("delete_faq: failed to delete FAQ row %s", faq_id)
        return False
    _invalidate(ws.title)
    return True


def find_faq(faq_id: str):
    row_number, record = _locate_faq_row(faq_id, use_cache=True)
    return record


# --------------------------------------------------------------------------- #
# Generic worksheet access (Phase 6 — Google Sheets Manager)
#
# Everything above this point is deliberately schema-specific (Leads /
# Messages / FAQs) so the existing dashboard tabs keep working byte-for-byte
# unchanged. This section adds a *generic* layer on top of the same
# connection/cache machinery that works on ANY worksheet in the spreadsheet
# by title — no sheet names hardcoded anywhere. New tabs added in Google
# Sheets show up automatically the next time the worksheet list is
# refreshed; nothing here needs to change for that.
# --------------------------------------------------------------------------- #
_meta_cache = {"ts": 0.0, "titles": []}
_META_TTL = 30  # seconds — the list of worksheet *names* changes rarely,
                 # so this is cached far more aggressively than row data.


def list_worksheet_titles(use_cache=True):
    """Every worksheet title in the spreadsheet, in sheet order. Cached
    briefly (Feature 12 — avoid a metadata API call on every dashboard
    load); pass use_cache=False to force a fresh read (e.g. after a sheet
    is added/renamed directly in Google Sheets)."""
    now = time.time()
    if use_cache and _meta_cache["titles"] and (now - _meta_cache["ts"] < _META_TTL):
        return _meta_cache["titles"]
    try:
        ss = _connect()
        titles = [ws.title for ws in ss.worksheets()]
    except Exception:
        log.exception("list_worksheet_titles: failed to list worksheets")
        return _meta_cache["titles"]
    _meta_cache["titles"] = titles
    _meta_cache["ts"] = now
    return titles


def get_worksheet(title):
    """Open (and cache) ANY worksheet by title. Unlike leads_ws()/messages_ws()/
    faqs_ws(), this never creates a sheet or forces a header schema — it's a
    read/write window onto whatever already exists."""
    title = str(title or "").strip()
    with _lock:
        if title in _ws_cache:
            return _ws_cache[title]
    ss = _connect()
    ws = ss.worksheet(title)  # raises if missing — callers check list_worksheet_titles() first
    with _lock:
        _ws_cache[title] = ws
    return ws


def get_worksheet_headers(title, use_cache=True):
    return _get_headers(get_worksheet(title), use_cache=use_cache)


def get_worksheet_records(title, use_cache=True):
    return _get_records(get_worksheet(title), use_cache=use_cache)


def get_worksheet_rows_indexed(title, use_cache=True):
    """Same records as get_worksheet_records, each tagged with its 1-based
    sheet row number under '_row' (header row = 1, so first data row = 2).
    The dashboard grid uses '_row' to address a cell/row for edit/delete/
    duplicate without ever re-deriving it from position, which would break
    the moment a filter or sort reorders what's on screen."""
    records = get_worksheet_records(title, use_cache=use_cache)
    out = []
    for i, r in enumerate(records):
        row = dict(r)
        row["_row"] = i + 2
        out.append(row)
    return out


def invalidate_worksheet(title):
    """Drop every cache layer for one worksheet after a write, so the very
    next read (dashboard poll or another admin's tab) sees the change with
    no manual refresh (Feature 3 / Feature 8)."""
    _invalidate(title)
    _headers_cache.pop(title, None)
    _headers_checked.discard(title)


def update_worksheet_cell(title, row_number, header, value):
    """Update a single cell, addressed by sheet row number + header name
    (never a raw column letter) so a column being reordered in Sheets can't
    silently corrupt a write. Refuses to touch the header row itself
    (Feature 11 — never delete/corrupt headers)."""
    row_number = int(row_number)
    if row_number <= 1:
        return False
    ws = get_worksheet(title)
    colmap = _header_index_map(ws)
    if header not in colmap:
        return False
    try:
        ws.update_cell(row_number, colmap[header], str(value))
    except Exception:
        log.exception("update_worksheet_cell: failed on '%s' row %s col %s", title, row_number, header)
        return False
    invalidate_worksheet(title)
    return True


def append_worksheet_row(title, values: dict):
    """Append a new row, mapping the given {header: value} dict onto the
    sheet's ACTUAL current header order — extra keys not present as a
    header are ignored, missing headers are written blank. Never assumes a
    fixed schema, so this works identically for Leads, Messages, FAQs, or
    any future sheet."""
    ws = get_worksheet(title)
    headers = get_worksheet_headers(title, use_cache=False)
    if not headers:
        return False
    row = [str(values.get(h, "")) for h in headers]
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("append_worksheet_row: failed on '%s'", title)
        return False
    invalidate_worksheet(title)
    return True


def duplicate_worksheet_row(title, row_number):
    """Append a copy of an existing row to the end of the sheet."""
    row_number = int(row_number)
    if row_number <= 1:
        return False
    ws = get_worksheet(title)
    records = get_worksheet_records(title, use_cache=False)
    idx = row_number - 2
    if idx < 0 or idx >= len(records):
        return False
    headers = get_worksheet_headers(title, use_cache=False)
    row = [str(records[idx].get(h, "")) for h in headers]
    try:
        ws.append_row(row, value_input_option="USER_ENTERED")
    except Exception:
        log.exception("duplicate_worksheet_row: failed on '%s' row %s", title, row_number)
        return False
    invalidate_worksheet(title)
    return True


def delete_worksheet_row(title, row_number):
    """Permanently delete one data row. Refuses to delete the header row
    (Feature 11)."""
    row_number = int(row_number)
    if row_number <= 1:
        return False
    ws = get_worksheet(title)
    try:
        ws.delete_rows(row_number)
    except Exception:
        log.exception("delete_worksheet_row: failed on '%s' row %s", title, row_number)
        return False
    invalidate_worksheet(title)
    return True


def delete_lead_row(phone):
    """Convenience wrapper: locate a lead by phone on the Leads sheet and
    delete that row. Goes through the same phone-normalizing lookup as
    every other lead write, so it can never delete the wrong row."""
    row_number, _record = _locate_lead_row(phone, use_cache=False)
    if row_number is None:
        return False
    ws = leads_ws()
    return delete_worksheet_row(ws.title, row_number)

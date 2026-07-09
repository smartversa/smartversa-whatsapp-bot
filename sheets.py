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
import threading
from datetime import datetime

from config import Config
from logger import log

# ---- Canonical schema (order matters for NEW sheets / appended headers) ----
LEAD_HEADERS = [
    "Name", "Phone", "WhatsApp Name", "Email", "Preferred Language",
    "Course Interest", "Lead Source", "Inquiry Message", "Stage",
    "Date", "Time", "Follow-up Date", "Payment Status", "Notes",
    "Followup1 Sent", "Followup2 Sent", "Followup3 Sent", "Followup4 Sent",
    "Lead Score", "Tags", "Priority", "AI Paused", "Last Contact",
]

MESSAGE_HEADERS = ["Phone", "Sender", "Message", "Date", "Time"]

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
    ws = messages_ws()
    now = datetime.now()
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

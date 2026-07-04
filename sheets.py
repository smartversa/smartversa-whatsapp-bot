"""
Google Sheets data-access layer.

- Lazy, cached client init (imported safely even without gspread installed).
- Short-TTL read cache to cut API calls (the old code re-read the whole sheet
  on every dashboard load / follow-up run).
- Non-destructive header management: missing columns are appended, never removed.
- Header-name-based writes so column order changes don't corrupt data.
"""

import json
import time
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
_headers_checked = set()


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
        _ws_cache[title] = ws
    if headers and Config.ENSURE_HEADERS:
        _ensure_headers(ws, headers)
    return ws


def _ensure_headers(ws, wanted):
    """Append any missing header columns. Never deletes or reorders existing."""
    if ws.title in _headers_checked:
        return
    try:
        existing = ws.row_values(1)
    except Exception:
        _headers_checked.add(ws.title)
        return
    if not existing:
        ws.update("A1", [wanted])
        _headers_checked.add(ws.title)
        return
    missing = [h for h in wanted if h not in existing]
    if missing:
        new_row = existing + missing
        ws.update("A1", [new_row])
        log.info("Added missing headers to '%s': %s", ws.title, missing)
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
    records = ws.get_all_records()
    _read_cache[title] = (now, records)
    return records


def _invalidate(title):
    _read_cache.pop(title, None)


def get_leads(use_cache=True):
    return _get_records(leads_ws(), use_cache=use_cache)


def get_messages(use_cache=True):
    return _get_records(messages_ws(), use_cache=use_cache)


# --------------------------------------------------------------------------- #
# Writes
# --------------------------------------------------------------------------- #
def _header_index_map(ws):
    headers = ws.row_values(1)
    return {h: i + 1 for i, h in enumerate(headers)}  # 1-based column indexes


def append_lead(lead: dict):
    """Append a lead using the canonical header order."""
    ws = leads_ws()
    headers = ws.row_values(1) or LEAD_HEADERS
    row = [str(lead.get(h, "")) for h in headers]
    ws.append_row(row, value_input_option="USER_ENTERED")
    _invalidate(ws.title)


def update_lead(phone: str, updates: dict) -> bool:
    """Update fields on the row whose Phone matches. Returns True if found."""
    ws = leads_ws()
    records = _get_records(ws, use_cache=False)
    colmap = _header_index_map(ws)
    phone = str(phone).strip()

    for i, row in enumerate(records):
        if str(row.get("Phone", "")).strip() == phone:
            row_number = i + 2  # +1 header, +1 for 1-based
            cells = []
            for key, value in updates.items():
                if key in colmap:
                    cells.append((row_number, colmap[key], str(value)))
            for (r, c, v) in cells:
                ws.update_cell(r, c, v)
            _invalidate(ws.title)
            return True
    return False


def find_lead(phone: str):
    phone = str(phone).strip()
    for row in get_leads():
        if str(row.get("Phone", "")).strip() == phone:
            return row
    return None


def append_message(phone, sender, message):
    ws = messages_ws()
    now = datetime.now()
    ws.append_row(
        [str(phone), sender, str(message),
         now.strftime("%d-%m-%Y"), now.strftime("%H:%M")],
        value_input_option="USER_ENTERED",
    )
    _invalidate(ws.title)

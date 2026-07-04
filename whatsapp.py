"""WhatsApp Cloud API (Meta) wrapper — send text and images, with logging."""

import hmac
import hashlib

import requests

from config import Config
from logger import log
import sheets


def _endpoint():
    return (
        f"https://graph.facebook.com/{Config.WHATSAPP_API_VERSION}"
        f"/{Config.PHONE_NUMBER_ID}/messages"
    )


def _headers():
    return {
        "Authorization": f"Bearer {Config.WHATSAPP_TOKEN}",
        "Content-Type": "application/json",
    }


def _post(payload):
    try:
        resp = requests.post(_endpoint(), headers=_headers(), json=payload, timeout=15)
        if resp.status_code >= 400:
            log.error("WhatsApp API %s: %s", resp.status_code, resp.text)
        else:
            log.info("WhatsApp sent (%s)", resp.status_code)
        return resp.status_code < 400
    except Exception:
        log.exception("WhatsApp send failed")
        return False


def send_message(to, text, sender="Bot", persist=True):
    ok = _post({
        "messaging_product": "whatsapp",
        "to": str(to).strip(),
        "type": "text",
        "text": {"body": text},
    })
    if persist:
        try:
            sheets.append_message(to, sender, text)
        except Exception:
            log.exception("Could not persist outgoing message")
    return ok


def send_image(to, image_url, caption=""):
    ok = _post({
        "messaging_product": "whatsapp",
        "to": str(to).strip(),
        "type": "image",
        "image": {"link": image_url, "caption": caption},
    })
    try:
        sheets.append_message(to, "Bot", f"[IMAGE] {caption}")
    except Exception:
        log.exception("Could not persist outgoing image")
    return ok


def verify_signature(raw_body: bytes, signature_header: str) -> bool:
    """
    Verify Meta's X-Hub-Signature-256 header when META_APP_SECRET is set.
    Returns True if verification passes OR if no app secret is configured
    (so existing deployments without the secret keep working).
    """
    if not Config.META_APP_SECRET:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(
        Config.META_APP_SECRET.encode(),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    provided = signature_header.split("=", 1)[1]
    return hmac.compare_digest(expected, provided)

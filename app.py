from flask import Flask, request
import os
import json
import gspread
import requests
from google.oauth2.service_account import Credentials
from datetime import datetime

app = Flask(__name__)

VERIFY_TOKEN = "smartversa_bot_2026"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = "1207113965816609"

user_sessions = {}

# ---------- Google Sheets Setup ----------
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = Credentials.from_service_account_info(creds_json, scopes=scope)
client = gspread.authorize(creds)

sheet_name = os.getenv("GOOGLE_SHEET_NAME")
sheet = client.open(sheet_name).sheet1


def send_whatsapp_message(to, text):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }

    requests.post(url, headers=headers, json=payload)


@app.route("/")
def home():
    return "SmartVersa Bot Running"


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403

    if request.method == "POST":
        data = request.get_json()

        try:
            entry = data["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]

            if "messages" in value:
                msg = value["messages"][0]
                phone = msg["from"]

                if "text" not in msg:
                    return "OK", 200

                text = msg["text"]["body"].strip()

                # New user
                if phone not in user_sessions:
                    user_sessions[phone] = {
                        "step": 1,
                        "name": "",
                        "language": "",
                        "email": "",
                        "interest": ""
                    }

                    send_whatsapp_message(
                        phone,
                        "Hi 👋 Welcome to SmartVersa!\n\nLet's get you registered.\n\nPlease enter your full name:"
                    )
                    return "OK", 200

                session = user_sessions[phone]

                # Step 1 -> Name
                if session["step"] == 1:
                    session["name"] = text
                    session["step"] = 2
                    send_whatsapp_message(
                        phone,
                        "Preferred Language?\n1. Hindi\n2. English"
                    )

                # Step 2 -> Language
                elif session["step"] == 2:
                    session["language"] = text
                    session["step"] = 3
                    send_whatsapp_message(
                        phone,
                        "Please enter your email address (or type SKIP):"
                    )

                # Step 3 -> Email
                elif session["step"] == 3:
                    session["email"] = text
                    session["step"] = 4
                    send_whatsapp_message(
                        phone,
                        "Which program interests you?\n1. AI & Data Science\n2. Digital Marketing\n3. Both"
                    )

                # Step 4 -> Interest + Save
                elif session["step"] == 4:
                    session["interest"] = text

                    now = datetime.now()

                    row = [
                        session["name"],
                        phone,
                        "",
                        session["email"],
                        session["language"],
                        session["interest"],
                        "WhatsApp Bot",
                        text,
                        "Qualified Lead",
                        now.strftime("%d-%m-%Y"),
                        now.strftime("%H:%M"),
                        "",
                        "Pending",
                        ""
                    ]

                    sheet.append_row(row)

                    send_whatsapp_message(
                        phone,
                        "Thanks for registering ✅\n\nOur team will contact you shortly.\n\nEnroll here:\nhttps://pay.smartversa.in/orderform"
                    )

                    del user_sessions[phone]

        except Exception as e:
            print("ERROR:", e)

        return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

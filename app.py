from flask import Flask, request
import os
import json
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime

app = Flask(__name__)

# =========================
# GOOGLE SHEETS SETUP
# =========================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = Credentials.from_service_account_info(creds_json, scopes=scope)
client = gspread.authorize(creds)

sheet_name = os.getenv("GOOGLE_SHEET_NAME")
sheet = client.open(sheet_name).sheet1


@app.route("/")
def home():
    return "SmartVersa Bot Running"


@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        VERIFY_TOKEN = "smartversa_bot_2026"

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403

    if request.method == "POST":
        data = request.get_json()

        print("Incoming:", data)

        try:
            entry = data["entry"][0]
            changes = entry["changes"][0]
            value = changes["value"]

            if "messages" in value:
                msg = value["messages"][0]
                phone = msg["from"]

                message_text = ""
                if "text" in msg:
                    message_text = msg["text"]["body"]

                now = datetime.now()

                row = [
                    "",  # Name
                    phone,
                    "",  # WhatsApp Name
                    "",  # Email
                    "",  # Preferred Language
                    "",  # Course Interest
                    "WhatsApp Bot",
                    message_text,
                    "New Lead",
                    now.strftime("%d-%m-%Y"),
                    now.strftime("%H:%M"),
                    "",
                    "Pending",
                    ""
                ]

                sheet.append_row(row)

                print("Lead Saved:", phone)

        except Exception as e:
            print("ERROR:", e)

        return "OK", 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

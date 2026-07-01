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


def send_whatsapp_message(to, text, sender="Bot"):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to).strip(),
        "type": "text",
        "text": {"body": text}
    }

    response = requests.post(url, headers=headers, json=payload)

    save_message(str(to), sender, text)

    print("Status:", response.status_code)
    print("Response:", response.text)


def save_lead(phone, session):
    now = datetime.now()

    row = [
        session["name"],
        phone,
        session.get("whatsapp_name", ""),
        session["email"],
        session["language"],
        session["interest"],
        "WhatsApp Bot",
        session["inquiry_message"],
        session["stage"],
        now.strftime("%d-%m-%Y"),
        now.strftime("%H:%M"),
        "",
        "Pending",
        "",
        "No",
        "No"
    ]

    sheet.append_row(row)


def check_pending_leads():
    records = sheet.get_all_records()

    for idx, row in enumerate(records, start=2):
        try:
            stage = row["Stage"]
            payment = row["Payment Status"]
            followup1 = row["Followup1 Sent"]
            followup2 = row["Followup2 Sent"]

            if stage != "Hot Lead":
                continue

            if payment == "Paid":
                continue

            lead_date = row["Date"]
            lead_time = row["Time"]

            if not lead_date or not lead_time:
                continue

            lead_datetime = datetime.strptime(
                f"{lead_date} {lead_time}",
                "%d-%m-%Y %H:%M"
            )

            hours_passed = (
                datetime.now() - lead_datetime
            ).total_seconds() / 3600

            phone = row["Phone"]
            name = row["Name"]

            if hours_passed >= 24 and followup1 != "Yes":
                msg = f"""Hi {name} 👋

You showed interest in SmartVersa recently.

Need help with enrollment or course selection?

Reply anytime 😊"""

                send_whatsapp_message(phone, msg)
                sheet.update_cell(idx, 15, "Yes")

            elif hours_passed >= 72 and followup2 != "Yes":
                msg = """Hi 😊

Just a reminder about your SmartVersa enrollment.

Seats are limited.

Enroll now:
https://pay.smartversa.in/orderform"""

                send_whatsapp_message(phone, msg)
                sheet.update_cell(idx, 16, "Yes")

        except Exception as e:
            print("FOLLOWUP ERROR:", e)


def get_course_details(choice):
    if choice == "1":
        return (
            "AI & Data Science",
            """🤖 AI & Data Science Course

✔ Python from scratch
✔ Data Analysis
✔ Machine Learning basics
✔ AI Tools
✔ Real-world Projects
✔ Internship Certificate
✔ Resume Building
✔ Portfolio Building

Price: ₹1299"""
        )

    elif choice == "2":
        return (
            "Digital Marketing",
            """📈 Digital Marketing Course

✔ Social Media Marketing
✔ Meta Ads
✔ SEO
✔ Content Creation
✔ Lead Generation
✔ Real Client Projects
✔ Internship Certificate
✔ Freelancing Guidance

Price: ₹4999"""
        )

    else:
        return (
            "Both",
            """🎯 SmartVersa Course Bundle

🤖 AI & Data Science — ₹1299
📈 Digital Marketing — ₹4999"""
        )


@app.route("/")
def home():
    return "SmartVersa Bot Running"


@app.route("/followup")
def run_followup():
    check_pending_leads()
    return "Follow-up completed"


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

                wa_name = ""
                if "contacts" in value:
                    wa_name = value["contacts"][0]["profile"]["name"]

                if "text" not in msg:
                    return "OK", 200

                text = msg["text"]["body"].strip()

                save_message(phone, "User", text)
                
                if phone not in user_sessions:
                    user_sessions[phone] = {
                        "step": 1,
                        "name": "",
                        "whatsapp_name": wa_name,
                        "language": "",
                        "email": "",
                        "interest": "",
                        "stage": "",
                        "inquiry_message": text
                    }

                    send_whatsapp_message(
                        phone,
                        "Hi 👋 Welcome to SmartVersa!\n\nPlease enter your full name:"
                    )
                    return "OK", 200

                session = user_sessions[phone]

                if session["step"] == 1:
                    session["name"] = text
                    session["step"] = 2
                    send_whatsapp_message(phone, "Preferred Language?\n\n1. Hindi\n2. English")

                elif session["step"] == 2:
                    if text == "1":
                        session["language"] = "Hindi"
                    elif text == "2":
                        session["language"] = "English"
                    else:
                        send_whatsapp_message(phone, "Please reply with 1 or 2.")
                        return "OK", 200

                    session["step"] = 3
                    send_whatsapp_message(
                        phone,
                        "Which course are you interested in?\n\n1. AI & Data Science\n2. Digital Marketing\n3. Both"
                    )

                elif session["step"] == 3:
                    if text not in ["1", "2", "3"]:
                        send_whatsapp_message(phone, "Please reply with 1, 2, or 3.")
                        return "OK", 200

                    course_name, details = get_course_details(text)
                    session["interest"] = course_name
                    session["step"] = 4

                    send_whatsapp_message(
                        phone,
                        details + "\n\nAre you interested?\n\n1. Yes\n2. No / Need Counsellor"
                    )

                elif session["step"] == 4:
                    if text == "1":
                        session["stage"] = "Hot Lead"
                        session["step"] = 5
                        send_whatsapp_message(
                            phone,
                            "Great 😊\n\nPlease enter your email address (or type SKIP):"
                        )

                    elif text == "2":
                        session["stage"] = "Need Counsellor"
                        session["step"] = 5
                        send_whatsapp_message(
                            phone,
                            "No worries 😊 Our counsellor will contact you shortly.\n\nPlease enter your email address (or type SKIP):"
                        )
                    else:
                        send_whatsapp_message(phone, "Please reply with 1 or 2.")

                elif session["step"] == 5:
                    if text.upper() == "SKIP":
                        session["email"] = ""
                    else:
                        session["email"] = text

                    save_lead(phone, session)

                    if session["stage"] == "Hot Lead":
                        send_whatsapp_message(
                            phone,
                            "🎉 Enrollment Link:\nhttps://pay.smartversa.in/orderform"
                        )
                    else:
                        send_whatsapp_message(
                            phone,
                            "✅ Your request has been sent to our counsellor."
                        )

                    del user_sessions[phone]

        except Exception as e:
            print("ERROR:", e)

        return "OK", 200


def save_message(phone, sender, message):
    messages_sheet = client.open(sheet_name).worksheet("Messages")
    now = datetime.now()

    row = [
        phone,
        sender,
        message,
        now.strftime("%d-%m-%Y"),
        now.strftime("%H:%M")
    ]

    messages_sheet.append_row(row)

@app.route("/send_manual")
def send_manual():
    phone = request.args.get("phone")
    msg = request.args.get("msg")

    if not phone or not msg:
        return "phone and msg required"

    send_whatsapp_message(phone, msg, sender="Admin")
    return "Message sent"
    

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

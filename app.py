from flask import Flask, request, redirect
import os
import json
import html
import gspread
import requests
from google.oauth2.service_account import Credentials
from datetime import datetime

app = Flask(__name__)

# ================= CONFIG =================
VERIFY_TOKEN = "smartversa_bot_2026"
WHATSAPP_TOKEN = os.getenv("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = "1207113965816609"

WEBSITE_URL = "https://smartversa.in"
PAYMENT_URL = "https://pay.smartversa.in/orderform"
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "smartversa123")

AI_IMAGE_URL = "https://images.unsplash.com/photo-1551288049-bebda4e38f71"
DM_IMAGE_URL = "https://images.unsplash.com/photo-1552664730-d307ca884978"

WHATSAPP_API_VERSION = "v23.0"

user_sessions = {}

# ================= GOOGLE SHEETS =================
SCOPE = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

_creds_raw = os.getenv("GOOGLE_CREDENTIALS_JSON")
if not _creds_raw:
    raise RuntimeError("Missing GOOGLE_CREDENTIALS_JSON environment variable")

creds_json = json.loads(_creds_raw)
creds = Credentials.from_service_account_info(creds_json, scopes=SCOPE)
client = gspread.authorize(creds)

SHEET_NAME = os.getenv("GOOGLE_SHEET_NAME")
if not SHEET_NAME:
    raise RuntimeError("Missing GOOGLE_SHEET_NAME environment variable")

sheet = client.open(SHEET_NAME).sheet1
messages_sheet = sheet.spreadsheet.worksheet("Messages")


# ================= HELPERS =================
def save_message(phone, sender, message):
    now = datetime.now()
    row = [
        str(phone),
        sender,
        message,
        now.strftime("%d-%m-%Y"),
        now.strftime("%H:%M")
    ]
    messages_sheet.append_row(row)


def send_whatsapp_message(to, text, sender="Bot"):
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{PHONE_NUMBER_ID}/messages"

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

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)
    except Exception as e:
        print("SEND MESSAGE ERROR:", e)

    save_message(to, sender, text)


def send_whatsapp_image(to, image_url, caption=""):
    url = f"https://graph.facebook.com/{WHATSAPP_API_VERSION}/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to).strip(),
        "type": "image",
        "image": {
            "link": image_url,
            "caption": caption
        }
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=15)
        print("STATUS:", response.status_code)
        print("RESPONSE:", response.text)
    except Exception as e:
        print("SEND IMAGE ERROR:", e)

    save_message(to, "Bot", f"[IMAGE] {caption}")


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


def get_course_details(choice):
    if choice == "1":
        return (
            "AI & Data Science",
            AI_IMAGE_URL,
            """🤖 AI & Data Science Course

✔ Python from scratch
✔ Data Analysis
✔ Machine Learning Basics
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
            DM_IMAGE_URL,
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
            AI_IMAGE_URL,
            """🎯 SmartVersa Bundle

🤖 AI & Data Science — ₹1299
📈 Digital Marketing — ₹4999"""
        )


def escape_html(text):
    return html.escape(str(text)).replace("\n", "<br>")


# ================= ROUTES =================
@app.route("/")
def home():
    return "SmartVersa Bot Running"


@app.route("/followup")
def run_followup():
    try:
        records = sheet.get_all_records()
    except Exception as e:
        print("SHEET ERROR:", e)
        return "Sheet error"

    for idx, row in enumerate(records, start=2):
        try:
            if row["Stage"] != "Hot Lead":
                continue

            if row["Payment Status"] == "Paid":
                continue

            lead_date = row["Date"]
            lead_time = row["Time"]

            if not lead_date or not lead_time:
                continue

            lead_datetime = datetime.strptime(
                f"{lead_date} {lead_time}",
                "%d-%m-%Y %H:%M"
            )

            hours_passed = (datetime.now() - lead_datetime).total_seconds() / 3600

            phone = row["Phone"]
            name = row["Name"]

            if hours_passed >= 24 and row["Followup1 Sent"] != "Yes":
                send_whatsapp_message(
                    phone,
                    f"Hi {name} 👋\n\nNeed help with enrollment?\n\nReply anytime 😊"
                )
                sheet.update_cell(idx, 15, "Yes")

            elif hours_passed >= 72 and row["Followup2 Sent"] != "Yes":
                send_whatsapp_message(
                    phone,
                    f"Final reminder 😊\n\nEnroll now:\n{PAYMENT_URL}"
                )
                sheet.update_cell(idx, 16, "Yes")

        except Exception as e:
            print("FOLLOWUP ERROR:", e)

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

    data = request.get_json(silent=True) or {}

    try:
        entry = data["entry"][0]
        changes = entry["changes"][0]
        value = changes["value"]

        if "messages" not in value:
            return "OK", 200

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
            send_whatsapp_message(
                phone,
                "Preferred Language?\n\n1. Hindi\n2. English"
            )

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

            course_name, image_url, details = get_course_details(text)
            session["interest"] = course_name
            session["step"] = 4

            send_whatsapp_image(phone, image_url, "SmartVersa Course")
            send_whatsapp_message(phone, details)
            send_whatsapp_message(
                phone,
                f"🌐 Website: {WEBSITE_URL}\n\nAre you interested?\n\n1. Yes\n2. No / Need Counsellor"
            )

        elif session["step"] == 4:
            if text == "1":
                session["stage"] = "Hot Lead"
                session["step"] = 5
                send_whatsapp_message(
                    phone,
                    "Great 😊\n\nPlease enter your email (or type SKIP):"
                )
            elif text == "2":
                session["stage"] = "Need Counsellor"
                session["step"] = 5
                send_whatsapp_message(
                    phone,
                    "No worries 😊 Counsellor will contact you.\n\nPlease enter your email (or type SKIP):"
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
                    f"🎉 Enrollment Link:\n{PAYMENT_URL}"
                )
            else:
                send_whatsapp_message(
                    phone,
                    "✅ Your request has been sent to counsellor."
                )

            del user_sessions[phone]

    except Exception as e:
        print("WEBHOOK ERROR:", e)

    return "OK", 200


@app.route("/send_manual", methods=["POST"])
def send_manual():
    password = request.form.get("password")
    if password != ADMIN_PASSWORD:
        return "Unauthorized"

    phone = request.form.get("phone")
    msg = request.form.get("msg")

    if not phone or not msg:
        return "Missing fields"

    send_whatsapp_message(phone, msg, sender="Admin")
    return redirect(f"/dashboard?phone={phone}&password={password}")


LOGIN_PAGE = """
<html>
<head>
    <title>SmartVersa Admin Login</title>
    <style>
        body {{
            font-family:Arial, sans-serif;
            background:#f4f6fb;
            height:100vh;
            margin:0;
            display:flex;
            align-items:center;
            justify-content:center;
        }}
        .box {{
            background:white;
            padding:40px;
            border-radius:14px;
            box-shadow:0 4px 20px rgba(0,0,0,0.08);
            text-align:center;
        }}
        input {{
            padding:10px 14px;
            border-radius:8px;
            border:1px solid #ccc;
            margin:10px 0;
            width:220px;
        }}
        button {{
            padding:10px 20px;
            border:none;
            background:#25d366;
            color:white;
            border-radius:8px;
            cursor:pointer;
            font-weight:bold;
        }}
    </style>
</head>
<body>
    <div class="box">
        <h2>SmartVersa Admin Login</h2>
        <form method="GET">
            <input type="password" name="password" placeholder="Password" autofocus/><br>
            <button type="submit">Login</button>
        </form>
    </div>
</body>
</html>
"""


@app.route("/dashboard")
def dashboard():
    password = request.args.get("password", "")
    search = request.args.get("search", "").strip()
    selected_phone = request.args.get("phone", "")

    if password != ADMIN_PASSWORD:
        return LOGIN_PAGE

    try:
        records = messages_sheet.get_all_records()
    except Exception as e:
        print("SHEET ERROR:", e)
        records = []

    leads = {}
    for row in records:
        phone = str(row.get("Phone", "")).strip()
        if not phone:
            continue
        if search and search not in phone:
            continue
        leads.setdefault(phone, []).append(row)

    chat_html = ""
    if selected_phone and selected_phone in leads:
        for msg in leads[selected_phone]:
            sender = msg.get("Sender", "")
            message = escape_html(msg.get("Message", ""))
            time = escape_html(msg.get("Time", ""))

            if sender == "User":
                bg = "#dcf8c6"
                align = "left"
            elif sender == "Admin":
                bg = "#d9efff"
                align = "right"
            else:
                bg = "#f0f0f0"
                align = "left"

            chat_html += f"""
            <div style="text-align:{align};margin:10px 0;">
                <div style="display:inline-block;background:{bg};padding:12px 16px;border-radius:15px;max-width:70%;text-align:left;">
                    <b>{escape_html(sender)}</b><br>
                    {message}
                    <div style="font-size:11px;color:gray;margin-top:6px;">{time}</div>
                </div>
            </div>
            """

    leads_html = ""
    for phone in leads:
        active = "background:#d9f2d9;" if phone == selected_phone else ""
        leads_html += f"""
        <div class="lead" style="{active}">
            <a href="/dashboard?password={password}&phone={phone}&search={search}">{escape_html(phone)}</a>
        </div>
        """

    if not leads_html:
        leads_html = "<p style='color:gray;'>No leads found.</p>"

    chat_title = escape_html(selected_phone) if selected_phone else "Select a lead"

    html_page = f"""
    <html>
    <head>
        <title>SmartVersa CRM</title>
        <style>
            * {{
                box-sizing:border-box;
            }}
            body {{
                margin:0;
                font-family:Arial, sans-serif;
                display:flex;
                height:100vh;
                background:#ece5dd;
            }}
            .left {{
                width:30%;
                min-width:260px;
                background:white;
                border-right:1px solid #ddd;
                overflow:auto;
                padding:20px;
            }}
            .left h2 {{
                margin-top:0;
            }}
            .right {{
                width:70%;
                display:flex;
                flex-direction:column;
                background:#efeae2;
            }}
            .chat {{
                flex:1;
                overflow:auto;
                padding:20px;
            }}
            .lead {{
                padding:14px;
                margin-bottom:10px;
                border-radius:12px;
                background:#f8f8f8;
            }}
            .lead:hover {{
                background:#eaf7ea;
            }}
            .sendbox {{
                background:white;
                padding:20px;
                border-top:1px solid #ddd;
            }}
            .searchform {{
                display:flex;
                gap:8px;
                margin-bottom:16px;
            }}
            input[type=text], input[name=search] {{
                padding:8px 10px;
                border-radius:8px;
                border:1px solid #ccc;
                flex:1;
            }}
            textarea {{
                width:100%;
                height:70px;
                border-radius:10px;
                padding:12px;
                border:1px solid #ccc;
                font-family:Arial, sans-serif;
                resize:vertical;
            }}
            button {{
                padding:10px 20px;
                border:none;
                background:#25d366;
                color:white;
                border-radius:10px;
                cursor:pointer;
                font-weight:bold;
            }}
            a {{
                text-decoration:none;
                color:black;
                font-weight:bold;
            }}
        </style>
    </head>
    <body>
        <div class="left">
            <h2>SmartVersa CRM</h2>
            <form method="GET" class="searchform">
                <input type="hidden" name="password" value="{password}">
                <input type="text" name="search" placeholder="Search number..." value="{escape_html(search)}">
                <button type="submit">Go</button>
            </form>
            {leads_html}
        </div>

        <div class="right">
            <div class="chat" id="chatBox">
                <h3>Chat: {chat_title}</h3>
                {chat_html}
            </div>

            <div class="sendbox">
                <form method="POST" action="/send_manual" id="sendForm">
                    <input type="hidden" name="password" value="{password}">
                    <input type="hidden" name="phone" value="{escape_html(selected_phone)}">
                    <textarea name="msg" id="msgBox" placeholder="Type message..." required></textarea>
                    <br><br>
                    <button type="submit">Send</button>
                </form>
            </div>
        </div>

        <script>
            (function () {{
                var msgBox = document.getElementById("msgBox");
                var searchBox = document.querySelector("input[name=search]");
                var isTyping = false;

                function markTyping() {{ isTyping = true; }}
                function markNotTyping() {{ isTyping = false; }}

                if (msgBox) {{
                    msgBox.addEventListener("focus", markTyping);
                    msgBox.addEventListener("input", markTyping);
                    msgBox.addEventListener("blur", markNotTyping);
                }}
                if (searchBox) {{
                    searchBox.addEventListener("focus", markTyping);
                    searchBox.addEventListener("input", markTyping);
                    searchBox.addEventListener("blur", markNotTyping);
                }}

                setInterval(function () {{
                    var active = document.activeElement;
                    var userIsTyping = isTyping || active === msgBox || active === searchBox;
                    var hasDraft = msgBox && msgBox.value.trim().length > 0;

                    if (!userIsTyping && !hasDraft) {{
                        window.location.reload();
                    }}
                }}, 20000);
            }})();
        </script>
    </body>
    </html>
    """
    return html_page


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
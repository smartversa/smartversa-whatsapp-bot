from flask import Flask, request, redirect
import os
import json
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

user_sessions = {}

# ================= GOOGLE SHEETS =================
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

creds_json = json.loads(os.getenv("GOOGLE_CREDENTIALS_JSON"))
creds = Credentials.from_service_account_info(creds_json, scopes=scope)
client = gspread.authorize(creds)

sheet_name = os.getenv("GOOGLE_SHEET_NAME")
sheet = client.open(sheet_name).sheet1
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
    save_message(to, sender, text)

    print("STATUS:", response.status_code)
    print("RESPONSE:", response.text)


def send_whatsapp_image(to, image_url, caption=""):
    url = f"https://graph.facebook.com/v23.0/{PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WHATSAPP_TOKEN}",
        "Content-Type": "application/json"
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(to),
        "type": "image",
        "image": {
            "link": image_url,
            "caption": caption
        }
    }

    response = requests.post(url, headers=headers, json=payload)

    save_message(to, "Bot", f"[IMAGE] {caption}")
    print(response.text)


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


@app.route("/")
def home():
    return "SmartVersa Bot Running"

@app.route("/followup")
def run_followup():
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

            hours_passed = (datetime.now() - lead_datetime).total_seconds() / 3600

            phone = row["Phone"]
            name = row["Name"]

            if hours_passed >= 24 and followup1 != "Yes":
                msg = f"""Hi {name} 👋

Need help with enrollment?

Reply anytime 😊"""

                send_whatsapp_message(phone, msg)
                sheet.update_cell(idx, 15, "Yes")

            elif hours_passed >= 72 and followup2 != "Yes":
                msg = f"""Final reminder 😊

Enroll now:
{PAYMENT_URL}"""

                send_whatsapp_message(phone, msg)
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
            print("ERROR:", e)

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


@app.route("/dashboard")
def dashboard():
    password = request.args.get("password")
    search = request.args.get("search", "").strip()

    if password != ADMIN_PASSWORD:
        return """
        <html>
        <body style='font-family:Arial;padding:50px;background:#f4f6fb'>
            <h2>SmartVersa Admin Login</h2>
            <form method='GET'>
                <input type='password' name='password' placeholder='Password'/>
                <button type='submit'>Login</button>
            </form>
        </body>
        </html>
        """

    records = messages_sheet.get_all_records()

    leads = {}
    for row in records:
        phone = str(row["Phone"])
        if search and search not in phone:
            continue
        if phone not in leads:
            leads[phone] = []
        leads[phone].append(row)

    selected_phone = request.args.get("phone")
    chat_html = ""

    if selected_phone and selected_phone in leads:
        for msg in leads[selected_phone]:
            sender = msg["Sender"]
            message = msg["Message"]
            time = msg["Time"]

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
            <div style='text-align:{align};margin:10px'>
                <div style='display:inline-block;background:{bg};padding:12px;border-radius:15px;max-width:70%'>
                    <b>{sender}</b><br>
                    {message}
                    <div style='font-size:11px;color:gray;margin-top:6px'>{time}</div>
                </div>
            </div>
            """

    html = f"""
    <html>
    <head>
    <title>SmartVersa CRM</title>
    <style>
        body {{
            margin:0;
            font-family:Arial;
            display:flex;
            height:100vh;
            background:#ece5dd;
        }}

        .left {{
            width:30%;
            background:white;
            border-right:1px solid #ddd;
            overflow:auto;
            padding:20px;
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
            transition:0.2s;
        }}

        .lead:hover {{
            background:#eaf7ea;
        }}

        .sendbox {{
            background:white;
            padding:20px;
            border-top:1px solid #ddd;
        }}

        textarea {{
            width:100%;
            height:70px;
            border-radius:10px;
            padding:12px;
            border:1px solid #ccc;
        }}

        button {{
            padding:10px 20px;
            border:none;
            background:#25d366;
            color:white;
            border-radius:10px;
            cursor:pointer;
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

            <form method="GET">
                <input type="hidden" name="password" value="{password}">
                <input name="search" placeholder="Search number..." value="{search}">
                <button type="submit">Search</button>
            </form>
            <br>
    """

    for phone in leads:
        html += f"""
        <div class='lead'>
            <a href='/dashboard?password={password}&phone={phone}'>{phone}</a>
        </div>
        """

    html += f"""
    <body>
        <div class="left">
            <h2>SmartVersa CRM</h2>

            <form method="GET">
                <input type="hidden" name="password" value="{password}">
                <input name="search" placeholder="Search number..." value="{request.args.get('search', '')}">
                <button type="submit">Search</button>
            </form>
            <br>
    """

    for phone in leads:
        html += f"""
        <div class='lead'>
            <a href='/dashboard?password={password}&phone={phone}'>{phone}</a>
        </div>
        """

    html += f"""
        </div>

        <div class="right">
            <div class="chat">
                <h3>Chat: {selected_phone if selected_phone else "Select Lead"}</h3>
                {chat_html}
            </div>

            <div class="sendbox">
                <form method="POST" action="/send_manual">
                    <input type="hidden" name="password" value="{password}">
                    <input type="hidden" name="phone" value="{selected_phone if selected_phone else ''}">
                    <textarea name="msg" placeholder="Type message..."></textarea>
                    <br><br>
                    <button type="submit">Send</button>
                </form>
            </div>
        </div>

        <script>
        let isTyping = false;
        const textarea = document.querySelector("textarea");

        if (textarea) {{
            textarea.addEventListener("focus", () => {{
                isTyping = true;
            }});

            textarea.addEventListener("blur", () => {{
                isTyping = false;
            }});

            textarea.addEventListener("input", () => {{
                isTyping = true;
            }});
        }}

        <script>
setInterval(() => {{
    const textarea = document.querySelector("textarea");

    if (!textarea || document.activeElement !== textarea) {{
        location.reload();
    }}
}}, 5000);
</script>

        </script>
    </body>
    </html>
    """
    return html


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)
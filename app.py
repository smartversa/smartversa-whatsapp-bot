from flask import Flask, request
import os
import requests

app = Flask(__name__)

VERIFY_TOKEN = "smartversa_bot_2026"
WHATSAPP_TOKEN = os.environ.get("WHATSAPP_TOKEN")
PHONE_NUMBER_ID = "1207113965816609"


@app.route("/")
def home():
    return "SmartVersa WhatsApp Bot Running!"


@app.route("/webhook", methods=["GET", "POST"])
def webhook():

    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        if mode == "subscribe" and token == VERIFY_TOKEN:
            return challenge, 200
        return "Forbidden", 403

    elif request.method == "POST":
        data = request.get_json(silent=True)
        print("POST DATA:", data)

        try:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            sender = message["from"]
            user_text = message["text"]["body"].lower().strip()

            if user_text in ["hi", "hello", "hey"]:
                reply = """Hi 👋 Welcome to SmartVersa!

We help students become industry-ready 🚀

Choose an option:
1️⃣ AI & Data Science Internship
2️⃣ Digital Marketing Internship
3️⃣ Fees / Pricing
4️⃣ Talk to Human Support"""

            elif user_text == "1":
                reply = """📊 AI & Data Science Internship

✔ Real Projects
✔ Resume Building
✔ Certificate
✔ Career Guidance

Reply:
ENROLL / BACK"""

            elif user_text == "2":
                reply = """📈 Digital Marketing Internship

Learn:
• SEO
• Meta Ads
• Lead Generation
• Social Media Marketing

Reply:
ENROLL / BACK"""

            elif user_text in ["3", "fees", "price", "pricing"]:
                reply = """💰 SmartVersa Pricing

AI & Data Science Internship: ₹899
Digital Marketing Internship: ₹4999

Reply ENROLL to join."""

            elif user_text in ["4", "human", "support"]:
                reply = "Our support team will contact you shortly 😊"

            elif user_text == "enroll":
                reply = "Please complete registration here: https://pay.smartversa.in"

            elif user_text == "back":
                reply = """Main Menu:

1️⃣ AI Internship
2️⃣ Digital Marketing
3️⃣ Fees
4️⃣ Human Support"""

            else:
                reply = """I didn't understand that 🤔

Please choose:
1 / 2 / 3 / 4"""

            send_whatsapp_message(sender, reply)

        except Exception as e:
            print("ERROR:", str(e))

        return "OK", 200


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
        "text": {
            "body": text
        }
    }

    response = requests.post(url, headers=headers, json=payload)
    print(response.status_code, response.text)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    app.run(host="0.0.0.0", port=port)

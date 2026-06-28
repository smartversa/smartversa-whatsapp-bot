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
    print("\n===== NEW REQUEST =====")
    print("METHOD:", request.method)
    print("FULL URL:", request.url)
    print("ARGS:", request.args)

    # Webhook verification
    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        print("MODE:", mode)
        print("TOKEN:", token)
        print("CHALLENGE:", challenge)

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("✅ VERIFIED SUCCESS")
            return challenge, 200
        else:
            print("❌ VERIFICATION FAILED")
            return "Forbidden", 403

    # Incoming message
    elif request.method == "POST":
        data = request.get_json(silent=True)
        print("POST DATA:", data)

        try:
            message = data["entry"][0]["changes"][0]["value"]["messages"][0]
            sender = message["from"]

            send_whatsapp_message(
                sender,
                "Hello from SmartVersa Bot 🚀"
            )

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

    print("SEND STATUS:", response.status_code)
    print("SEND RESPONSE:", response.text)


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    print("🚀 RUNNING THIS APP.PY")
    app.run(host="0.0.0.0", port=port, debug=False)

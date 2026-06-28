from flask import Flask, request

app = Flask(__name__)

@app.route("/")
def home():
    return "SmartVersa WhatsApp Bot Running!"

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    print("\n===== NEW REQUEST =====")
    print("METHOD:", request.method)
    print("FULL URL:", request.url)
    print("ARGS:", request.args)

    if request.method == "GET":
        mode = request.args.get("hub.mode")
        token = request.args.get("hub.verify_token")
        challenge = request.args.get("hub.challenge")

        print("MODE:", repr(mode))
        print("TOKEN:", repr(token))
        print("CHALLENGE:", repr(challenge))

        VERIFY_TOKEN = "smartversa_bot_2026"

        if mode == "subscribe" and token == VERIFY_TOKEN:
            print("✅ VERIFIED SUCCESS")
            return challenge, 200
        else:
            print("❌ VERIFICATION FAILED")
            return "Forbidden", 403

    elif request.method == "POST":
        data = request.get_json(silent=True)
        print("POST DATA:", data)
        return "OK", 200


if __name__ == "__main__":
    print("🚀 RUNNING THIS APP.PY")
    app.run(host="0.0.0.0", port=3000, debug=False)
"""
SmartVersa knowledge base + FAQ engine + intent detection + lead scoring.

This runs with zero AI cost. The optional AI counsellor (ai.py) uses this same
knowledge base as grounding, so answers stay consistent whether AI is on or off.
"""

import re

from config import Config

# --------------------------------------------------------------------------- #
# Courses
# --------------------------------------------------------------------------- #
COURSES = {
    "1": {
        "name": "AI & Data Science",
        "price": 1299,
        "image": Config.AI_IMAGE_URL,
        "duration": "Self-paced with live-style project guidance",
        "level": "Beginner to Intermediate (no coding required)",
        "modules": [
            "AI Foundation (AI, ML, Data Science basics)",
            "Python Basics",
            "Data Analysis (Pandas, cleaning, visualization)",
            "SQL (SELECT, WHERE, GROUP BY, aggregates)",
            "Power BI (dashboards, publishing)",
        ],
        "projects": ["Sales Dashboard (Power BI)", "Python Data Analysis project"],
        "roles": ["Data Analyst Intern", "Junior Analyst", "BI Analyst"],
        "details": (
            "🤖 *AI & Data Science Program*\n\n"
            "✔ Python from scratch\n"
            "✔ Data Analysis (Pandas)\n"
            "✔ SQL + Power BI dashboards\n"
            "✔ Machine Learning basics\n"
            "✔ 2 real-world projects\n"
            "✔ Internship-style experience\n"
            "✔ Resume & portfolio building\n\n"
            "👨‍🎓 Best for: students, freshers, career switchers (no coding needed)\n"
            "💰 Price: ₹1299"
        ),
    },
    "2": {
        "name": "Digital Marketing",
        "price": 4999,
        "image": Config.DM_IMAGE_URL,
        "duration": "Self-paced with real project work",
        "level": "Beginner to Advanced (no experience required)",
        "modules": [
            "Digital Marketing Foundations",
            "Facebook / Instagram / Quora Marketing",
            "Social Media Strategy & Content Marketing",
            "Branding & Audience Growth",
            "Lead Generation & Conversion Funnels",
        ],
        "projects": [
            "Social Media Growth Strategy",
            "Meta Ads Campaign",
            "SEO Audit & Keyword Research",
            "Lead Generation Funnel",
        ],
        "roles": ["Social Media Manager", "Digital Marketer", "Freelancer", "Growth Marketer"],
        "details": (
            "📈 *Digital Marketing Program*\n\n"
            "✔ Facebook / Instagram / Meta Ads\n"
            "✔ SEO + content marketing\n"
            "✔ Branding & audience growth\n"
            "✔ Lead generation & funnels\n"
            "✔ 4 real projects\n"
            "✔ Freelancing focused\n\n"
            "👨‍🎓 Best for: students, freelancers, creators, business owners\n"
            "💰 Price: ₹4999"
        ),
    },
}


def course_by_choice(choice):
    if choice == "3":
        both = (
            "🎯 *SmartVersa Programs*\n\n"
            "🤖 AI & Data Science — ₹1299\n"
            "📈 Digital Marketing — ₹4999\n\n"
            "Reply *1* or *2* to see full details."
        )
        return {"name": "Both", "image": Config.AI_IMAGE_URL, "details": both}
    return COURSES.get(choice)


# --------------------------------------------------------------------------- #
# Intent detection
# --------------------------------------------------------------------------- #
INTENT_KEYWORDS = {
    "price":       ["price", "fee", "fees", "cost", "kitna", "kitne", "paisa", "rupees", "₹", "charge", "amount"],
    "duration":    ["duration", "how long", "kitne din", "kitna time", "months", "weeks", "time lagega"],
    "syllabus":    ["syllabus", "curriculum", "modules", "topics", "content", "kya sikhaya", "what will i learn"],
    "certificate": ["certificate", "certification", "certi", "internship certificate"],
    "internship":  ["internship", "intern", "job guarantee", "experience letter"],
    "refund":      ["refund", "money back", "cancel", "return"],
    "placement":   ["placement", "job", "naukri", "hiring", "salary", "package", "career"],
    "timing":      ["timing", "schedule", "class time", "kab", "when", "live class", "recording"],
    "payment":     ["pay", "payment", "buy", "enroll", "enrol", "join", "purchase", "khareed", "payment link", "how to pay"],
    "prerequisite":["prerequisite", "coding required", "programming", "background", "eligibility", "qualification"],
    "restart":     ["restart", "start over", "reset", "menu", "start again", "shuru"],
    "human":       ["counsellor", "counselor", "human", "agent", "talk to", "call me", "baat karni"],
    "greeting":    ["hi", "hello", "hey", "namaste", "hii", "helo", "start"],
}

# Scoring per the brief
INTENT_SCORE = {
    "price": 10,
    "certificate": 15,
    "payment": 40,
    "internship": 10,
    "placement": 8,
    "syllabus": 5,
}


def detect_intents(text: str):
    t = (text or "").lower()
    found = set()
    for intent, kws in INTENT_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                found.add(intent)
                break
    return found


def score_for(intents) -> int:
    return sum(INTENT_SCORE.get(i, 0) for i in intents)


# --------------------------------------------------------------------------- #
# Language detection (Hindi / English / Hinglish)
# --------------------------------------------------------------------------- #
_HINDI_ROMAN = ["kitna", "kitne", "hai", "kya", "aap", "mujhe", "chahiye",
                "batao", "paisa", "naukri", "kaise", "karna", "shuru", "baat"]


def detect_language(text: str, fallback="English") -> str:
    if not text:
        return fallback
    if re.search(r"[\u0900-\u097F]", text):   # Devanagari
        return "Hindi"
    low = text.lower()
    if any(w in low for w in _HINDI_ROMAN):
        return "Hinglish"
    return fallback


# --------------------------------------------------------------------------- #
# FAQ answers (multilingual)
# --------------------------------------------------------------------------- #
def faq_answer(intent: str, language: str) -> str:
    ai = COURSES["1"]
    dm = COURSES["2"]
    lang = language or "English"

    table = {
        "price": {
            "English": f"💰 Course fees:\n• AI & Data Science — ₹{ai['price']}\n• Digital Marketing — ₹{dm['price']}",
            "Hindi":   f"💰 कोर्स फीस:\n• AI & Data Science — ₹{ai['price']}\n• Digital Marketing — ₹{dm['price']}",
            "Hinglish":f"💰 Course fees:\n• AI & Data Science — ₹{ai['price']}\n• Digital Marketing — ₹{dm['price']}",
        },
        "duration": {
            "English": "⏳ Both programs are self-paced with project guidance, so you can finish at your own speed.",
            "Hindi":   "⏳ दोनों प्रोग्राम self-paced हैं, आप अपनी speed से project guidance के साथ complete कर सकते हैं।",
            "Hinglish":"⏳ Dono programs self-paced hain — apni speed se project guidance ke saath complete kar sakte ho.",
        },
        "certificate": {
            "English": "🏅 Yes — you get an internship-style certificate (issued with company stamp & signature) on completion.",
            "Hindi":   "🏅 हाँ — course complete करने पर आपको internship certificate मिलता है (company stamp और signature के साth)।",
            "Hinglish":"🏅 Haan — completion par internship certificate milta hai (company stamp & signature ke saath).",
        },
        "internship": {
            "English": "💼 Both programs are internship-style with real projects, so you build actual work experience.",
            "Hindi":   "💼 दोनों प्रोग्राम internship-style हैं, real projects के साथ — जिससे actual experience बनता है।",
            "Hinglish":"💼 Dono programs internship-style hain, real projects ke saath — actual experience banta hai.",
        },
        "refund": {
            "English": "🔁 For any refund or cancellation query, our counsellor will help you directly. Shall I connect you?",
            "Hindi":   "🔁 Refund/cancellation के लिए हमारा counsellor आपकी help करेगा। क्या मैं connect करूँ?",
            "Hinglish":"🔁 Refund/cancellation ke liye counsellor directly help karega. Connect karun?",
        },
        "placement": {
            "English": ("🚀 You'll be job-ready for roles like "
                        f"{', '.join(ai['roles'][:2])} (AI track) or "
                        f"{', '.join(dm['roles'][:2])} (Marketing track), with a portfolio to show."),
            "Hindi":   ("🚀 Course के बाद आप job-ready होंगे — जैसे "
                        f"{', '.join(ai['roles'][:2])} या {', '.join(dm['roles'][:2])} — portfolio के साth।"),
            "Hinglish":("🚀 Course ke baad job-ready ban jaoge — jaise "
                        f"{', '.join(ai['roles'][:2])} ya {', '.join(dm['roles'][:2])} — portfolio ke saath."),
        },
        "timing": {
            "English": "🕒 It's flexible — self-paced learning with recordings, so you study whenever suits you.",
            "Hindi":   "🕒 Timing flexible है — recordings के साth self-paced, जब चाहें पढ़ें।",
            "Hinglish":"🕒 Timing flexible hai — recordings ke saath self-paced, jab chaaho padho.",
        },
        "prerequisite": {
            "English": "✅ No coding or prior experience needed — both programs start from absolute basics.",
            "Hindi":   "✅ कोई coding या experience ज़रूरी नहीं — दोनों programs बिल्कुल basics से start होते हैं।",
            "Hinglish":"✅ Koi coding ya experience zaroori nahi — dono programs basics se start hote hain.",
        },
        "syllabus": {
            "English": ("📚 AI & Data Science: " + "; ".join(ai["modules"]) +
                        "\n\n📚 Digital Marketing: " + "; ".join(dm["modules"])),
            "Hindi":   ("📚 AI & Data Science: " + "; ".join(ai["modules"]) +
                        "\n\n📚 Digital Marketing: " + "; ".join(dm["modules"])),
            "Hinglish":("📚 AI & Data Science: " + "; ".join(ai["modules"]) +
                        "\n\n📚 Digital Marketing: " + "; ".join(dm["modules"])),
        },
        "payment": {
            "English": f"✅ You can enroll here:\n{Config.PAYMENT_URL}\n\nNeed help completing it? Just ask.",
            "Hindi":   f"✅ यहाँ से enroll करें:\n{Config.PAYMENT_URL}\n\nकोई help चाहिए तो बताइए।",
            "Hinglish":f"✅ Yahan se enroll karo:\n{Config.PAYMENT_URL}\n\nKoi help chahiye toh batao.",
        },
    }

    entry = table.get(intent)
    if not entry:
        return ""
    return entry.get(lang, entry.get("English", ""))


# --------------------------------------------------------------------------- #
# Course recommendation heuristic
# --------------------------------------------------------------------------- #
def recommend_course(text: str) -> str:
    t = (text or "").lower()
    technical = any(w in t for w in
                    ["data", "python", "coding", "analyst", "sql", "analytics", "ai", "machine"])
    marketing = any(w in t for w in
                    ["marketing", "social", "instagram", "ads", "freelanc", "business", "content", "brand"])
    if technical and not marketing:
        return "1"
    if marketing and not technical:
        return "2"
    # Beginner with no clear technical signal -> Digital Marketing (lower barrier)
    return "2"

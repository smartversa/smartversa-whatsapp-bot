"""
SmartVersa knowledge base + FAQ engine + intent detection + lead scoring.

This runs with zero AI cost. The optional AI counsellor (ai.py) uses this same
knowledge base as grounding, so answers stay consistent whether AI is on or off.
"""

import re

from config import Config

# --------------------------------------------------------------------------- #
# Company
# --------------------------------------------------------------------------- #
COMPANY = {
    "name": "SmartVersa",
    "registration": "Active MSME-registered company",
    "location": "Haryana, India",
    "website": "https://smartversa.in",
    "support_email": "team@smartversa.in",
    "whatsapp_support": "+91 9306539879",
    "support_hours": "10:00 AM to 7:00 PM (IST)",
    "response_time": "2–3 hours (typical)",
}

# --------------------------------------------------------------------------- #
# Courses
# --------------------------------------------------------------------------- #
COURSES = {
    "1": {
        "name": "AI & Data Science",
        "price": 1299,
        "image": Config.AI_IMAGE_URL,
        "duration": "Self-paced, recorded classes only — complete at your own speed",
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
        "includes": ["Certificate issued by SmartVersa", "Internship", "Real Projects"],
        "details": (
            "🤖 *AI & Data Science Program*\n\n"
            "✔ Python from scratch\n"
            "✔ Data Analysis (Pandas)\n"
            "✔ SQL + Power BI dashboards\n"
            "✔ Machine Learning basics\n"
            "✔ 2 real-world projects\n"
            "✔ Internship\n"
            "✔ Certificate issued by SmartVersa\n"
            "✔ Recorded classes — 100% self-paced\n\n"
            "👨‍🎓 Best for: students, freshers, career switchers (no coding needed)\n"
            "💰 Price: ₹1299 (GST included)"
        ),
    },
    "2": {
        "name": "Digital Marketing",
        "price": 4999,
        "image": Config.DM_IMAGE_URL,
        "duration": "Self-paced, recorded classes only — complete at your own speed",
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
        "includes": ["Certificate issued by SmartVersa", "Internship", "Real Projects"],
        "details": (
            "📈 *Digital Marketing Program*\n\n"
            "✔ Facebook / Instagram / Meta Ads\n"
            "✔ SEO + content marketing\n"
            "✔ Branding & audience growth\n"
            "✔ Lead generation & funnels\n"
            "✔ 4 real projects\n"
            "✔ Internship\n"
            "✔ Certificate issued by SmartVersa\n"
            "✔ Recorded classes — 100% self-paced\n\n"
            "👨‍🎓 Best for: students, freelancers, creators, business owners\n"
            "💰 Price: ₹4999 (GST included)"
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
# Placement support (confirmed scope — never promise guaranteed jobs)
# --------------------------------------------------------------------------- #
PLACEMENT_SUPPORT = [
    "Resume Building",
    "Resume Review",
    "LinkedIn Optimization",
    "Interview Preparation",
    "Career Guidance",
]

# --------------------------------------------------------------------------- #
# Refund policy (confirmed — never promise automatic refunds)
# --------------------------------------------------------------------------- #
REFUND_POLICY = (
    "Refunds are available only for valid and genuine reasons, after review by the "
    "SmartVersa team. Refunds are not automatic."
)

# --------------------------------------------------------------------------- #
# Payment (confirmed)
# --------------------------------------------------------------------------- #
PAYMENT_INFO = {
    "gateway": "Razorpay",
    "gst_included": True,
}


# --------------------------------------------------------------------------- #
# Intent detection
# --------------------------------------------------------------------------- #
INTENT_KEYWORDS = {
    "price":       ["price", "fee", "fees", "cost", "kitna", "kitne", "paisa", "rupees", "₹", "charge", "amount", "gst", "tax"],
    "duration":    ["duration", "how long", "kitne din", "kitna time", "months", "weeks", "time lagega"],
    "syllabus":    ["syllabus", "curriculum", "modules", "topics", "content", "kya sikhaya", "what will i learn"],
    "certificate": ["certificate", "certification", "certi", "internship certificate"],
    "internship":  ["internship", "intern", "job guarantee", "experience letter"],
    "refund":      ["refund", "money back", "cancel", "return"],
    "placement":   ["placement", "job", "naukri", "hiring", "salary", "package", "career", "resume", "linkedin", "interview prep", "interview preparation"],
    "timing":      ["timing", "schedule", "class time", "kab", "when", "live class", "recording", "recorded"],
    "payment":     ["pay", "payment", "buy", "enroll", "enrol", "join", "purchase", "khareed", "payment link", "how to pay", "razorpay", "upi", "card"],
    "prerequisite":["prerequisite", "coding required", "programming", "background", "eligibility", "qualification"],
    "restart":     ["restart", "start over", "reset", "menu", "start again", "shuru"],
    "human":       ["counsellor", "counselor", "human", "agent", "talk to", "call me", "baat karni"],
    "greeting":    ["hi", "hello", "hey", "namaste", "hii", "helo", "start"],
    "about":       ["about smartversa", "who are you", "company details", "genuine company",
                    "trustworthy", "is this legit", "legit", "scam", "fraud", "registered company",
                    "msme", "location", "address", "where are you located", "website"],
    "support":     ["support", "contact you", "helpdesk", "help desk", "response time",
                    "working hours", "office hours", "customer care", "reach you", "email id",
                    "whatsapp number", "support email"],
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
            "English": f"💰 Course fees (GST included):\n• AI & Data Science — ₹{ai['price']}\n• Digital Marketing — ₹{dm['price']}",
            "Hindi":   f"💰 कोर्स फीस (GST शामिल):\n• AI & Data Science — ₹{ai['price']}\n• Digital Marketing — ₹{dm['price']}",
            "Hinglish":f"💰 Course fees (GST included):\n• AI & Data Science — ₹{ai['price']}\n• Digital Marketing — ₹{dm['price']}",
        },
        "duration": {
            "English": "⏳ Classes are recorded only (no live classes) and fully self-paced — completion time depends on your own learning speed.",
            "Hindi":   "⏳ Classes recorded हैं (कोई live class नहीं) और पूरी तरह self-paced — completion आपकी अपनी speed पर depend करता है।",
            "Hinglish":"⏳ Classes recorded hain (koi live class nahi) aur fully self-paced — completion aapki apni speed par depend karta hai.",
        },
        "certificate": {
            "English": "🏅 Yes — you get a certificate issued by SmartVersa on completion of the course.",
            "Hindi":   "🏅 हाँ — course complete करने पर SmartVersa की तरफ से certificate मिलता है।",
            "Hinglish":"🏅 Haan — course complete karne par SmartVersa ki taraf se certificate milta hai.",
        },
        "internship": {
            "English": "💼 Both programs include an internship along with real projects, so you build actual work experience.",
            "Hindi":   "💼 दोनों programs में internship included है, real projects के साथ — जिससे actual experience बनता है।",
            "Hinglish":"💼 Dono programs mein internship included hai, real projects ke saath — actual experience banta hai.",
        },
        "refund": {
            "English": f"🔁 {REFUND_POLICY} Would you like me to connect you with our counsellor to review your case?",
            "Hindi":   f"🔁 Refund सिर्फ valid और genuine reasons के लिए, review के बाद दिया जाता है — automatic नहीं। क्या counsellor से connect करूँ?",
            "Hinglish":f"🔁 Refund sirf valid aur genuine reasons ke liye, review ke baad diya jaata hai — automatic nahi. Counsellor se connect karun?",
        },
        "placement": {
            "English": ("🚀 SmartVersa provides placement support: " + ", ".join(PLACEMENT_SUPPORT) +
                        ". We can't guarantee jobs or placements, but we help you become genuinely job-ready "
                        f"for roles like {', '.join(ai['roles'][:2])} (AI track) or {', '.join(dm['roles'][:2])} (Marketing track)."),
            "Hindi":   ("🚀 SmartVersa placement support देता है: " + ", ".join(PLACEMENT_SUPPORT) +
                        "। हम guaranteed job/placement का वादा नहीं करते, लेकिन आपको job-ready बनाते हैं — जैसे "
                        f"{', '.join(ai['roles'][:2])} या {', '.join(dm['roles'][:2])}।"),
            "Hinglish":("🚀 SmartVersa placement support deta hai: " + ", ".join(PLACEMENT_SUPPORT) +
                        ". Hum guaranteed job/placement ka wada nahi karte, lekin job-ready banate hain — jaise "
                        f"{', '.join(ai['roles'][:2])} ya {', '.join(dm['roles'][:2])}."),
        },
        "timing": {
            "English": "🕒 There are no live classes — all sessions are pre-recorded, so you can study whenever suits you.",
            "Hindi":   "🕒 कोई live class नहीं है — सारी classes recorded हैं, जब चाहें पढ़ें।",
            "Hinglish":"🕒 Koi live class nahi hai — saari classes recorded hain, jab chaaho padho.",
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
            "English": f"✅ You can enroll here (secure Razorpay payment, GST included):\n{Config.PAYMENT_URL}\n\nNeed help completing it? Just ask.",
            "Hindi":   f"✅ यहाँ से enroll करें (Razorpay से secure payment, GST included):\n{Config.PAYMENT_URL}\n\nकोई help चाहिए तो बताइए।",
            "Hinglish":f"✅ Yahan se enroll karo (Razorpay se secure payment, GST included):\n{Config.PAYMENT_URL}\n\nKoi help chahiye toh batao.",
        },
        "about": {
            "English": (f"🏢 *{COMPANY['name']}* is an {COMPANY['registration']}, based in {COMPANY['location']}.\n"
                        f"🌐 {COMPANY['website']}\n"
                        f"📧 {COMPANY['support_email']}"),
            "Hindi":   (f"🏢 *{COMPANY['name']}* एक {COMPANY['registration']} है, {COMPANY['location']} में based।\n"
                        f"🌐 {COMPANY['website']}\n"
                        f"📧 {COMPANY['support_email']}"),
            "Hinglish":(f"🏢 *{COMPANY['name']}* ek {COMPANY['registration']} hai, {COMPANY['location']} mein based.\n"
                        f"🌐 {COMPANY['website']}\n"
                        f"📧 {COMPANY['support_email']}"),
        },
        "support": {
            "English": (f"🙋 You can reach our support team:\n📧 {COMPANY['support_email']}\n"
                        f"📱 WhatsApp: {COMPANY['whatsapp_support']}\n"
                        f"🕒 Working hours: {COMPANY['support_hours']}\n"
                        f"⏱ Typical response time: {COMPANY['response_time']}"),
            "Hindi":   (f"🙋 हमारी support team से यहाँ संपर्क करें:\n📧 {COMPANY['support_email']}\n"
                        f"📱 WhatsApp: {COMPANY['whatsapp_support']}\n"
                        f"🕒 Working hours: {COMPANY['support_hours']}\n"
                        f"⏱ Typical response time: {COMPANY['response_time']}"),
            "Hinglish":(f"🙋 Hamari support team se yahan contact karo:\n📧 {COMPANY['support_email']}\n"
                        f"📱 WhatsApp: {COMPANY['whatsapp_support']}\n"
                        f"🕒 Working hours: {COMPANY['support_hours']}\n"
                        f"⏱ Typical response time: {COMPANY['response_time']}"),
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

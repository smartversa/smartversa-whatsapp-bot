"""
SmartVersa knowledge base + FAQ engine + intent detection + lead scoring.

This runs with zero AI cost. The optional AI counsellor (ai.py) uses this same
knowledge base as grounding, so answers stay consistent whether AI is on or off.

Production notes:
- Every fact in this file is confirmed SmartVersa information. Nothing here is
  invented (no made-up policies, discounts, offers, guarantees, or steps).
- Where exact operational detail isn't confirmed (e.g. device specs, demo
  availability, assignment structure), the FAQ answer says so plainly and
  offers to connect the student with a human counsellor instead of guessing.
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
        "tools": ["Python", "Pandas", "SQL", "Power BI"],
        "target_audience": "Students, freshers, and career switchers — no coding background needed",
        "prerequisites": "No coding or prior experience required",
        "benefits": [
            "Hands-on real projects",
            "Internship experience",
            "Certificate issued by SmartVersa",
            "Learn fully at your own pace",
        ],
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
        "tools": ["Meta Ads Manager", "Instagram/Facebook", "SEO tools", "Content planning tools"],
        "target_audience": "Students, freelancers, creators, and business owners",
        "prerequisites": "No coding or prior experience required",
        "benefits": [
            "Hands-on real campaigns/projects",
            "Internship experience",
            "Certificate issued by SmartVersa",
            "Learn fully at your own pace",
        ],
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
    "enrollment_process": "Pay securely through the Razorpay payment link — GST is already included in the listed price.",
    "payment_confirmation": "Razorpay confirms your payment instantly once the transaction succeeds.",
    "after_payment_process": (
        "After payment, the SmartVersa team reaches out to guide you further. "
        "If you don't hear back, you can contact support directly."
    ),
}


# --------------------------------------------------------------------------- #
# Intent detection
# --------------------------------------------------------------------------- #
INTENT_KEYWORDS = {
    "price":       ["price", "fee", "fees", "cost", "kitna", "kitne", "paisa", "rupees", "₹", "charge", "amount", "gst", "tax"],
    "duration":    ["duration", "how long", "kitne din", "kitna time", "months", "weeks", "time lagega", "self-paced", "self paced"],
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
    "greeting":    ["hi", "hello", "hey", "namaste", "hii", "helo", "start",
                    "good morning", "good afternoon", "good evening"],
    "about":       ["about smartversa", "who are you", "company details", "genuine company",
                    "trustworthy", "is this legit", "legit", "scam", "fraud", "registered company",
                    "msme", "location", "address", "where are you located", "website"],
    "support":     ["support", "contact you", "helpdesk", "help desk", "response time",
                    "working hours", "office hours", "customer care", "reach you", "email id",
                    "whatsapp number", "support email"],
    "comparison":  ["difference between", "which course is better", "compare", "vs", "versus",
                    "better course", "which one should i choose", "which is better",
                    "which course should i take", "dono me kya difference"],
    "beginner_doubt": ["beginner", "no experience", "never coded", "can i do this",
                    "am i eligible for this", "new to this", "confuse", "confused", "doubt",
                    "not sure if i can", "mujhe nahi aata", "will i understand"],
    "parents":     ["parents", "mom", "dad", "papa", "mummy", "family", "convince my parents",
                    "parents allow", "parents agree", "parents not allowing", "ghar wale"],
    "after_payment": ["after payment", "after paying", "what after enroll", "next steps",
                    "after enrolling", "payment done", "already paid", "how to start after payment",
                    "what happens after payment", "payment ho gaya"],
    "small_talk":  ["how are you", "what's up", "whats up", "who made you", "are you a bot",
                    "are you human", "your name", "kaise ho", "kaisi ho", "aap kaun ho"],
    "objection":   ["too expensive", "mehenga", "no time", "not sure", "think about it",
                    "later", "abhi nahi", "sochna hai", "busy", "expensive", "i'll think"],
    "projects":    ["projects", "project work", "real project", "hands-on project", "portfolio project"],
    "device_requirement": ["laptop", "laptop required", "computer required", "device needed",
                    "system requirement", "pc required", "mobile se ho jayega"],
    "stream_eligibility": ["commerce student", "arts student", "science student", "any stream",
                    "bcom", "b.com", "ba student", "bsc student", "12th", "non-tech background",
                    "humanities student"],
    "assignments": ["assignment", "assessment", "quiz", "evaluation test"],
    "experienced": ["already know coding", "already working", "i already know", "experienced in",
                    "i have experience", "already a developer", "already do marketing",
                    "already working professional"],
    "demo":        ["demo", "free trial", "trial class", "sample class", "preview class"],
    "thanks":      ["thanks", "thank you", "thnx", "shukriya", "dhanyawad"],
    "acknowledge": ["okay", "fine", "alright", "acha", "theek hai", "sahi hai"],
    "farewell":    ["bye", "goodbye", "see you", "tata", "milte hain", "chalta hoon"],
}

# Scoring per the brief — reflects buying intent strength
INTENT_SCORE = {
    "price": 10,
    "certificate": 15,
    "payment": 40,
    "internship": 10,
    "placement": 8,
    "syllabus": 5,
    "after_payment": 25,
    "comparison": 5,
    "projects": 5,
    "experienced": 5,
}


def detect_intents(text: str):
    """Word-boundary aware keyword matching to avoid false positives
    (e.g. 'hi' no longer matches inside 'this', 'ok' no longer matches inside 'smoke')."""
    t = (text or "").lower()
    found = set()
    for intent, kws in INTENT_KEYWORDS.items():
        for kw in kws:
            pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
            if re.search(pattern, t):
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
            "Hindi":   "🔁 Refund सिर्फ valid और genuine reasons के लिए, review के बाद दिया जाता है — automatic नहीं। क्या counsellor से connect करूँ?",
            "Hinglish":"🔁 Refund sirf valid aur genuine reasons ke liye, review ke baad diya jaata hai — automatic nahi. Counsellor se connect karun?",
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
            "English": (f"✅ You can enroll here (secure Razorpay payment, GST included):\n{Config.PAYMENT_URL}\n\n"
                        f"{PAYMENT_INFO['payment_confirmation']} Need help completing it? Just ask."),
            "Hindi":   (f"✅ यहाँ से enroll करें (Razorpay से secure payment, GST included):\n{Config.PAYMENT_URL}\n\n"
                        "Payment successful होते ही Razorpay confirm कर देता है। कोई help चाहिए तो बताइए।"),
            "Hinglish":(f"✅ Yahan se enroll karo (Razorpay se secure payment, GST included):\n{Config.PAYMENT_URL}\n\n"
                        "Payment successful hote hi Razorpay confirm kar deta hai. Koi help chahiye toh batao."),
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
        "greeting": {
            "English": "👋 Hey there! I'm SmartVersa's assistant. I can help with course details, pricing, or connect you to a counsellor — what would you like to know?",
            "Hindi":   "👋 नमस्ते! मैं SmartVersa का assistant हूँ। Course details, pricing, या counsellor से connect — जो चाहें पूछिए।",
            "Hinglish":"👋 Hey! Main SmartVersa ka assistant hoon. Course details, pricing, ya counsellor se connect — jo bhi chahiye poochho.",
        },
        "comparison": {
            "English": ("🤔 Quick comparison:\n"
                        f"• *AI & Data Science* — ₹{ai['price']}, {ai['level']}. Roles: {', '.join(ai['roles'][:2])}.\n"
                        f"• *Digital Marketing* — ₹{dm['price']}, {dm['level']}. Roles: {', '.join(dm['roles'][:2])}.\n"
                        "Both include a certificate, internship and real projects. Want a recommendation based on your interest?"),
            "Hindi":   ("🤔 Quick comparison:\n"
                        f"• *AI & Data Science* — ₹{ai['price']}, {ai['level']}. Roles: {', '.join(ai['roles'][:2])}.\n"
                        f"• *Digital Marketing* — ₹{dm['price']}, {dm['level']}. Roles: {', '.join(dm['roles'][:2])}.\n"
                        "दोनों में certificate, internship और real projects शामिल हैं। आपके interest के हिसाब से recommendation चाहिए?"),
            "Hinglish":("🤔 Quick comparison:\n"
                        f"• *AI & Data Science* — ₹{ai['price']}, {ai['level']}. Roles: {', '.join(ai['roles'][:2])}.\n"
                        f"• *Digital Marketing* — ₹{dm['price']}, {dm['level']}. Roles: {', '.join(dm['roles'][:2])}.\n"
                        "Dono mein certificate, internship aur real projects included hain. Aapke interest ke hisaab se recommendation chahiye?"),
        },
        "beginner_doubt": {
            "English": "😊 No worries at all — both programs are built for complete beginners. No coding or prior experience needed; you start from the basics and build real projects step by step.",
            "Hindi":   "😊 कोई चिंता नहीं — दोनों programs beginners के लिए बने हैं। कोई coding या experience ज़रूरी नहीं, basics से शुरू होकर real projects step by step बनाते हैं।",
            "Hinglish":"😊 Koi tension nahi — dono programs beginners ke liye hi bane hain. Koi coding ya experience zaroori nahi, basics se shuru karke real projects step by step banate ho.",
        },
        "parents": {
            "English": (f"👨‍👩‍👧 Totally understandable! *{COMPANY['name']}* is an {COMPANY['registration']}, based in {COMPANY['location']} "
                        f"({COMPANY['website']}). Both programs include a certificate, internship and real projects — "
                        "happy to share more details you can show your parents, or connect them directly with our counsellor."),
            "Hindi":   (f"👨‍👩‍👧 बिल्कुल समझ सकता हूँ! *{COMPANY['name']}* एक {COMPANY['registration']} है, {COMPANY['location']} में based "
                        f"({COMPANY['website']})। दोनों programs में certificate, internship और real projects शामिल हैं — "
                        "आपके parents को दिखाने के लिए details दे सकता हूँ, या सीधे counsellor से बात करवा सकता हूँ।"),
            "Hinglish":(f"👨‍👩‍👧 Bilkul samajh sakta hoon! *{COMPANY['name']}* ek {COMPANY['registration']} hai, {COMPANY['location']} mein based "
                        f"({COMPANY['website']}). Dono programs mein certificate, internship aur real projects included hain — "
                        "parents ko dikhane ke liye details de sakta hoon, ya seedha counsellor se baat karva sakta hoon."),
        },
        "after_payment": {
            "English": (f"✅ {PAYMENT_INFO['after_payment_process']} "
                        f"WhatsApp us at {COMPANY['whatsapp_support']} or email {COMPANY['support_email']} "
                        f"({COMPANY['support_hours']}, typical response time {COMPANY['response_time']}). "
                        "I can also connect you with a counsellor for the exact next steps."),
            "Hindi":   (f"✅ Payment के बाद हमारी team आपसे guide करने के लिए contact करेगी। अगर response ना मिले तो "
                        f"WhatsApp करें {COMPANY['whatsapp_support']} या email करें {COMPANY['support_email']} "
                        f"({COMPANY['support_hours']}, response time {COMPANY['response_time']})। "
                        "मैं counsellor से भी connect करवा सकता हूँ।"),
            "Hinglish":(f"✅ Payment ke baad hamari team aapse guide karne ke liye contact karegi. Response na mile toh "
                        f"WhatsApp karo {COMPANY['whatsapp_support']} ya email karo {COMPANY['support_email']} "
                        f"({COMPANY['support_hours']}, response time {COMPANY['response_time']}). "
                        "Main counsellor se bhi connect karva sakta hoon."),
        },
        "small_talk": {
            "English": "😄 I'm doing great, thanks for asking! I'm SmartVersa's AI assistant, here to help with our AI & Data Science and Digital Marketing programs. What would you like to know?",
            "Hindi":   "😄 मैं बढ़िया हूँ, पूछने के लिए धन्यवाद! मैं SmartVersa का AI assistant हूँ, AI & Data Science और Digital Marketing programs में help करने के लिए। क्या जानना चाहेंगे?",
            "Hinglish":"😄 Main badhiya hoon, poochne ke liye thanks! Main SmartVersa ka AI assistant hoon, AI & Data Science aur Digital Marketing programs mein help karne ke liye. Kya jaanna chahoge?",
        },
        "objection": {
            "English": ("💡 Totally fair. Our programs are self-paced (recorded classes), so you learn at your own speed, and the fee "
                        "(GST included) covers a certificate, internship and real projects — no hidden costs. Take your time, "
                        "I'm here whenever you have questions!"),
            "Hindi":   ("💡 समझ सकता हूँ। हमारे programs self-paced (recorded classes) हैं, अपनी speed से पढ़ सकते हैं, और fee "
                        "(GST included) में certificate, internship और real projects शामिल हैं — कोई hidden cost नहीं। "
                        "अपना समय लीजिए, कोई सवाल हो तो बताइए!"),
            "Hinglish":("💡 Samajh sakta hoon. Hamare programs self-paced (recorded classes) hain, apni speed se padh sakte ho, aur fee "
                        "(GST included) mein certificate, internship aur real projects included hain — koi hidden cost nahi. "
                        "Apna time lo, koi sawaal ho toh batao!"),
        },
        "projects": {
            "English": ("🛠️ Real projects included:\n"
                        f"• AI & Data Science: {', '.join(ai['projects'])}\n"
                        f"• Digital Marketing: {', '.join(dm['projects'])}"),
            "Hindi":   ("🛠️ Real projects included:\n"
                        f"• AI & Data Science: {', '.join(ai['projects'])}\n"
                        f"• Digital Marketing: {', '.join(dm['projects'])}"),
            "Hinglish":("🛠️ Real projects included:\n"
                        f"• AI & Data Science: {', '.join(ai['projects'])}\n"
                        f"• Digital Marketing: {', '.join(dm['projects'])}"),
        },
        "device_requirement": {
            "English": ("💻 A laptop or computer with a stable internet connection gives the best learning experience for recorded video "
                        "content. I don't have exact confirmed technical specs — I can connect you with a counsellor if you'd like precise details."),
            "Hindi":   ("💻 Recorded video content के लिए laptop/computer और अच्छा internet होना best रहता है। Exact technical specs confirmed "
                        "नहीं हैं — चाहें तो counsellor से confirm करवा दूँ।"),
            "Hinglish":("💻 Recorded video content ke liye laptop/computer aur achha internet hona best rehta hai. Exact technical specs "
                        "confirmed nahi hain — chaho toh counsellor se confirm karva doon."),
        },
        "stream_eligibility": {
            "English": "✅ Yes! Both programs are open to students from any stream — commerce, arts, or science. No coding or prior experience is required, so your academic background doesn't matter.",
            "Hindi":   "✅ हाँ! दोनों programs किसी भी stream के students के लिए हैं — commerce, arts, या science। कोई coding या experience ज़रूरी नहीं, background मायने नहीं रखता।",
            "Hinglish":"✅ Haan! Dono programs kisi bhi stream ke students ke liye hain — commerce, arts, ya science. Koi coding ya experience zaroori nahi, background matter nahi karta.",
        },
        "assignments": {
            "English": ("📝 Both programs are built around hands-on real projects that double as practical assessments. "
                        "I don't have confirmed details on separate graded assignments/quizzes — I can connect you with a counsellor for that."),
            "Hindi":   ("📝 दोनों programs real projects पर based हैं, जो practical assessment का काम करते हैं। Separate graded assignments/quiz "
                        "के बारे में confirmed detail नहीं है — counsellor से connect करवा सकता हूँ।"),
            "Hinglish":("📝 Dono programs real projects par based hain, jo practical assessment ka kaam karte hain. Separate graded "
                        "assignments/quiz ke baare mein confirmed detail nahi hai — counsellor se connect karva sakta hoon."),
        },
        "experienced": {
            "English": ("💪 That's great! Since it's fully self-paced, you can move quickly through what you already know and focus on the "
                        "projects, certificate, and internship to strengthen your portfolio — and it fits around your existing schedule or job."),
            "Hindi":   ("💪 बढ़िया! चूंकि यह पूरी तरह self-paced है, जो पहले से आता है उसे fast cover कर सकते हैं और projects, certificate, "
                        "internship पर focus कर सकते हैं — यह आपकी schedule/job के साथ भी fit हो जाता है।"),
            "Hinglish":("💪 Badhiya! Chunki yeh fully self-paced hai, jo pehle se aata hai wo fast cover kar sakte ho aur projects, "
                        "certificate, internship pe focus kar sakte ho — yeh aapki schedule/job ke saath bhi fit ho jaata hai."),
        },
        "demo": {
            "English": "🎬 I don't have confirmed details on a free demo/trial class. Let me connect you with a counsellor who can help with that.",
            "Hindi":   "🎬 Free demo/trial class के बारे में confirmed detail मेरे पास नहीं है। मैं counsellor से connect करवा देता हूँ।",
            "Hinglish":"🎬 Free demo/trial class ke baare mein confirmed detail mere paas nahi hai. Main counsellor se connect karva deta hoon.",
        },
        "thanks": {
            "English": "You're welcome! 😊 Let me know if you have any other questions.",
            "Hindi":   "आपका स्वागत है! 😊 कोई और सवाल हो तो बताइए।",
            "Hinglish":"Koi baat nahi! 😊 Aur koi sawaal ho toh batao.",
        },
        "acknowledge": {
            "English": "👍 Great! Let me know if you'd like to know anything else — pricing, syllabus, or how to enroll.",
            "Hindi":   "👍 बढ़िया! कुछ और जानना हो — pricing, syllabus, या enroll कैसे करें — तो बताइए।",
            "Hinglish":"👍 Badhiya! Kuch aur jaanna ho — pricing, syllabus, ya enroll kaise karein — toh batao.",
        },
        "farewell": {
            "English": "👋 Thanks for chatting! Feel free to reach out anytime — have a great day!",
            "Hindi":   "👋 बात करने के लिए धन्यवाद! जब चाहें फिर से संपर्क करें — आपका दिन शुभ हो!",
            "Hinglish":"👋 Chat karne ke liye thanks! Jab bhi chaho phir se contact karo — have a great day!",
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

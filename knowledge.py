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
                    "which course should i take", "dono me kya difference",
                    "recommend", "recommend a course", "recommend course", "recommend me a course",
                    "suggest a course", "suggest course", "suggest me a course",
                    "best course", "which course", "which course should i choose",
                    "which course should i pick", "which course should i join",
                    "konsa course", "kaunsa course", "kaun sa course", "mere liye best",
                    "mujhe konsa course", "help me choose", "which one should i pick",
                    "best course for me"],
    "beginner_doubt": ["beginner", "no experience", "never coded", "can i do this",
                    "am i eligible for this", "new to this", "confuse", "confused", "doubt",
                    "not sure if i can", "mujhe nahi aata", "will i understand",
                    "coding nahi aati", "coding nahi aata", "mujhe coding nahi aati",
                    "mujhe coding nahi aata", "no coding", "no coding required",
                    "no coding knowledge", "coding nahi", "mujhe coding nahi", "codding nahi aati",
                    "codding nahi aata"],
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
                    "system requirement", "pc required", "mobile se ho jayega",
                    "sirf mobile", "sirf mobile hai", "only mobile", "mobile only",
                    "mobile hi hai", "mobile se hoga", "mobile", "no laptop", "laptop nahi",
                    "laptop nahi hai", "don't have a laptop", "dont have a laptop"],
    "stream_eligibility": ["commerce student", "arts student", "science student", "any stream",
                    "bcom", "b.com", "ba student", "bsc student", "12th", "non-tech background",
                    "humanities student", "commerce", "arts", "commerce se hu", "commerce se hoon",
                    "commerce background", "arts se hu", "arts se hoon", "arts background",
                    "science se hu", "science se hoon", "science background", "pcm", "pcb",
                    "bca student", "bca se hu", "bca se hoon", "b.com student", "main commerce",
                    "main arts", "main science"],
    "assignments": ["assignment", "assessment", "quiz", "evaluation test"],
    "experienced": ["already know coding", "already working", "i already know", "experienced in",
                    "i have experience", "already a developer", "already do marketing",
                    "already working professional"],
    "demo":        ["demo", "free trial", "trial class", "sample class", "preview class"],
    "thanks":      ["thanks", "thank you", "thnx", "shukriya", "dhanyawad"],
    "acknowledge": ["okay", "fine", "alright", "acha", "theek hai", "sahi hai"],
    "farewell":    ["bye", "goodbye", "see you", "tata", "milte hain", "chalta hoon"],

    # ---------------------------------------------------------------- #
    # Trust / legitimacy / legal
    # ---------------------------------------------------------------- #
    "trust": ["real company", "fake company", "is this real", "is this fake", "scam",
              "fraud", "trustworthy", "trust worthy", "can i trust", "genuine company",
              "genuine hai", "asli hai", "nakli hai", "legit company", "is it legit",
              "is it legal", "legal hai", "registered company", "company registered hai",
              "govt registered", "government registered", "authorised", "authorized",
              "recognised", "recognized", "valid company", "reliable company",
              "bharosemand", "bharosa", "yakeen", "sach me", "sachi company",
              "kya ye sahi hai", "safe hai kya", "is this safe", "trust kar sakte",
              "trust kar sakte hain", "is smartversa real", "is smartversa fake",
              "smartversa fraud", "smartversa scam", "smartversa legit"],
    "msme": ["msme", "msme registered", "msme certificate", "udyam", "udyam registration",
             "gst registered", "company registration number", "cin number", "registration number"],

    "certificate_value": ["certificate valid hai", "certificate valid", "certificate kaam ayega",
             "certificate ki value", "certificate recognised", "certificate recognized",
             "certificate accepted", "certificate govt approved", "iso certificate",
             "ugc approved", "aicte approved", "university recognised", "certificate use hoga",
             "will this certificate help", "does certificate matter", "certificate ka fayda"],

    "linkedin": ["linkedin", "linkedin optimization", "linkedin profile", "linkedin banwao",
                 "linkedin help", "linkedin update"],
    "resume": ["resume", "cv banwana", "resume banwana", "resume review", "cv review",
               "resume banao", "cv chahiye", "resume help", "resume kaise banaye"],
    "portfolio": ["portfolio", "portfolio banwana", "portfolio chahiye", "project portfolio",
                  "github portfolio", "showcase projects"],
    "interview": ["interview", "interview prep", "interview preparation", "mock interview",
                  "interview tips", "interview ready", "interview ke liye"],
    "mentors": ["mentor", "mentors", "mentorship", "guide karega kaun", "trainer kaun hai",
                "trainer", "instructor", "teacher", "faculty", "kaun sikhayega",
                "who will teach"],

    "emi": ["emi", "installment", "installments", "kist", "kisto me", "monthly payment",
            "pay in parts", "part payment", "split payment"],
    "discount": ["discount", "koi discount", "any discount", "offer chal raha", "coupon",
                 "coupon code", "promo code", "sasta", "kam price", "price kam karo",
                 "less price", "reduce price", "special offer"],
    "scholarship": ["scholarship", "scholarship hai kya", "fee waiver", "free seat",
                     "financial help", "financial assistance"],

    "audience_fit": ["working professional", "job kar raha", "job kar rahi", "housewife",
                      "gharelu mahila", "gap year", "gap year hai", "fresher", "freshers",
                      "abhi graduate hua", "abhi graduate hui", "college student",
                      "school student", "12th ke baad", "graduate ke baad", "mba student",
                      "mba se hu", "mba se hoon", "part time karna hai", "full time job ke saath"],

    "career_outcomes": ["career", "career growth", "future scope", "scope in ai",
                         "scope in digital marketing", "roadmap", "career roadmap",
                         "job scope", "future me kya", "growth potential", "career options",
                         "kya banoge", "kya ban sakte", "which career", "career path"],
    "freelancing": ["freelance", "freelancing", "freelancer", "work from home",
                     "apna kaam", "own clients", "client lena"],
    "higher_studies": ["higher studies", "further studies", "masters", "abroad studies",
                        "study abroad", "ms karna hai", "phd", "further education"],
    "salary": ["salary", "package", "in hand salary", "starting salary", "kitni salary",
               "average package", "ctc"],

    "enrollment_process": ["how to enroll", "enrollment process", "admission process",
                            "how to join", "how to register", "registration process",
                            "batch start date", "next batch", "batch kab start",
                            "joining process", "kaise join karu", "kaise enroll karu"],
    "payment_failure": ["payment failed", "payment fail", "payment nahi hua", "paisa kat gaya",
                         "money deducted", "transaction failed", "payment error",
                         "payment issue", "payment problem", "paisa deduct ho gaya"],
    "offer_letter": ["offer letter", "internship letter", "appointment letter",
                      "joining letter", "experience letter milega"],

    "notes": ["notes", "study material", "pdf notes", "reading material", "notes milenge"],
    "doubts": ["doubt clearing", "doubt session", "ask doubts", "who clears doubts",
               "how to ask doubts", "query resolution"],
    "batch_size": ["batch size", "kitne students", "group size", "class strength"],

    "tools_query": ["power bi", "sql", "excel", "python course", "machine learning",
                    "ml", "data science", "seo", "meta ads", "google ads", "analytics tool",
                    "which tools", "what tools", "which software", "kaunse tools",
                    "kaunsa software"],
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
    "enrollment_process": 20,
    "payment_failure": 30,
    "emi": 15,
    "discount": 10,
    "scholarship": 10,
    "trust": 5,
    "career_outcomes": 8,
    "salary": 8,
    "resume": 5,
    "linkedin": 5,
    "interview": 5,
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
        "trust": {
            "English": (f"🛡️ Fair question! *{COMPANY['name']}* is an {COMPANY['registration']}, based in "
                        f"{COMPANY['location']} ({COMPANY['website']}). Every enrolled student gets a certificate, "
                        "real projects, and an internship — and our support team is reachable anytime if you need proof "
                        f"or have questions ({COMPANY['whatsapp_support']})."),
            "Hindi":   (f"🛡️ अच्छा सवाल! *{COMPANY['name']}* एक {COMPANY['registration']} है, {COMPANY['location']} में based "
                        f"({COMPANY['website']})। हर student को certificate, real projects और internship मिलती है — "
                        f"कोई भी doubt हो तो support team से बात कर सकते हैं ({COMPANY['whatsapp_support']})।"),
            "Hinglish":(f"🛡️ Achha sawaal! *{COMPANY['name']}* ek {COMPANY['registration']} hai, {COMPANY['location']} mein based "
                        f"({COMPANY['website']}). Har student ko certificate, real projects aur internship milti hai — "
                        f"koi bhi doubt ho toh support team se baat kar sakte ho ({COMPANY['whatsapp_support']})."),
        },
        "msme": {
            "English": (f"📋 Yes — {COMPANY['name']} is an {COMPANY['registration']}. If you'd like, I can connect you "
                        "with our team for further verification details."),
            "Hindi":   (f"📋 हाँ — {COMPANY['name']} एक {COMPANY['registration']} है। चाहें तो verification details के लिए "
                        "team से connect करवा सकता हूँ।"),
            "Hinglish":(f"📋 Haan — {COMPANY['name']} ek {COMPANY['registration']} hai. Chaho toh verification details ke "
                        "liye team se connect karva sakta hoon."),
        },
        "certificate_value": {
            "English": ("🏅 The certificate is issued by SmartVersa on successful completion, backed by real projects "
                        "and an internship on your profile — which is what most recruiters actually look for alongside "
                        "a certificate. I don't have confirmed details on external accreditation bodies (UGC/AICTE etc.) "
                        "— happy to connect you with a counsellor for that specific detail."),
            "Hindi":   ("🏅 Certificate SmartVersa की तरफ से course पूरा करने पर मिलता है, साथ में real projects और "
                        "internship भी profile में जुड़ते हैं — यही recruiters ज़्यादा देखते हैं। External accreditation "
                        "(UGC/AICTE) की confirmed detail नहीं है — counsellor से पूछ सकते हैं।"),
            "Hinglish":("🏅 Certificate SmartVersa ki taraf se course complete karne par milta hai, saath mein real "
                        "projects aur internship bhi profile mein judte hain — yehi recruiters zyada dekhte hain. "
                        "External accreditation (UGC/AICTE) ki confirmed detail nahi hai — counsellor se pooch sakte ho."),
        },
        "linkedin": {
            "English": "💼 LinkedIn optimization is part of our placement support — we help you present your projects, certificate, and internship the right way on your profile.",
            "Hindi":   "💼 LinkedIn optimization हमारे placement support का हिस्सा है — projects, certificate और internship को सही तरीके से profile पर दिखाने में मदद करते हैं।",
            "Hinglish":"💼 LinkedIn optimization hamare placement support ka hissa hai — projects, certificate aur internship ko sahi tarike se profile pe dikhane mein help karte hain.",
        },
        "resume": {
            "English": "📄 Resume building and review is included in our placement support, so your projects, internship, and certificate come across clearly to recruiters.",
            "Hindi":   "📄 Resume building और review हमारे placement support में शामिल है, जिससे आपके projects, internship और certificate recruiters तक अच्छे से पहुंचें।",
            "Hinglish":"📄 Resume building aur review hamare placement support mein included hai, jisse aapke projects, internship aur certificate recruiters tak achhe se pahunchein.",
        },
        "portfolio": {
            "English": ("🗂️ Your portfolio comes from the real projects you build during the course — "
                        "you'll have hands-on work to show, not just a certificate."),
            "Hindi":   "🗂️ आपका portfolio course के real projects से बनता है — सिर्फ certificate नहीं, दिखाने के लिए actual काम भी होगा।",
            "Hinglish":"🗂️ Aapka portfolio course ke real projects se banta hai — sirf certificate nahi, dikhane ke liye actual kaam bhi hoga.",
        },
        "interview": {
            "English": "🎤 Interview preparation is part of our placement support, alongside resume building, LinkedIn optimization, and career guidance.",
            "Hindi":   "🎤 Interview preparation हमारे placement support का हिस्सा है, साथ में resume building, LinkedIn optimization और career guidance भी।",
            "Hinglish":"🎤 Interview preparation hamare placement support ka hissa hai, saath mein resume building, LinkedIn optimization aur career guidance bhi.",
        },
        "mentors": {
            "English": ("🧑‍🏫 You're guided through structured recorded lessons, real projects, and support from our team "
                        "for doubts. I don't have confirmed details on 1:1 mentor assignment — I can check with a "
                        "counsellor if that matters to you."),
            "Hindi":   ("🧑‍🏫 आपको structured recorded lessons, real projects, और doubts के लिए team support मिलता है। "
                        "1:1 mentor assignment की confirmed detail नहीं है — चाहें तो counsellor से पूछ सकता हूँ।"),
            "Hinglish":("🧑‍🏫 Aapko structured recorded lessons, real projects, aur doubts ke liye team support milta "
                        "hai. 1:1 mentor assignment ki confirmed detail nahi hai — chaho toh counsellor se pooch sakta hoon."),
        },
        "emi": {
            "English": ("💳 I don't have confirmed EMI/installment details right now — payment is currently via a "
                        "single secure Razorpay transaction. I can connect you with our team to check if part-payment "
                        "is possible for your case."),
            "Hindi":   ("💳 EMI/installment की confirmed detail अभी मेरे पास नहीं है — payment अभी single Razorpay "
                        "transaction से होती है। चाहें तो team से पूछ के बताता हूँ।"),
            "Hinglish":("💳 EMI/installment ki confirmed detail abhi mere paas nahi hai — payment abhi single Razorpay "
                        "transaction se hoti hai. Chaho toh team se pooch ke batata hoon."),
        },
        "discount": {
            "English": ("🏷️ The listed price (GST included) is our standard fee. I don't "
                        "have any confirmed discount/coupon running right now — I can connect you with our counsellor "
                        "to check if anything's available."),
            "Hindi":   ("🏷️ Listed price ही हमारी standard fee है (GST included)। अभी कोई confirmed discount/coupon "
                        "नहीं है — counsellor से check करवा सकता हूँ।"),
            "Hinglish":("🏷️ Listed price hi hamari standard fee hai (GST included). Abhi koi confirmed discount/coupon "
                        "nahi hai — counsellor se check karva sakta hoon."),
        },
        "scholarship": {
            "English": ("🎓 I don't have confirmed details on a scholarship or fee-waiver program right now. "
                        "I can connect you with our counsellor to check if you qualify for anything."),
            "Hindi":   ("🎓 Scholarship/fee-waiver की confirmed detail अभी मेरे पास नहीं है। चाहें तो counsellor से "
                        "check करवा दूँ।"),
            "Hinglish":("🎓 Scholarship/fee-waiver ki confirmed detail abhi mere paas nahi hai. Chaho toh counsellor "
                        "se check karva doon."),
        },
        "audience_fit": {
            "English": ("🙌 Both programs work well whether you're a student, working professional, homemaker, fresher, "
                        "or on a gap year — everything is recorded and self-paced, so you learn on your own schedule "
                        "with no fixed class timings to juggle."),
            "Hindi":   ("🙌 दोनों programs हर किसी के लिए ठीक हैं — student, working professional, homemaker, fresher, "
                        "या gap year पर हों। सब कुछ recorded और self-paced है, अपनी schedule से पढ़ सकते हैं।"),
            "Hinglish":("🙌 Dono programs har kisi ke liye theek hain — student, working professional, homemaker, "
                        "fresher, ya gap year pe ho. Sab kuch recorded aur self-paced hai, apni schedule se padh sakte ho."),
        },
        "career_outcomes": {
            "English": ("🚀 AI & Data Science can lead toward roles like Data Analyst or BI Analyst; Digital Marketing "
                        "can lead toward Social Media Manager, Digital Marketer, or freelance marketing work. Both "
                        "fields are growing fast in India. We support your job-readiness with resume, LinkedIn, and "
                        "interview prep — final placement isn't guaranteed, but you finish genuinely equipped."),
            "Hindi":   ("🚀 AI & Data Science से Data Analyst / BI Analyst जैसे roles मिल सकते हैं; Digital Marketing से "
                        "Social Media Manager, Digital Marketer, या freelance work। दोनों fields India में तेज़ी से grow "
                        "कर रही हैं। हम resume, LinkedIn, interview prep में मदद करते हैं — guaranteed placement नहीं, "
                        "पर आप job-ready ज़रूर बनते हैं।"),
            "Hinglish":("🚀 AI & Data Science se Data Analyst / BI Analyst jaise roles mil sakte hain; Digital Marketing "
                        "se Social Media Manager, Digital Marketer, ya freelance work. Dono fields India mein tezi se "
                        "grow kar rahi hain. Hum resume, LinkedIn, interview prep mein madad karte hain — guaranteed "
                        "placement nahi, par aap job-ready zaroor bante ho."),
        },
        "freelancing": {
            "English": ("🧳 Both tracks are freelance-friendly — Digital Marketing especially, since Meta Ads, SEO, and "
                        "content skills are in direct demand from small businesses; AI & Data Science also opens up "
                        "freelance data-analysis work with the right portfolio."),
            "Hindi":   ("🧳 दोनों tracks freelancing के लिए अच्छे हैं — खासकर Digital Marketing, क्योंकि Meta Ads, SEO, "
                        "content skills की demand direct रहती है; AI & Data Science में भी portfolio के साथ freelance "
                        "data work मिल सकता है।"),
            "Hinglish":("🧳 Dono tracks freelancing ke liye achhe hain — khaaskar Digital Marketing, kyunki Meta Ads, "
                        "SEO, content skills ki demand direct rehti hai; AI & Data Science mein bhi portfolio ke saath "
                        "freelance data work mil sakta hai."),
        },
        "higher_studies": {
            "English": ("🎓 Both programs give you a practical head start (real projects + fundamentals) that pairs "
                        "well alongside or before higher studies — they're not a replacement for a degree, but a "
                        "practical skill layer on top of it."),
            "Hindi":   ("🎓 दोनों programs practical head start देते हैं (real projects + fundamentals) जो higher studies "
                        "के साथ या पहले भी मददगार हैं — यह degree का replacement नहीं, बल्कि उसके ऊपर practical skill है।"),
            "Hinglish":("🎓 Dono programs practical head start dete hain (real projects + fundamentals) jo higher "
                        "studies ke saath ya pehle bhi madadgar hain — yeh degree ka replacement nahi, balki uske "
                        "upar practical skill hai."),
        },
        "salary": {
            "English": ("💰 I don't have confirmed average salary figures to share — they vary by role, company, and "
                        "location. What I can say is both tracks build toward genuinely in-demand roles, and we support "
                        "you with resume, LinkedIn, and interview prep to help you negotiate well."),
            "Hindi":   ("💰 Confirmed average salary figures मेरे पास नहीं हैं — role, company, location पर depend करता "
                        "है। पर दोनों tracks in-demand roles की तरफ ले जाते हैं, और हम resume/LinkedIn/interview prep "
                        "में मदद करते हैं।"),
            "Hinglish":("💰 Confirmed average salary figures mere paas nahi hain — role, company, location pe depend "
                        "karta hai. Par dono tracks in-demand roles ki taraf le jaate hain, aur hum resume/LinkedIn/"
                        "interview prep mein madad karte hain."),
        },
        "enrollment_process": {
            "English": (f"📝 Enrollment is simple: pick your program, pay securely via Razorpay (GST included) here:\n"
                        f"{Config.PAYMENT_URL}\nOur team then reaches out to guide your next steps. There are no fixed "
                        "batch start dates since everything is self-paced — you can begin as soon as you enroll."),
            "Hindi":   (f"📝 Enrollment simple है: program choose करें, Razorpay से secure payment करें (GST included):\n"
                        f"{Config.PAYMENT_URL}\nफिर हमारी team next steps के लिए guide करेगी। कोई fixed batch date "
                        "नहीं है — enroll करते ही start कर सकते हैं।"),
            "Hinglish":(f"📝 Enrollment simple hai: program choose karo, Razorpay se secure payment karo (GST included):\n"
                        f"{Config.PAYMENT_URL}\nPhir hamari team next steps ke liye guide karegi. Koi fixed batch "
                        "date nahi hai — enroll karte hi start kar sakte ho."),
        },
        "payment_failure": {
            "English": (f"⚠️ Sorry to hear that. If money was deducted but the payment shows as failed, it's usually "
                        f"auto-reversed by the bank/Razorpay within a few days. Please share a screenshot with our "
                        f"support team — 📱 WhatsApp {COMPANY['whatsapp_support']} or 📧 {COMPANY['support_email']} — "
                        f"so we can check and confirm your enrollment right away."),
            "Hindi":   (f"⚠️ Sorry to hear that. अगर पैसा कट गया पर payment failed दिखा रहा है, तो अक्सर bank/Razorpay "
                        f"कुछ दिनों में auto-reverse कर देता है। Screenshot हमारी support team को भेजें — "
                        f"📱 WhatsApp {COMPANY['whatsapp_support']} या 📧 {COMPANY['support_email']} — ताकि हम check "
                        "करके enrollment confirm कर सकें।"),
            "Hinglish":(f"⚠️ Sorry to hear that. Agar paisa kat gaya par payment failed dikha raha hai, toh aksar "
                        f"bank/Razorpay kuch dino mein auto-reverse kar deta hai. Screenshot hamari support team ko "
                        f"bhejo — 📱 WhatsApp {COMPANY['whatsapp_support']} ya 📧 {COMPANY['support_email']} — taaki "
                        "hum check karke enrollment confirm kar sakein."),
        },
        "offer_letter": {
            "English": ("📜 Both programs include a genuine internship alongside real projects, giving you actual "
                        "work experience for your resume. I don't have confirmed specifics on the exact letter/document "
                        "format — I can connect you with a counsellor for that detail."),
            "Hindi":   ("📜 दोनों programs में genuine internship है, real projects के साथ — resume के लिए actual "
                        "experience मिलता है। Exact letter/document format की confirmed detail नहीं है — counsellor से "
                        "पूछ सकता हूँ।"),
            "Hinglish":("📜 Dono programs mein genuine internship hai, real projects ke saath — resume ke liye actual "
                        "experience milta hai. Exact letter/document format ki confirmed detail nahi hai — counsellor "
                        "se pooch sakta hoon."),
        },
        "notes": {
            "English": ("📒 Learning is built around recorded video lessons and real projects. I don't have confirmed "
                        "details on separate downloadable notes/PDFs — happy to check with a counsellor if that's "
                        "important to you."),
            "Hindi":   ("📒 Learning recorded video lessons और real projects पर based है। Separate downloadable "
                        "notes/PDFs की confirmed detail नहीं है — counsellor से पूछ सकता हूँ।"),
            "Hinglish":("📒 Learning recorded video lessons aur real projects par based hai. Separate downloadable "
                        "notes/PDFs ki confirmed detail nahi hai — counsellor se pooch sakta hoon."),
        },
        "doubts": {
            "English": ("❓ You can reach our support team for doubts anytime — "
                        f"📱 WhatsApp {COMPANY['whatsapp_support']} or 📧 {COMPANY['support_email']} "
                        f"({COMPANY['support_hours']})."),
            "Hindi":   ("❓ Doubts के लिए हमारी support team से कभी भी संपर्क कर सकते हैं — "
                        f"📱 WhatsApp {COMPANY['whatsapp_support']} या 📧 {COMPANY['support_email']} "
                        f"({COMPANY['support_hours']})।"),
            "Hinglish":("❓ Doubts ke liye hamari support team se kabhi bhi contact kar sakte ho — "
                        f"📱 WhatsApp {COMPANY['whatsapp_support']} ya 📧 {COMPANY['support_email']} "
                        f"({COMPANY['support_hours']})."),
        },
        "batch_size": {
            "English": ("👥 Since classes are self-paced recorded videos (not live cohorts), there isn't a fixed "
                        "batch/class size to speak of — you learn independently, with support available whenever "
                        "you need it."),
            "Hindi":   ("👥 Classes self-paced recorded videos हैं (live cohort नहीं), इसलिए fixed batch/class size "
                        "जैसी कोई चीज़ नहीं है — आप independently सीखते हैं, ज़रूरत पर support मिलता है।"),
            "Hinglish":("👥 Classes self-paced recorded videos hain (live cohort nahi), isliye fixed batch/class size "
                        "jaisi koi cheez nahi hai — aap independently seekhte ho, zaroorat par support milta hai."),
        },
        "tools_query": {
            "English": ("🛠️ AI & Data Science covers: " + ", ".join(ai["tools"]) +
                        ".\nDigital Marketing covers: " + ", ".join(dm["tools"]) + "."),
            "Hindi":   ("🛠️ AI & Data Science में: " + ", ".join(ai["tools"]) +
                        "।\nDigital Marketing में: " + ", ".join(dm["tools"]) + "।"),
            "Hinglish":("🛠️ AI & Data Science mein: " + ", ".join(ai["tools"]) +
                        ".\nDigital Marketing mein: " + ", ".join(dm["tools"]) + "."),
        },
    }

    entry = table.get(intent)
    if not entry:
        return ""
    return entry.get(lang, entry.get("English", ""))


# --------------------------------------------------------------------------- #
# Course recommendation heuristic
# --------------------------------------------------------------------------- #
def recommend_course(text: str, background: str = "", goal: str = "") -> str:
    """Contextual recommendation. `text` is the free-form signal (kept for
    backward compatibility with existing callers); `background` and `goal`
    are optional extra context (e.g. 'commerce', 'job') a caller may already
    know from earlier in the conversation, for a sharper recommendation."""
    t = " ".join([text or "", background or "", goal or ""]).lower()
    technical = any(w in t for w in
                    ["data", "python", "coding", "analyst", "sql", "analytics", "ai", "machine",
                     "power bi", "excel", "science", "bca", "engineering"])
    marketing = any(w in t for w in
                    ["marketing", "social", "instagram", "ads", "freelanc", "business", "content",
                     "brand", "seo", "arts", "commerce"])
    if technical and not marketing:
        return "1"
    if marketing and not technical:
        return "2"
    # Beginner with no clear technical signal -> Digital Marketing (lower barrier)
    return "2"


# --------------------------------------------------------------------------- #
# Objection sub-typing
# --------------------------------------------------------------------------- #
OBJECTION_KEYWORDS = {
    "expensive":        ["expensive", "mehenga", "mehnga", "costly", "high price", "kam karo",
                          "afford nahi", "cant afford", "can't afford", "budget nahi"],
    "parents_permission":["parents permission", "ask parents", "parents ki permission",
                          "parents allow", "mom dad permission", "ghar walo se puchna",
                          "family permission"],
    "need_time":        ["need time", "time chahiye", "abhi nahi", "not now", "busy hu",
                          "will decide later", "baad me"],
    "thinking":         ["thinking", "soch raha", "soch rahi", "i'll think", "ill think",
                          "let me think", "will think about it"],
    "already_learning": ["already learning", "already enrolled elsewhere", "already doing a course",
                          "kahi aur se seekh raha", "kahi aur se kar raha", "already taking a course"],
}

_OBJECTION_REPLIES = {
    "expensive": {
        "English": ("💡 Totally fair. The fee (GST included) is a one-time cost that covers a certificate, "
                    "internship, and real projects — no hidden charges. I don't have a confirmed discount to offer, "
                    "but I can connect you with our counsellor to see what's possible."),
        "Hindi":   ("💡 समझ सकता हूँ। Fee (GST included) एक बार का cost है, जिसमें certificate, internship और real "
                    "projects शामिल हैं — कोई hidden charge नहीं। Confirmed discount नहीं है, पर counsellor से बात "
                    "करवा सकता हूँ।"),
        "Hinglish":("💡 Samajh sakta hoon. Fee (GST included) ek baar ka cost hai, jisme certificate, internship "
                    "aur real projects included hain — koi hidden charge nahi. Confirmed discount nahi hai, par "
                    "counsellor se baat karva sakta hoon."),
    },
    "parents_permission": {
        "English": ("👨‍👩‍👧 Totally understandable — this is a real decision. I can share full program details "
                    "(company info, certificate, internship, real projects) that you can show your parents, or "
                    "connect them directly with our counsellor for any questions they have."),
        "Hindi":   ("👨‍👩‍👧 बिल्कुल समझ सकता हूँ — यह एक real decision है। मैं पूरी details (company info, "
                    "certificate, internship, real projects) दे सकता हूँ जो parents को दिखा सकते हैं, या counsellor "
                    "से सीधे बात करवा सकता हूँ।"),
        "Hinglish":("👨‍👩‍👧 Bilkul samajh sakta hoon — yeh ek real decision hai. Main poori details (company info, "
                    "certificate, internship, real projects) de sakta hoon jo parents ko dikha sakte ho, ya "
                    "counsellor se seedha baat karva sakta hoon."),
    },
    "need_time": {
        "English": ("⏳ No rush at all — since it's fully self-paced, there's no deadline pressure once you do "
                    "enroll either. Take your time deciding, I'm here whenever you have questions."),
        "Hindi":   ("⏳ कोई जल्दी नहीं — enroll करने के बाद भी सब कुछ self-paced है, कोई deadline pressure नहीं। "
                    "अपना समय लीजिए, सवाल हो तो बताइए।"),
        "Hinglish":("⏳ Koi jaldi nahi — enroll karne ke baad bhi sab kuch self-paced hai, koi deadline pressure "
                    "nahi. Apna time lo, sawaal ho toh batao."),
    },
    "thinking": {
        "English": ("🙂 Of course, take your time. Meanwhile, is there anything specific holding you back — "
                    "price, syllabus, or something else — that I could clarify?"),
        "Hindi":   ("🙂 बिल्कुल, अपना समय लीजिए। बीच में अगर कोई specific सवाल हो — price, syllabus, या कुछ और — "
                    "तो बताइए।"),
        "Hinglish":("🙂 Bilkul, apna time lo. Beech mein agar koi specific sawaal ho — price, syllabus, ya kuch "
                    "aur — toh batao."),
    },
    "already_learning": {
        "English": ("👍 That's great that you're already learning! Our programs stand out with a certificate, "
                    "genuine internship, and real hands-on projects on top of the fundamentals — happy to show how "
                    "it could complement what you're already doing."),
        "Hindi":   ("👍 बढ़िया कि आप already सीख रहे हैं! हमारे programs certificate, genuine internship और real "
                    "hands-on projects के साथ अलग हैं — बता सकता हूँ यह कैसे complement कर सकता है।"),
        "Hinglish":("👍 Badhiya ki aap already seekh rahe ho! Hamare programs certificate, genuine internship aur "
                    "real hands-on projects ke saath alag hain — bata sakta hoon yeh kaise complement kar sakta hai."),
    },
}


def objection_subtype(text: str):
    """Best-effort classification of *why* someone is objecting, checked in a
    fixed priority order (most specific first). Returns a subtype key or
    None if no specific sub-signal is found (caller should fall back to the
    generic 'objection' FAQ answer)."""
    t = (text or "").lower()
    for subtype in ("parents_permission", "already_learning", "expensive",
                     "thinking", "need_time"):
        for kw in OBJECTION_KEYWORDS.get(subtype, []):
            if kw in t:
                return subtype
    return None


def objection_answer(subtype: str, language: str) -> str:
    entry = _OBJECTION_REPLIES.get(subtype)
    if not entry:
        return ""
    return entry.get(language, entry.get("English", ""))


# --------------------------------------------------------------------------- #
# Background / audience detection
# --------------------------------------------------------------------------- #
BACKGROUND_KEYWORDS = {
    "commerce": ["commerce", "bcom", "b.com", "b com"],
    "arts":     ["arts", "ba student", "humanities", "b.a", "main arts"],
    "science":  ["science", "bsc", "b.sc", "pcm", "pcb", "main science"],
    "bca":      ["bca"],
    "mba":      ["mba"],
}

GOAL_KEYWORDS = {
    "job":            ["job", "naukri", "placement", "salary", "employment"],
    "freelancing":    ["freelance", "freelancing", "freelancer"],
    "higher_studies": ["higher studies", "masters", "further studies", "phd", "study abroad"],
    "business":       ["own business", "apna business", "startup", "entrepreneur"],
}


def detect_background(text: str):
    t = (text or "").lower()
    for key, kws in BACKGROUND_KEYWORDS.items():
        for kw in kws:
            if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", t):
                return key
    return None


def detect_goal(text: str):
    t = (text or "").lower()
    for key, kws in GOAL_KEYWORDS.items():
        for kw in kws:
            if kw in t:
                return key
    return None


# --------------------------------------------------------------------------- #
# Semantic / fuzzy fallback layer — never say "I don't know" until we've
# tried (1) exact keyword intents, (2) typo-tolerant fuzzy matching, (3)
# token-overlap semantic similarity, and only then (4) human handoff.
# Zero extra dependencies (stdlib difflib only).
# --------------------------------------------------------------------------- #
from difflib import SequenceMatcher, get_close_matches

_ALL_PHRASES = [(kw, intent) for intent, kws in INTENT_KEYWORDS.items() for kw in kws]
_ALL_PHRASE_TEXT = [p for p, _ in _ALL_PHRASES]


def _fuzzy_match(text: str, threshold: float = 0.84):
    """Typo-tolerant pass: catches things like 'certifcate' or 'placment'
    that literal matching would miss."""
    if not text:
        return set()
    t = text.lower().strip()
    found = set()

    close = get_close_matches(t, _ALL_PHRASE_TEXT, n=3, cutoff=threshold)
    for phrase in close:
        for p, intent in _ALL_PHRASES:
            if p == phrase:
                found.add(intent)

    words = re.findall(r"[a-zA-Z]+", t)
    short_phrases = [(p, i) for p, i in _ALL_PHRASES if " " not in p and len(p) > 3]
    for w in words:
        for p, intent in short_phrases:
            if SequenceMatcher(None, w, p).ratio() >= threshold:
                found.add(intent)
    return found


def _semantic_match(text: str, min_overlap: int = 2):
    """Coarse semantic pass: scores every intent by keyword *token* overlap
    with the message, so mixed word order / Hinglish phrasing still lands on
    the right intent. Returns the single best-scoring intent if it clears
    `min_overlap`, else empty."""
    t = (text or "").lower()
    tokens = set(re.findall(r"[a-zA-Z]+", t))
    if not tokens:
        return set()

    best_intent, best_score = None, 0
    for intent, kws in INTENT_KEYWORDS.items():
        kw_tokens = set()
        for kw in kws:
            kw_tokens.update(re.findall(r"[a-zA-Z]+", kw.lower()))
        overlap = len(tokens & kw_tokens)
        if overlap > best_score:
            best_intent, best_score = intent, overlap

    if best_intent and best_score >= min_overlap:
        return {best_intent}
    return set()


def detect_intents_smart(text: str):
    """Full detection pipeline: exact keyword match first (cheap, precise),
    then typo-tolerant fuzzy match, then coarse semantic overlap. Stops as
    soon as a stage finds something."""
    intents = detect_intents(text)
    if intents:
        return intents
    intents = _fuzzy_match(text)
    if intents:
        return intents
    return _semantic_match(text)

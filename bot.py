"""
SmartVersa conversational engine.

Preserves the original onboarding flow (name → language → course → interested →
email → save) and adds: branded welcome, Hindi/English/Hinglish, intent + FAQ
answers at any step, lead scoring, restart-anytime, counsellor handoff, and an
optional AI counsellor takeover for free-form conversation after onboarding.

In-memory sessions (like the original). A DB/Redis-backed session store is the
Tranche-2 upgrade for multi-worker persistence.
"""

from datetime import datetime

from config import Config
from logger import log, safe
import whatsapp
import sheets
import ai
from knowledge import (
    COURSES, course_by_choice, detect_intents, score_for,
    faq_answer, detect_language, recommend_course,
)

# phone -> session dict
_sessions = {}


# Lead stages
STAGE_NEW = "New Lead"
STAGE_CONTACTED = "Contacted"
STAGE_WARM = "Warm Lead"
STAGE_HOT = "Hot Lead"
STAGE_PAYMENT_SENT = "Payment Sent"
STAGE_NOT_INTERESTED = "Not Interested"

_FAQ_PRIORITY = ["payment", "price", "certificate", "internship", "placement",
                 "syllabus", "duration", "timing", "refund", "prerequisite"]

_RESTART_WORDS = {"restart", "reset", "menu", "start over", "start again", "shuru"}

# ============================================================
# SmartVersa Bot V2.1
# Natural Language Dictionaries
# These allow users to reply using normal words instead of only numbers.
# ============================================================

YES_WORDS = {
    "1", "yes", "haan", "ha", "ok", "okay",
    "sure", "join", "enroll", "interested", "start",

    # Additional natural replies
    "yes please",
    "lets join",
    "let's join",
    "i am interested",
    "continue",
    "go ahead"
}

NO_WORDS = {
    "2", "no", "nahi", "nah", "later",
    "call", "counsellor", "human", "talk",

    # Additional natural replies
    "not interested",
    "not now",
    "maybe later",
    "skip"
}



DETAIL_WORDS = {
    "details", "detail", "info",
    "information", "more", "course details"
}
AI_WORDS = {
    "1",
    "ai",
    "ai course",
    "data science",
    "ai & data science",
    "machine learning",
    "python",
    "analytics",

    # Related keywords
    "artificial intelligence",
    "data analyst",
    "data analytics",
    "power bi",
    "excel"
}

DM_WORDS = {
    "2",
    "digital marketing",
    "marketing",
    "seo",
    "meta ads",
    "social media",

    # Related keywords
    "instagram",
    "facebook ads",
    "google ads",
    "ads",
    "content marketing"
}

BOTH_WORDS = {
    "3",
    "both",
    "dono",
    "all"
}

def normalize(text):
    """Normalize user input for comparison."""
    return (text or "").strip().lower()

def _new_session(wa_name, first_text):
    return {
        "step": 1,
        "name": "",
        "whatsapp_name": wa_name or "",
        "language": detect_language(first_text, fallback=""),
        "interest": "",
        "email": "",
        "stage": STAGE_NEW,
        "inquiry_message": first_text,
        "score": 0,
        "tags": set(),
        "history": [],
        "saved": False,
    }


def _get_session(phone, wa_name, text):
    if phone not in _sessions:
        _sessions[phone] = _new_session(wa_name, text)
    return _sessions[phone]


def _priority(score):
    if score >= 40:
        return "High"
    if score >= 15:
        return "Medium"
    return "Low"


def _send(phone, sess, text):
    whatsapp.send_message(phone, text)
    sess["history"].append({"role": "bot", "text": text})


def _lang(sess):
    return sess.get("language") or "English"


def _welcome(sess):
    lang = _lang(sess)
    if lang == "Hindi":
        return ("👋 नमस्ते! *SmartVersa* में आपका स्वागत है — AI education & "
                "internship programs.\n\nकृपया अपना पूरा नाम बताइए:")
    if lang == "Hinglish":
        return ("👋 Namaste! *SmartVersa* me welcome — AI education & internship "
                "programs.\n\nApna full name bataiye:")
    return ("👋 Welcome to *SmartVersa* — AI education & internship programs!\n\n"
            "Please enter your full name:")


def _ask_language(sess):
    return "Preferred language?\n\n1. Hindi\n2. English\n3. Hinglish"


def _ask_course(sess):
    lang = _lang(sess)
    if lang == "Hindi":
        return ("आप किस program में interested हैं?\n\n"
                "1. AI & Data Science (₹1299)\n2. Digital Marketing (₹4999)\n3. दोनों")
    return ("Which program are you interested in?\n\n"
            "1. AI & Data Science (₹1299)\n2. Digital Marketing (₹4999)\n3. Both")


def _best_faq(intents, sess):
    for intent in _FAQ_PRIORITY:
        if intent in intents:
            ans = faq_answer(intent, _lang(sess))
            if ans:
                return intent, ans
    return None, None


def _tag(sess, intents):
    for i in intents:
        if i in ("price", "certificate", "payment", "internship", "placement", "syllabus"):
            sess["tags"].add(i)


def _handoff_message(sess):
    lang = _lang(sess)
    if lang == "Hindi":
        return "🙋 ठीक है! हमारा counsellor जल्दी आपसे संपर्क करेगा। कोई सवाल हो तो यहीं पूछिए।"
    if lang == "Hinglish":
        return "🙋 Theek hai! Hamara counsellor jaldi aapse contact karega. Koi sawaal ho toh yahin poochho."
    return "🙋 Sure! Our counsellor will reach out shortly. Meanwhile, ask me anything here."


def _save_lead(phone, sess):
    lead = {
        "Name": sess["name"],
        "Phone": phone,
        "WhatsApp Name": sess.get("whatsapp_name", ""),
        "Email": sess.get("email", ""),
        "Preferred Language": sess.get("language", ""),
        "Course Interest": sess.get("interest", ""),
        "Lead Source": "WhatsApp Bot",
        "Inquiry Message": sess.get("inquiry_message", ""),
        "Stage": sess.get("stage", STAGE_NEW),
        "Date": datetime.now().strftime("%d-%m-%Y"),
        "Time": datetime.now().strftime("%H:%M"),
        "Follow-up Date": "",
        "Payment Status": "Pending",
        "Notes": "",
        "Followup1 Sent": "No",
        "Followup2 Sent": "No",
        "Followup3 Sent": "No",
        "Followup4 Sent": "No",
        "Lead Score": sess.get("score", 0),
        "Tags": ", ".join(sorted(sess.get("tags", []))),
        "Priority": _priority(sess.get("score", 0)),
        "AI Paused": "No",
        "Last Contact": datetime.now().strftime("%d-%m-%Y %H:%M"),
    }
    sheets.append_lead(lead)
    sess["saved"] = True


def _update_lead_progress(phone, sess):
    if not sess.get("saved"):
        return
    sheets.update_lead(phone, {
        "Stage": sess.get("stage", STAGE_NEW),
        "Lead Score": sess.get("score", 0),
        "Tags": ", ".join(sorted(sess.get("tags", []))),
        "Priority": _priority(sess.get("score", 0)),
        "Last Contact": datetime.now().strftime("%d-%m-%Y %H:%M"),
    })


def _send_course(phone, sess, choice):
    course = course_by_choice(choice)
    if not course:
        return False
    sess["interest"] = course["name"]
    whatsapp.send_image(phone, course["image"], "SmartVersa")
    _send(phone, sess, course["details"])
    return True


# --------------------------------------------------------------------------- #
# Main entry point
# --------------------------------------------------------------------------- #
@safe(default=None, label="bot.handle")
def handle(phone, text, wa_name=""):
    text = (text or "").strip()
    sess = _get_session(phone, wa_name, text)
    sess["history"].append({"role": "user", "text": text})

    # Auto-refine language from the user's own words.
    if not sess.get("language"):
        sess["language"] = detect_language(text, fallback="")

    # Restart anytime
    if text.lower() in _RESTART_WORDS:
        _sessions[phone] = _new_session(wa_name, text)
        _send(phone, _sessions[phone], _welcome(_sessions[phone]))
        return

    intents = detect_intents(text)
    gained = score_for(intents)
    if gained:
        sess["score"] += gained
    _tag(sess, intents)

    # Explicit human/counsellor request at any point
    if "human" in intents:
        sess["stage"] = STAGE_WARM
        _send(phone, sess, _handoff_message(sess))
        _update_lead_progress(phone, sess)
        return

    step = sess["step"]

    # ---------------- Onboarding ----------------
    if step == 1:
        # First-ever message: greet + ask name. Answer an opening question too.
        if not sess["name"] and len(sess["history"]) == 1:
            intent, ans = _best_faq(intents, sess)
            if ans:
                _send(phone, sess, ans)
            _send(phone, sess, _welcome(sess))
            return
        sess["name"] = text
        sess["step"] = 2
        _send(phone, sess, _ask_language(sess))
        return

    if step == 2:
        mapping = {
            "1": "Hindi",
            "2": "English",
            "3": "Hinglish",
            "hindi": "Hindi",
            "english": "English",
            "hinglish": "Hinglish",
            "eng": "English",
            "en": "English",
            "hi": "Hindi"
        }

        # Normalize user input before checking
        text_normal = normalize(text)

        if text_normal in mapping:
            sess["language"] = mapping[text_normal]
            sess["step"] = 3
            _send(phone, sess, _ask_course(sess))
        else:
            _answer_or_reprompt(phone, sess, intents, _ask_language(sess))

        return


    if step == 3:
        text_normal = normalize(text)

        # Convert natural language into numeric choice
        if text_normal in AI_WORDS:
            choice = "1"
        elif text_normal in DM_WORDS:
            choice = "2"
        elif text_normal in BOTH_WORDS:
            choice = "3"
        else:
            choice = text

        if choice in ("1", "2", "3"):
            if _send_course(phone, sess, choice):
                sess["step"] = 4
                lang = _lang(sess)

                q = (
                    "Are you interested?\n\n"
                    "1. Yes, enroll me\n"
                    "2. Talk to a counsellor"
                    if lang == "English"
                    else
                    "Interested?\n\n"
                    "1. Haan, enroll karna hai\n"
                    "2. Counsellor se baat karni hai"
                )

                _send(phone, sess, q)

        else:
            _answer_or_reprompt(phone, sess, intents, _ask_course(sess))

        return


    if step == 4:
        if normalize(text) in YES_WORDS:
            sess["stage"] = STAGE_HOT
            sess["score"] += 20
            sess["step"] = 5
            lang = _lang(sess)
            _send(phone, sess,
                  ("Great 😊 Please share your email (or type SKIP):"
                   if lang != "Hindi" else "बढ़िया 😊 अपना email दें (या SKIP लिखें):"))
        elif normalize(text) in NO_WORDS:
            sess["stage"] = STAGE_WARM
            sess["step"] = 5
            _send(phone, sess, _handoff_message(sess) +
                  "\n\n📧 Email? (or type SKIP):")
        else:
            _answer_or_reprompt(phone, sess, intents,
                                "Please reply 1 (Yes) or 2 (Counsellor).")
        return

    if step == 5:
        sess["email"] = "" if text.upper() == "SKIP" else text
        _save_lead(phone, sess)
        sess["step"] = 6
        if sess["stage"] == STAGE_HOT:
            _send(phone, sess, _enroll_message(sess))
            sess["stage"] = STAGE_PAYMENT_SENT
            _update_lead_progress(phone, sess)
        else:
            lang = _lang(sess)
            _send(phone, sess,
                  ("✅ Sent to our counsellor. Ask me anything meanwhile!"
                   if lang == "English" else
                   "✅ Counsellor ko bhej diya. Meanwhile kuch bhi poochho!"))
        return

    # ---------------- Open conversation (post-onboarding) ---------------
    _open_conversation(phone, sess, text, intents)


def _enroll_message(sess):
    lang = _lang(sess)
    if lang == "Hindi":
        return f"🎉 यहाँ से enroll करें:\n{Config.PAYMENT_URL}\n\nकोई दिक्कत हो तो बताइए!"
    if lang == "Hinglish":
        return f"🎉 Yahan se enroll karo:\n{Config.PAYMENT_URL}\n\nKoi dikkat ho toh batao!"
    return f"🎉 Enroll here:\n{Config.PAYMENT_URL}\n\nTell me if you need any help!"


def _answer_or_reprompt(phone, sess, intents, prompt):
    """During onboarding, if the user asked a question, answer it then re-ask."""
    intent, ans = _best_faq(intents, sess)
    if ans:
        _send(phone, sess, ans)
    _send(phone, sess, prompt)


def _open_conversation(phone, sess, text, intents):
    # If the user is ready to pay, always give the link and mark the stage.
    # -------------------------------------------------------
# If the user asks for course details again,
# resend the selected course information.
# -------------------------------------------------------

    if normalize(text) in DETAIL_WORDS:

        if sess.get("interest") == "AI & Data Science":
            _send_course(phone, sess, "1")
            return

        elif sess.get("interest") == "Digital Marketing":
            _send_course(phone, sess, "2")
            return
        elif sess.get("interest") == "Both":
            _send_course(phone, sess, "3")
            return
    if "payment" in intents:
        _send(phone, sess, _enroll_message(sess))
        sess["stage"] = STAGE_PAYMENT_SENT
        _update_lead_progress(phone, sess)
        return

    # Try the AI counsellor first (if enabled).
    ai_text = ai.reply(
        memory={"name": sess.get("name"), "language": sess.get("language"),
                "interest": sess.get("interest")},
        history=sess.get("history", []),
        user_text=text,
    )
    if ai_text:
        _send(phone, sess, ai_text)
        _update_lead_progress(phone, sess)
        return

    # Rule-based fallback: answer FAQ or offer help.
    intent, ans = _best_faq(intents, sess)
    if ans:
        _send(phone, sess, ans)
    else:
        rec = recommend_course(text)
        course = COURSES[rec]
        lang = _lang(sess)
        if lang == "Hindi":
            msg = (f"मैं आपकी help के लिए हूँ 😊 आपके लिए *{course['name']}* अच्छा रहेगा। "
                   f"Details चाहिए या counsellor से बात करें?")
        else:
            msg = (f"I'm here to help 😊 Based on what you shared, *{course['name']}* "
                   f"could suit you well. Want the details, or shall I connect a counsellor?")
        _send(phone, sess, msg)
    _update_lead_progress(phone, sess)

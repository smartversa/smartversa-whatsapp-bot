"""
SmartVersa conversational engine.

Preserves the original onboarding flow (name -> language -> course -> interested ->
email -> save) and behaves like a real admission counsellor on top of it:

- Remembers what's already known (name, language, course, topics discussed,
  lead stage, payment status) and never re-asks for it.
- Never restarts unless the user explicitly says restart/reset/start over.
- Answers small talk (hi, thanks, okay, bye, ...) naturally without derailing
  the flow.
- Never recommends a course cold — if asked "which course is best", asks a
  couple of quick qualifying questions first, then recommends with a reason.
- Always answers "what's taught / included / syllabus" questions with real
  syllabus + projects + internship + certificate info, never a redirect to a
  different course.
- Falls back to a human counsellor handoff whenever it isn't confident,
  instead of guessing.

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

# Payment statuses (kept simple; confirmed automatically only via webhook, if any)
PAYMENT_PENDING = "Pending"
PAYMENT_LINK_SENT = "Link Sent"

# FAQ intents answered directly from knowledge.py, in priority order.
# "syllabus" and "comparison" are handled by dedicated flows below (grounded
# course-detail answers and guided recommendation), so they're excluded here.
# "human", "payment" (stage-changing) and "restart" are handled explicitly.
_FAQ_PRIORITY = [
    "payment", "price", "certificate", "internship", "placement", "refund",
    "duration", "timing", "prerequisite", "about", "support", "projects",
    "stream_eligibility", "device_requirement", "assignments", "demo",
    "experienced", "beginner_doubt", "parents", "objection", "after_payment",
    "small_talk", "greeting", "thanks", "acknowledge", "farewell",
]

_RESTART_WORDS = {"restart", "reset", "menu", "start over", "start again", "shuru"}

# Phrases that mean "tell me what's taught / included" -> grounded course details.
_COURSE_INFO_PATTERNS = [
    "what is taught", "what will i learn", "what's included", "whats included",
    "what is included", "what do i get", "kya sikhaya", "kya milega",
]

# Phrases that mean "help me pick a course" -> guided recommendation flow.
_RECOMMEND_PATTERNS = [
    "recommend a course", "recommend course", "suggest a course",
    "which course is best", "best course for me", "help me choose",
    "which course should i take", "which course should i join",
    "which one should i pick",
]

_COURSE_NAME_TO_KEY = {c["name"]: key for key, c in COURSES.items()}

_RECO_QUESTIONS = {
    1: {
        "English": "Quick question — are you a student or a working professional?",
        "Hindi": "एक सवाल — आप student हैं या working professional?",
        "Hinglish": "Ek quick sawaal — aap student ho ya working professional?",
    },
    2: {
        "English": "Got it. What's your main goal — a job, freelancing, higher studies, or your own business?",
        "Hindi": "समझ गया। आपका main goal क्या है — job, freelancing, higher studies, या अपना business?",
        "Hinglish": "Samajh gaya. Aapka main goal kya hai — job, freelancing, higher studies, ya apna business?",
    },
    3: {
        "English": "Last one — are you more drawn to AI & Data, or Marketing?",
        "Hindi": "आखिरी सवाल — आपको AI & Data ज़्यादा पसंद है या Marketing?",
        "Hinglish": "Last one — aapko AI & Data zyada pasand hai ya Marketing?",
    },
}


# --------------------------------------------------------------------------- #
# Session helpers
# --------------------------------------------------------------------------- #
def _new_session(wa_name, first_text):
    return {
        "step": 1,
        "name": "",
        "whatsapp_name": wa_name or "",
        "language": detect_language(first_text, fallback=""),
        "interest": "",
        "email": "",
        "stage": STAGE_NEW,
        "payment_status": PAYMENT_PENDING,
        "inquiry_message": first_text,
        "score": 0,
        "tags": set(),
        "history": [],
        "saved": False,
        "current_topic": "",
        "topics_covered": [],
        "reco_stage": 0,          # 0 = not started, 1-3 = awaiting answer, "done" = finished
        "reco_answers": {},
        "reco_recommendation": "",
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


def _selected_course_key(sess):
    return _COURSE_NAME_TO_KEY.get(sess.get("interest", ""))


def _track_topic(sess, intents):
    for i in _FAQ_PRIORITY:
        if i in intents:
            sess["current_topic"] = i
            if i not in sess["topics_covered"]:
                sess["topics_covered"].append(i)
            break


def _tag(sess, intents):
    for i in intents:
        if i in ("price", "certificate", "payment", "internship", "placement", "syllabus"):
            sess["tags"].add(i)


# --------------------------------------------------------------------------- #
# Message builders
# --------------------------------------------------------------------------- #
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


def _handoff_message(sess):
    lang = _lang(sess)
    if lang == "Hindi":
        return "🙋 ठीक है! हमारा counsellor जल्दी आपसे संपर्क करेगा। कोई सवाल हो तो यहीं पूछिए।"
    if lang == "Hinglish":
        return "🙋 Theek hai! Hamara counsellor jaldi aapse contact karega. Koi sawaal ho toh yahin poochho."
    return "🙋 Sure! Our counsellor will reach out shortly. Meanwhile, ask me anything here."


def _enroll_message(sess):
    lang = _lang(sess)
    if lang == "Hindi":
        return f"🎉 यहाँ से enroll करें:\n{Config.PAYMENT_URL}\n\nकोई दिक्कत हो तो बताइए!"
    if lang == "Hinglish":
        return f"🎉 Yahan se enroll karo:\n{Config.PAYMENT_URL}\n\nKoi dikkat ho toh batao!"
    return f"🎉 Enroll here:\n{Config.PAYMENT_URL}\n\nTell me if you need any help!"


def _best_faq(intents, sess):
    for intent in _FAQ_PRIORITY:
        if intent in intents:
            ans = faq_answer(intent, _lang(sess))
            if ans:
                return intent, ans
    return None, None


def _course_details_answer(sess):
    """Grounded answer covering syllabus + projects + internship + certificate.
    Uses the student's already-selected course if we know it; otherwise
    presents both, but never suggests switching courses."""
    lang = _lang(sess)
    key = _selected_course_key(sess)
    courses = [COURSES[key]] if key else [COURSES["1"], COURSES["2"]]

    blocks = []
    for c in courses:
        modules = "; ".join(c["modules"])
        projects = ", ".join(c["projects"])
        includes = ", ".join(c["includes"])
        if lang == "Hindi":
            blocks.append(
                f"📘 *{c['name']}*\n• Syllabus: {modules}\n• Projects: {projects}\n• शामिल है: {includes}"
            )
        elif lang == "Hinglish":
            blocks.append(
                f"📘 *{c['name']}*\n• Syllabus: {modules}\n• Projects: {projects}\n• Included: {includes}"
            )
        else:
            blocks.append(
                f"📘 *{c['name']}*\n• Syllabus: {modules}\n• Projects: {projects}\n• Included: {includes}"
            )
    return "\n\n".join(blocks)


def _fallback_response(phone, sess):
    """Last resort when nothing else answered the question: guide toward a
    recommendation if we don't know their interest yet, otherwise offer a
    human counsellor instead of guessing."""
    if not sess.get("interest"):
        _start_recommendation(phone, sess)
        return

    lang = _lang(sess)
    if lang == "Hindi":
        msg = ("मुझे इसका पक्का जवाब नहीं पता 🙏 चाहें तो counsellor से connect करवा दूँ, "
               "या price/syllabus/certificate के बारे में पूछिए।")
    elif lang == "Hinglish":
        msg = ("Mujhe iska exact jawab nahi pata 🙏 chaho toh counsellor se connect karva doon, "
               "ya price/syllabus/certificate ke baare mein poochho.")
    else:
        msg = ("I'm not fully confident on that one 🙏 I can connect you with our counsellor, "
               "or you can ask me about price, syllabus, or the certificate.")
    _send(phone, sess, msg)


# --------------------------------------------------------------------------- #
# Guided course recommendation (never recommend cold)
# --------------------------------------------------------------------------- #
def _start_recommendation(phone, sess):
    sess["reco_stage"] = 1
    sess["reco_answers"] = {}
    _send(phone, sess, _RECO_QUESTIONS[1][_lang(sess)])


def _continue_recommendation(phone, sess, text):
    stage = sess["reco_stage"]
    sess["reco_answers"][stage] = text
    if stage < 3:
        sess["reco_stage"] = stage + 1
        _send(phone, sess, _RECO_QUESTIONS[stage + 1][_lang(sess)])
        return

    # Q3 directly asks "AI & Data or Marketing" — trust a clear answer to it
    # over the combined blob, since goal/background answers can otherwise
    # contain mixed signal words (e.g. "not into social media").
    key = _classify_track(sess["reco_answers"].get(3, ""))
    if not key:
        blob = " ".join(sess["reco_answers"].values())
        key = recommend_course(blob)

    sess["reco_stage"] = "done"
    sess["reco_recommendation"] = key
    _send(phone, sess, _recommendation_message(sess, key))


def _classify_track(answer3_text):
    """Best-effort read of the direct AI/Data-vs-Marketing answer. Returns a
    course key ('1' or '2') only when the signal is unambiguous, else None."""
    t = (answer3_text or "").lower()
    technical = any(w in t for w in ("ai", "data", "analytics", "python", "sql"))
    marketing = any(w in t for w in ("marketing", "social", "instagram", "ads", "content", "brand"))
    if technical and not marketing:
        return "1"
    if marketing and not technical:
        return "2"
    return None


def _recommendation_message(sess, key):
    course = COURSES[key]
    lang = _lang(sess)
    roles = ", ".join(course["roles"][:2])

    if lang == "Hindi":
        msg = (f"आपके answers के हिसाब से, *{course['name']}* (₹{course['price']}) आपके लिए best रहेगा — "
               f"इससे {roles} जैसे roles मिल सकते हैं। Full syllabus चाहिए या enroll link भेजूं?")
    elif lang == "Hinglish":
        msg = (f"Aapke answers ke hisaab se, *{course['name']}* (₹{course['price']}) aapke liye best rahega — "
               f"isse {roles} jaise roles mil sakte hain. Full syllabus chahiye ya enroll link bhejun?")
    else:
        msg = (f"Based on what you shared, *{course['name']}* (₹{course['price']}) looks like the best fit — "
               f"it can lead to roles like {roles}. Want the full syllabus, or shall I send the enroll link?")

    # Still mid-onboarding and haven't picked a course number yet -> nudge them along.
    if sess["step"] == 3 and not sess.get("interest"):
        nudge = ("\n\nReply *1* for AI & Data Science or *2* for Digital Marketing to continue."
                 if lang != "Hindi" else
                 "\n\nआगे बढ़ने के लिए *1* (AI & Data Science) या *2* (Digital Marketing) भेजें।")
        msg += nudge
    return msg


# --------------------------------------------------------------------------- #
# Lead persistence
# --------------------------------------------------------------------------- #
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
        "Payment Status": sess.get("payment_status", PAYMENT_PENDING),
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
    """Refreshes the lead's live fields, including 'Last Contact' — this is
    also what a follow-up scheduler should check to avoid messaging a student
    who is actively chatting right now."""
    if not sess.get("saved"):
        return
    sheets.update_lead(phone, {
        "Stage": sess.get("stage", STAGE_NEW),
        "Payment Status": sess.get("payment_status", PAYMENT_PENDING),
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
# AI passthrough (shared by onboarding reprompts and open conversation)
# --------------------------------------------------------------------------- #
def _ai_reply(sess, text):
    if not text:
        return None
    return ai.reply(
        memory={"name": sess.get("name"), "language": sess.get("language"),
                "interest": sess.get("interest")},
        history=sess.get("history", []),
        user_text=text,
    )


def _answer_or_reprompt(phone, sess, intents, prompt, text=""):
    """During onboarding, if the user asked a question, answer it then re-ask
    only the piece of info we still need — never repeats info already given.

    Tries the AI counsellor first (if configured) for a more natural, free-form
    answer grounded in the SmartVersa knowledge base. If AI is disabled,
    unavailable, or fails, falls back to the deterministic FAQ engine — so the
    bot answers naturally either way, and works completely free with no
    OpenAI/Anthropic key set.
    """
    ai_text = _ai_reply(sess, text)
    if ai_text:
        _send(phone, sess, ai_text)
    else:
        _, ans = _best_faq(intents, sess)
        if ans:
            _send(phone, sess, ans)
    _send(phone, sess, prompt)


def _is_course_info_question(text, intents):
    if "syllabus" in intents:
        return True
    t = text.lower()
    return any(p in t for p in _COURSE_INFO_PATTERNS)


def _wants_recommendation(text, intents):
    if "comparison" in intents:
        return True
    t = text.lower()
    return any(p in t for p in _RECOMMEND_PATTERNS)


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

    try:
        _dispatch(phone, sess, text, wa_name)
    finally:
        # Always refresh "Last Contact" on the session that is actually
        # current for this phone (handles the restart-creates-new-session case).
        current = _sessions.get(phone, sess)
        _update_lead_progress(phone, current)


def _dispatch(phone, sess, text, wa_name):
    # Restart anytime — the only thing that resets the conversation.
    if text.lower() in _RESTART_WORDS:
        _sessions[phone] = _new_session(wa_name, text)
        _send(phone, _sessions[phone], _welcome(_sessions[phone]))
        return

    intents = detect_intents(text)
    gained = score_for(intents)
    if gained:
        sess["score"] += gained
    _tag(sess, intents)
    _track_topic(sess, intents)

    # Explicit human/counsellor request at any point.
    if "human" in intents:
        sess["stage"] = STAGE_WARM
        _send(phone, sess, _handoff_message(sess))
        return

    # Once we know the student's name, let natural questions (course details,
    # "which course is best", an in-progress recommendation Q&A) work at any
    # step, not just after onboarding finishes.
    if sess.get("name"):
        if sess.get("reco_stage") in (1, 2, 3):
            _continue_recommendation(phone, sess, text)
            return

        if _is_course_info_question(text, intents):
            _send(phone, sess, _course_details_answer(sess))
            return

        if _wants_recommendation(text, intents):
            if sess.get("reco_stage") == "done":
                _send(phone, sess, _recommendation_message(sess, sess["reco_recommendation"]))
            else:
                _start_recommendation(phone, sess)
            return

    step = sess["step"]

    # ---------------- Onboarding ----------------
    if step == 1:
        # First-ever message: greet + ask name. Answer an opening question too.
        if not sess["name"] and len(sess["history"]) == 1:
            _answer_or_reprompt(phone, sess, intents, _welcome(sess), text)
            return
        sess["name"] = text
        sess["step"] = 2
        _send(phone, sess, _ask_language(sess))
        return

    if step == 2:
        mapping = {"1": "Hindi", "2": "English", "3": "Hinglish"}
        if text in mapping:
            sess["language"] = mapping[text]
            sess["step"] = 3
            _send(phone, sess, _ask_course(sess))
        else:
            _answer_or_reprompt(phone, sess, intents, _ask_language(sess), text)
        return

    if step == 3:
        if text in ("1", "2", "3"):
            if _send_course(phone, sess, text):
                sess["step"] = 4
                lang = _lang(sess)
                q = ("Are you interested?\n\n1. Yes, enroll me\n2. Talk to a counsellor"
                     if lang == "English" else
                     "Interested?\n\n1. Haan, enroll karna hai\n2. Counsellor se baat karni hai")
                _send(phone, sess, q)
        else:
            _answer_or_reprompt(phone, sess, intents, _ask_course(sess), text)
        return

    if step == 4:
        if text == "1":
            sess["stage"] = STAGE_HOT
            sess["score"] += 20
            sess["step"] = 5
            lang = _lang(sess)
            _send(phone, sess,
                  ("Great 😊 Please share your email (or type SKIP):"
                   if lang != "Hindi" else "बढ़िया 😊 अपना email दें (या SKIP लिखें):"))
        elif text == "2":
            sess["stage"] = STAGE_WARM
            sess["step"] = 5
            _send(phone, sess, _handoff_message(sess) + "\n\n📧 Email? (or type SKIP):")
        else:
            _answer_or_reprompt(phone, sess, intents,
                                 "Please reply 1 (Yes) or 2 (Counsellor).", text)
        return

    if step == 5:
        sess["email"] = "" if text.upper() == "SKIP" else text
        _save_lead(phone, sess)
        sess["step"] = 6
        if sess["stage"] == STAGE_HOT:
            _send(phone, sess, _enroll_message(sess))
            sess["stage"] = STAGE_PAYMENT_SENT
            sess["payment_status"] = PAYMENT_LINK_SENT
        else:
            lang = _lang(sess)
            _send(phone, sess,
                  ("✅ Sent to our counsellor. Ask me anything meanwhile!"
                   if lang == "English" else
                   "✅ Counsellor ko bhej diya. Meanwhile kuch bhi poochho!"))
        return

    # ---------------- Open conversation (post-onboarding) ----------------
    _open_conversation(phone, sess, text, intents)


def _open_conversation(phone, sess, text, intents):
    # If the user is ready to pay, always give the link and mark the stage.
    if "payment" in intents:
        _send(phone, sess, _enroll_message(sess))
        sess["stage"] = STAGE_PAYMENT_SENT
        sess["payment_status"] = PAYMENT_LINK_SENT
        return

    # Try the AI counsellor first (if enabled).
    ai_text = _ai_reply(sess, text)
    if ai_text:
        _send(phone, sess, ai_text)
        return

    # Rule-based fallback: answer FAQ, guide to a recommendation, or hand off.
    _, ans = _best_faq(intents, sess)
    if ans:
        _send(phone, sess, ans)
        return

    _fallback_response(phone, sess)

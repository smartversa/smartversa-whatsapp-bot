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
import re

from config import Config
from logger import log, safe
import whatsapp
import sheets
import crm
import ai
from knowledge import (
    COURSES, course_by_choice, detect_intents, detect_intents_smart, score_for,
    faq_answer, detect_language, recommend_course,
    objection_subtype, objection_answer, detect_background, detect_goal,
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
    "payment_failure", "payment", "price", "emi", "discount", "scholarship",
    "certificate", "certificate_value", "internship", "offer_letter",
    "placement", "career_outcomes", "salary", "freelancing", "higher_studies",
    "resume", "linkedin", "portfolio", "interview", "mentors",
    "refund", "duration", "timing", "batch_size", "enrollment_process",
    "prerequisite", "trust", "msme", "about", "support", "doubts", "notes",
    "projects", "tools_query", "stream_eligibility", "audience_fit",
    "device_requirement", "assignments", "demo", "experienced",
    "beginner_doubt", "parents", "objection", "after_payment",
    "small_talk", "greeting", "thanks", "acknowledge", "farewell",
]

_RESTART_WORDS = {"restart", "reset", "menu", "start over", "start again", "shuru"}

# --------------------------------------------------------------------------- #
# Phrase normalization — bridges real WhatsApp phrasing to the exact keyword
# phrases knowledge.py's detect_intents() already looks for. knowledge.py is
# NOT modified; this only affects which text detect_intents() sees, never
# what's stored/displayed/logged. Each entry: if `needle` appears anywhere in
# the message, we append the exact `keyword` phrase knowledge.py recognizes,
# so the existing FAQ (beginner_doubt / stream_eligibility / device_requirement
# / etc.) fires instead of the "not fully confident" fallback.
# --------------------------------------------------------------------------- #
_PHRASE_SYNONYMS = [
    # "Mujhe coding nahi aati" / "coding nahi aata" -> beginner_doubt
    ("coding nahi aati", "mujhe nahi aata"),
    ("coding nahi aata", "mujhe nahi aata"),
    ("nahi aati", "mujhe nahi aata"),
    ("nahi aata hai", "mujhe nahi aata"),
    # "Main commerce/arts/science se hu" -> stream_eligibility
    ("commerce se hu", "commerce student"),
    ("commerce se hoon", "commerce student"),
    ("arts se hu", "arts student"),
    ("arts se hoon", "arts student"),
    ("science se hu", "science student"),
    ("science se hoon", "science student"),
    ("bca se hu", "any stream"),
    ("bca se hoon", "any stream"),
    # "Sirf mobile hai" -> device_requirement
    ("sirf mobile", "mobile se ho jayega"),
    ("mobile hi hai", "mobile se ho jayega"),
    ("mobile se hoga", "mobile se ho jayega"),
    ("only mobile", "mobile se ho jayega"),
]

# --------------------------------------------------------------------------- #
# Conversation-quality normalization — greetings/typos/emojis/short acks.
# Real WhatsApp users type "hlo", "hy", "okk", "hmmm", "yes", "han", send bare
# emojis, etc. knowledge.py's keyword lists don't cover every variant, which
# was causing common greetings/acknowledgements to fall through to the
# fallback instead of being recognized. This ONLY affects the text handed to
# detect_intents() for matching — the real message is still what's stored,
# displayed, and logged. knowledge.py itself is never touched.
# --------------------------------------------------------------------------- #
_EMOJI_TO_WORD = {
    "\U0001F44D": "okay", "\U0001F64F": "thanks", "\U0001F60A": "okay",
    "\u2764\uFE0F": "thanks", "\U0001F602": "okay",
    "\U0001F600": "okay", "\U0001F642": "okay", "\U0001F44C": "okay",
    "\U0001F525": "okay", "\U0001F601": "okay", "\U0001F64C": "thanks",
}

# Bare acknowledgement / filler words -> read as "okay" (knowledge.py's
# "acknowledge" intent already fires on "okay") even though its own keyword
# list doesn't cover all these short-reply variants.
_ACK_SYNONYMS = {
    "ok", "okk", "okkk", "k", "kk", "hmm", "hmmm", "hmmmm", "han", "haan",
    "yes", "yess", "yup", "yeah", "ya", "done", "sure", "noted", "gotit",
    "got it", "cool", "achha", "acha", "theek", "theek h", "thik hai",
}

# Praise / short positive reactions -- treated as acknowledgement too.
_PRAISE_SYNONYMS = {"nice", "great", "awesome", "good", "superb", "perfect", "wow", "amazing"}

# Common greeting misspellings not in knowledge.py's "greeting" keyword list.
_GREETING_TYPOS = {
    "hlo", "hy", "heyy", "heyyy", "hii", "hiii", "hiiii", "helo", "hellow",
    "gm", "gud morning", "gud evening", "gud afternoon", "yo", "sup",
    "heya", "hey there", "hola", "namaskar", "namaskaar", "morning",
    "evening", "afternoon", "hlw", "hey buddy", "hii there", "hiya",
}

# Small-talk phrasing not in knowledge.py's own keyword list.
_SMALL_TALK_TYPOS = {"who are you", "kon ho tum", "tum kaun ho", "aap kya ho"}

# Common typos for words that already have real answers in knowledge.py --
# fixed before intent matching so the bot never says "I don't know" about
# something it actually knows.
_TYPO_FIXES = {
    "certficate": "certificate", "certifcate": "certificate", "certificat": "certificate",
    "internsip": "internship", "intership": "internship", "interniship": "internship",
    "placment": "placement", "placemnt": "placement", "plasment": "placement",
    "pyhton": "python", "digitel": "digital", "sylabus": "syllabus",
    "syllabuss": "syllabus", "projekt": "project",
    "linkdin": "linkedin", "linkedn": "linkedin", "resme": "resume", "resum": "resume",
    "scholorship": "scholarship", "scholorshp": "scholarship", "schlorship": "scholarship",
    "discont": "discount", "discoutn": "discount", "emii": "emi",
    "geniune": "genuine", "geuinue": "genuine", "regd": "registered",
}


def _normalize_for_intent(text: str) -> str:
    """Returns a version of `text` used ONLY for detect_intents() matching.
    The original text is still what's stored, displayed, and logged."""
    t = (text or "").strip()
    low = t.lower()

    # Emoji-only (or emoji + minimal text) messages.
    for emoji, word in _EMOJI_TO_WORD.items():
        if emoji in t:
            low = f"{low} {word}"

    # Bare word normalization (exact match on the stripped message, since
    # these are short standalone replies, not fragments of longer sentences).
    stripped = re.sub(r"[^\w\s]", "", low).strip()
    if stripped in _ACK_SYNONYMS:
        low = f"{low} okay"
    elif stripped in _PRAISE_SYNONYMS:
        low = f"{low} okay"
    elif stripped in _GREETING_TYPOS:
        low = f"{low} hi"

    for phrase in _SMALL_TALK_TYPOS:
        if phrase in low:
            low = f"{low} who made you"

    # Known typo fixes, word-boundary safe.
    for wrong, right in _TYPO_FIXES.items():
        low = re.sub(r"(?<!\w)" + re.escape(wrong) + r"(?!\w)", right, low)

    # Phrase-level synonyms (see _PHRASE_SYNONYMS above).
    for needle, keyword in _PHRASE_SYNONYMS:
        if needle in low:
            low = f"{low} {keyword}"

    return low


# --------------------------------------------------------------------------- #
# Anti-repetition — never send the exact same acknowledge/farewell/thanks/
# fallback reply twice in a row, so short back-and-forth exchanges ("Ok" x5,
# "bye" x3) don't read like a broken script.
# --------------------------------------------------------------------------- #
_ACK_VARIANTS = {
    "English": [
        "\U0001F44D Great! Let me know if you'd like to know anything else — pricing, syllabus, or how to enroll.",
        "Got it \U0001F60A Feel free to ask about pricing, syllabus, certificate, or internship anytime.",
        "\U0001F44C Cool, I'm here whenever you want to know more about the programs.",
    ],
    "Hindi": [
        "\U0001F44D बढ़िया! कुछ और जानना हो — pricing, syllabus, या enroll कैसे करें — तो बताइए।",
        "समझ गया \U0001F60A pricing, syllabus, certificate या internship के बारे में कभी भी पूछ सकते हैं।",
        "\U0001F44C ठीक है, program के बारे में कुछ भी जानना हो तो बताइए।",
    ],
    "Hinglish": [
        "\U0001F44D Badhiya! Kuch aur jaanna ho — pricing, syllabus, ya enroll kaise karein — toh batao.",
        "Got it \U0001F60A Pricing, syllabus, certificate ya internship ke baare mein kabhi bhi pooch sakte ho.",
        "\U0001F44C Theek hai, program ke baare mein kuch bhi jaanna ho toh batao.",
    ],
}

_FAREWELL_VARIANTS = {
    "English": [
        "\U0001F44B Thanks for chatting! Feel free to reach out anytime — have a great day!",
        "Take care! \U0001F60A I'm right here whenever you want to continue.",
    ],
    "Hindi": [
        "\U0001F44B बात करने के लिए धन्यवाद! जब चाहें फिर से संपर्क करें — आपका दिन शुभ हो!",
        "ध्यान रखिए \U0001F60A जब भी बात करनी हो, मैं यहीं हूँ।",
    ],
    "Hinglish": [
        "\U0001F44B Chat karne ke liye thanks! Jab bhi chaho phir se contact karo — have a great day!",
        "Take care \U0001F60A Jab bhi baat karni ho, main yahin hoon.",
    ],
}

_THANKS_VARIANTS = {
    "English": [
        "You're welcome! \U0001F60A Let me know if you have any other questions.",
        "Anytime! \U0001F64C I'm here if anything else comes to mind.",
    ],
    "Hindi": [
        "आपका स्वागत है! \U0001F60A कोई और सवाल हो तो बताइए।",
        "कोई बात नहीं! \U0001F64C कुछ और पूछना हो तो बताइए।",
    ],
    "Hinglish": [
        "Koi baat nahi! \U0001F60A Aur koi sawaal ho toh batao.",
        "Anytime! \U0001F64C Kuch aur poochna ho toh batao.",
    ],
}

_FALLBACK_VARIANTS = {
    "English": [
        "I'm not fully confident on that one \U0001F64F I can connect you with our counsellor, "
        "or you can ask me about price, syllabus, or the certificate.",
        "That's a bit outside what I can confirm myself \U0001F64F Want me to loop in our counsellor, "
        "or ask about pricing, projects, or internship instead?",
    ],
    "Hindi": [
        "मुझे इसका पक्का जवाब नहीं पता \U0001F64F चाहें तो counsellor से connect करवा दूँ, "
        "या price/syllabus/certificate के बारे में पूछिए।",
        "यह मुझे confirm नहीं है \U0001F64F चाहें तो counsellor से बात करवा दूँ, "
        "या price/projects/internship के बारे में पूछिए।",
    ],
    "Hinglish": [
        "Mujhe iska exact jawab nahi pata \U0001F64F chaho toh counsellor se connect karva doon, "
        "ya price/syllabus/certificate ke baare mein poochho.",
        "Yeh mujhe confirm nahi hai \U0001F64F chaho toh counsellor se baat karva doon, "
        "ya price/projects/internship ke baare mein poochho.",
    ],
}


def _last_bot_text(sess):
    for turn in reversed(sess.get("history", [])):
        if turn.get("role") == "bot":
            return turn.get("text", "")
    return None


def _varied(sess, lang, variants):
    """Pick a reply that differs from the last thing the bot actually said,
    so acknowledgements/farewells/fallbacks don't repeat verbatim back to back."""
    pool = variants.get(lang, variants["English"])
    last = _last_bot_text(sess)
    for candidate in pool:
        if candidate != last:
            return candidate
    return pool[0]

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
    "which one should i pick", "konsa course", "kaunsa course",
    "kaun sa course", "mere liye konsa course", "mere liye best",
    "which course should i choose", "which course should i pick",
    "suggest me a course", "suggest course",
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
        "followup_category": "",  # last detected follow-up signal category (Phase 4)
        "followup_reason": "",    # phrase that triggered it
        "background": "",         # multi-turn memory: commerce/arts/science/bca/mba
        "goal": "",                # multi-turn memory: job/freelancing/higher_studies/business
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


def _track_background_goal(sess, text):
    """Multi-turn memory: once a student mentions their academic background
    (commerce/arts/science/...) or their goal (job/freelancing/...) anywhere
    in the chat, remember it for the rest of the conversation so later
    questions ('Can I learn Python?') can be answered/recommended in context
    without re-asking."""
    bg = detect_background(text)
    if bg and not sess.get("background"):
        sess["background"] = bg
    goal = detect_goal(text)
    if goal and not sess.get("goal"):
        sess["goal"] = goal


# --------------------------------------------------------------------------- #
# Follow-up intelligence engine
#
# Reads every inbound message for a "soft objection" / stalling / interest
# signal (the kind of thing a human counsellor would mentally file away —
# "this one needs a parent's okay", "this one thinks it's expensive", etc.)
# and silently tags the lead with a follow-up category + the exact phrase
# that triggered it. This never changes what the bot replies with — it only
# annotates the lead so app.py's follow-up cadence (Phase 4) can pick a
# relevant, non-repetitive message instead of a generic reminder.
#
# Storage: piggybacks on the existing "Tags" column (a "fu_<category>"
# entry, always kept singular — a fresh signal replaces the old one) and the
# existing "Notes" column (one short audit line via crm.add_note). No new
# sheet columns, no change to sheets.py/crm.py.
# --------------------------------------------------------------------------- #
_FOLLOWUP_RULES = [
    # (category, phrases) — checked in order, first match wins, so more
    # specific/decisive signals (Cold, Hot) are listed before soft stalls.
    ("Cold", (
        "not interested", "not intrested", "nahi chahiye", "nhi chahiye",
        "no thanks", "not needed", "no need", "not required",
    )),
    ("Hot", (
        "pay now", "buy now", "make payment", "checkout", "enroll now",
        "enrol now", "i want to join", "i want to enroll", "ready to pay",
    )),
    ("Parent", (
        "ask my parents", "ask parents", "ask my mom", "ask my dad",
        "talk to my parents", "need to ask parents", "parents ko puchna",
        "mummy papa", "mumma papa", "papa se puchna", "mummy se puchna",
        "guardian ki permission", "family se baat",
    )),
    ("Budget", (
        "too expensive", "very expensive", "bahut mehenga", "bahut mehnga",
        "can't afford", "cant afford", "no money", "not affordable",
        "high fees", "kam paise", "paise nahi hai", "mehenga hai",
        "koi discount", "discount hai kya",
    )),
    ("Need Call", (
        "call me", "please call", "mujhe call karo", "call karo",
        "callback", "call back",
    )),
    ("Need Demo", (
        "send details", "send info", "send information", "share details",
        "demo chahiye", "free demo", "trial class", "demo class",
    )),
    ("Certificate", (
        "need certificate", "certificate chahiye", "certificate milega",
    )),
    ("Already Working", (
        "already working", "i have a job", "already job kar raha",
        "already employed", "job kar rahi hu", "job kar raha hu",
    )),
    ("Busy", (
        "busy", "abhi busy hu", "no time right now", "not free right now",
        "abhi time nahi", "busy hu abhi",
    )),
    ("Thinking", (
        "i'll tell tomorrow", "ill tell tomorrow", "tell tomorrow",
        "kal bataunga", "kal batati hu", "kal bataungi", "let me think",
        "will think", "thinking about it", "soch raha hu", "soch rahi hu",
        "need time", "need some time", "give me time", "abhi decide nahi",
    )),
]


def _detect_followup_signal(text_l: str):
    """Scan a lowercased message for the first matching follow-up signal.
    Returns (category, matched_phrase) or (None, None)."""
    for category, phrases in _FOLLOWUP_RULES:
        for phrase in phrases:
            if phrase in text_l:
                return category, phrase
    return None, None


def _apply_followup_category(sess, category):
    """Stamp the lead's session tags with a single fu_<category> marker,
    replacing any earlier one — a follow-up signal is a snapshot of the
    lead's latest posture, not a running tally. Piggybacks on the same
    "tags" set that already feeds the Tags column via _update_lead_progress
    / _save_lead, so no extra sheet write path is introduced."""
    sess["tags"] = {t for t in sess.get("tags", set()) if not str(t).startswith("fu_")}
    sess["tags"].add(f"fu_{category.lower().replace(' ', '_')}")
    sess["followup_category"] = category


@safe(default=None, label="bot._track_followup_signal")
def _track_followup_signal(phone, sess, text):
    """Runs silently in the background on every inbound message — never
    sends a reply itself and never affects which reply the rest of the
    pipeline sends (requirement: never interfere with AI replies)."""
    text_l = (text or "").strip().lower()
    if not text_l:
        return
    category, phrase = _detect_followup_signal(text_l)
    if not category:
        return

    _apply_followup_category(sess, category)
    sess["followup_reason"] = phrase

    # An explicit "not interested" should also stop the follow-up cadence
    # outright (same mechanism already used for Converted leads), not just
    # get logged as a category.
    if category == "Cold":
        sess["stage"] = STAGE_NOT_INTERESTED

    # Log a short audit trail on the lead only once it actually exists as a
    # sheet row; pre-save signals are still captured via sess["tags"] and
    # will land on the row the moment _save_lead runs.
    if sess.get("saved"):
        try:
            crm.add_note(phone, f'Follow-up signal: "{phrase}" -> {category}')
        except Exception:
            log.exception("bot: failed to log follow-up note for %s", phone)


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


def _best_faq(intents, sess, text=""):
    for intent in _FAQ_PRIORITY:
        if intent in intents:
            if intent == "acknowledge":
                return intent, _varied(sess, _lang(sess), _ACK_VARIANTS)
            if intent == "farewell":
                return intent, _varied(sess, _lang(sess), _FAREWELL_VARIANTS)
            if intent == "thanks":
                return intent, _varied(sess, _lang(sess), _THANKS_VARIANTS)
            if intent == "objection":
                # Give a tailored reply for *why* they're objecting when we
                # can tell (too expensive / need parents' okay / need time /
                # already learning elsewhere), else the generic objection FAQ.
                sub = objection_subtype(text)
                tailored = objection_answer(sub, _lang(sess)) if sub else ""
                if tailored:
                    return intent, tailored
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
    msg = _varied(sess, lang, _FALLBACK_VARIANTS)
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
        key = recommend_course(blob, sess.get("background", ""), sess.get("goal", ""))

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
                "interest": sess.get("interest"), "background": sess.get("background"),
                "goal": sess.get("goal")},
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
        _, ans = _best_faq(intents, sess, text)
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

    intents = detect_intents_smart(_normalize_for_intent(text))
    gained = score_for(intents)
    if gained:
        sess["score"] += gained
    _tag(sess, intents)
    _track_topic(sess, intents)
    _track_followup_signal(phone, sess, text)
    _track_background_goal(sess, text)

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
        # First-ever message: greet + ask name. Answer an opening question too
        # -- but a plain "Hi"/"Hello"/emoji with nothing else to answer should
        # only get ONE welcome, not a greeting-FAQ reply stacked on top of it.
        if not sess["name"] and len(sess["history"]) == 1:
            substantive = intents - {"greeting", "small_talk", "acknowledge"}
            if not substantive:
                _send(phone, sess, _welcome(sess))
            else:
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
    _, ans = _best_faq(intents, sess, text)
    if ans:
        _send(phone, sess, ans)
        return

    _fallback_response(phone, sess)

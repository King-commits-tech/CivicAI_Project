"""
Conversational chatbot.
It talks in the SAME language the citizen uses (English / Hindi / Hinglish), asks follow-up questions
only when something is missing (location, duration, unclear category) and then shows an AI summary
card for the citizen to confirm.

The conversation "draft" is kept in the Flask session:
  stage: idle -> need_category -> need_location -> need_duration -> confirm
"""

import re

from ai.engine import detect_language, extract_duration, clean_location_answer
from ai.training_data import DEPARTMENTS
from core import db
from core.services import analyse, create_complaint

T = {
    "greet": {
        "en": "Hello! 👋 I am CivicAI, your complaint assistant. Just tell me your problem in your own words - English, हिंदी or Hinglish. You can also press 🎤 and speak.",
        "hi": "नमस्ते! 👋 मैं CivicAI हूँ। अपनी समस्या अपने शब्दों में बताइए - हिंदी, English या Hinglish में। आप 🎤 दबाकर बोल भी सकते हैं।",
        "hinglish": "Namaste! 👋 Main CivicAI hoon. Apni problem apne shabdon me batao - Hindi, English ya Hinglish me. 🎤 dabakar bol bhi sakte ho.",
    },
    "unclear": {
        "en": "I could not clearly understand the type of problem 🤔. Please choose the closest one, or describe it a little more:",
        "hi": "मैं समस्या का प्रकार ठीक से समझ नहीं पाया 🤔। कृपया सबसे नज़दीकी विकल्प चुनें या थोड़ा और बताइए:",
        "hinglish": "Main problem ka type theek se samajh nahi paaya 🤔. Sabse close option chuno ya thoda aur batao:",
    },
    "understood": {
        "en": "Got it ✅ This looks like a <b>{cat}</b> issue (<b>{sub}</b>).",
        "hi": "समझ गया ✅ यह <b>{cat}</b> की समस्या लगती है (<b>{sub}</b>)।",
        "hinglish": "Samajh gaya ✅ Ye <b>{cat}</b> ki problem lag rahi hai (<b>{sub}</b>).",
    },
    "ask_location": {
        "en": "📍 Where exactly is this problem? (colony / ward / landmark)",
        "hi": "📍 यह समस्या कहाँ है? (कॉलोनी / वार्ड / पास की जगह)",
        "hinglish": "📍 Ye problem kahan hai? (colony / ward / landmark batao)",
    },
    "ask_duration": {
        "en": "⏱️ Since when are you facing this? (e.g. 'since yesterday', '3 days') - or tap Skip.",
        "hi": "⏱️ यह समस्या कब से है? (जैसे 'कल से', '3 दिन') - या Skip दबाएँ।",
        "hinglish": "⏱️ Ye problem kab se hai? (jaise 'kal se', '3 din') - ya Skip dabao.",
    },
    "confirm": {
        "en": "Here is what I understood. Please check and press <b>Submit</b> 👇",
        "hi": "मैंने यह समझा है। कृपया जाँचें और <b>Submit</b> दबाएँ 👇",
        "hinglish": "Maine ye samjha hai. Check karke <b>Submit</b> dabao 👇",
    },
    "similar": {
        "en": "ℹ️ {n} other citizen(s) already reported a similar problem here. I have linked them - this increases the priority.",
        "hi": "ℹ️ यहाँ {n} और नागरिकों ने ऐसी ही शिकायत की है। मैंने इन्हें जोड़ दिया है - इससे प्राथमिकता बढ़ गई है।",
        "hinglish": "ℹ️ Yahan {n} aur logon ne aisi hi complaint ki hai. Maine inko link kar diya - isse priority badh gayi.",
    },
    "repeat": {
        "en": "⚠️ This problem was 'resolved' here recently but came back. I will flag it for strict review.",
        "hi": "⚠️ यह समस्या हाल ही में 'हल' बताई गई थी पर फिर आ गई। मैं इसे सख्त जाँच के लिए भेजूँगा।",
        "hinglish": "⚠️ Ye problem abhi 'solve' batayi gayi thi par wapas aa gayi. Main isko strict review ke liye flag karunga.",
    },
    "done": {
        "en": "🎉 Complaint registered!<br>Your ID: <b class='cid'>{cid}</b><br>Sent to <b>{dept}</b>. Expected within <b>{h} hours</b>. You will get SMS / e-mail updates.",
        "hi": "🎉 शिकायत दर्ज हो गई!<br>आपकी ID: <b class='cid'>{cid}</b><br><b>{dept}</b> को भेजी गई। <b>{h} घंटे</b> में समाधान अपेक्षित। SMS / ई-मेल से अपडेट मिलेंगे।",
        "hinglish": "🎉 Complaint register ho gayi!<br>Aapki ID: <b class='cid'>{cid}</b><br><b>{dept}</b> ko bhej di. <b>{h} ghante</b> me solve hona chahiye. SMS / e-mail se update milenge.",
    },
    "cancel": {
        "en": "Okay, cancelled. Tell me a new problem any time 🙂",
        "hi": "ठीक है, रद्द कर दिया। कभी भी नई समस्या बताइए 🙂",
        "hinglish": "Theek hai, cancel kar diya. Kabhi bhi nayi problem batao 🙂",
    },
    "thanks": {
        "en": "You're welcome! 🙏 Anything else I can help with?",
        "hi": "आपका स्वागत है! 🙏 और कुछ मदद चाहिए?",
        "hinglish": "Welcome! 🙏 Aur kuch madad chahiye?",
    },
    "not_found": {
        "en": "I couldn't find complaint {cid}. Please check the ID.",
        "hi": "शिकायत {cid} नहीं मिली। कृपया ID जाँचें।",
        "hinglish": "Complaint {cid} nahi mili. ID check karo.",
    },
    "status": {
        "en": "📋 <b>{cid}</b> - status: <b>{status}</b><br>Department: {dept}<br>Deadline: {dl}",
        "hi": "📋 <b>{cid}</b> - स्थिति: <b>{status}</b><br>विभाग: {dept}<br>समय सीमा: {dl}",
        "hinglish": "📋 <b>{cid}</b> - status: <b>{status}</b><br>Department: {dept}<br>Deadline: {dl}",
    },
}

GREETINGS = {"hi", "hello", "hey", "namaste", "namaskar", "hii", "helo", "good morning", "good evening", "नमस्ते", "नमस्कार", "हेलो"}
THANKS = {"thanks", "thank you", "thank u", "shukriya", "dhanyawad", "धन्यवाद", "शुक्रिया", "ok thanks"}
CANCEL = {"cancel", "restart", "reset", "start again", "new complaint", "रद्द", "band karo", "cancel karo"}
SKIP = {"skip", "dont know", "don't know", "pata nahi", "nahi pata", "पता नहीं", "no idea", "-"}


def t(key, lang, **kw):
    return T[key].get(lang, T[key]["en"]).format(**kw)


def reply(messages, stage="idle", analysis=None, chips=None, card=None, done=None):
    return {"messages": messages if isinstance(messages, list) else [messages], "stage": stage,
            "analysis": analysis, "chips": chips or [], "card": card, "done": done}


def _next_step(draft):
    """Decide what to ask next based on what is still missing."""
    lang = draft["lang"]
    a = analyse(draft["text"], draft.get("location"), draft.get("duration_hours"))
    if draft.get("forced_category"):
        a = analyse(draft["text"] + " " + draft["forced_category"], draft.get("location"), draft.get("duration_hours"))
    draft["location"] = draft.get("location") or a["location"]
    if draft.get("duration_hours") is None and a["duration_hours"] is not None:
        draft["duration_hours"] = a["duration_hours"]

    msgs = []
    if not draft.get("announced"):
        msgs.append(t("understood", lang, cat=a["category"], sub=a["subtype"]))
        draft["announced"] = True

    if not draft["location"]:
        draft["stage"] = "need_location"
        msgs.append(t("ask_location", lang))
        return reply(msgs, "need_location", a)
    if draft.get("duration_hours") is None and not draft.get("duration_skipped"):
        draft["stage"] = "need_duration"
        msgs.append(t("ask_duration", lang))
        return reply(msgs, "need_duration", a, chips=["Skip", "Today", "Since yesterday", "3 days", "1 week"])

    draft["stage"] = "confirm"
    if a["similar_open"]:
        msgs.append(t("similar", lang, n=len(a["similar_open"])))
    if a["similar_resolved"]:
        msgs.append(t("repeat", lang))
    msgs.append(t("confirm", lang))
    card = {"description": draft["text"], "location": draft["location"], "category": a["category"], "subtype": a["subtype"],
            "department": a["department"], "priority": a["priority"], "severity": a["severity"],
            "deadline_hours": a["deadline_hours"], "duration": a["duration_hours"]}
    return reply(msgs, "confirm", a, card=card)


def handle(session, message):
    msg = (message or "").strip()
    low = msg.lower().strip(" .!?")
    draft = session.get("draft") or {"stage": "idle"}
    lang = detect_language(msg) if msg else draft.get("lang", "en")
    if draft.get("lang") and len(msg.split()) <= 3 and lang == "en" and not re.search(r"[a-z]{4,}", low):
        lang = draft["lang"]  # short answers like "3 din" keep the earlier language

    def save(r):
        session["draft"] = draft
        session.modified = True
        return r

    if not msg:
        return reply(t("greet", "en"))

    # ---------- commands that work at any time
    m = re.search(r"\b(civ-\d{4}-[a-z]{2,3}-\d{4})\b", low)
    if m:
        cid = m.group(1).upper()
        c = db.query("SELECT * FROM complaints WHERE id=?", (cid,), one=True)
        if not c:
            return reply(t("not_found", lang, cid=cid))
        return reply(t("status", lang, cid=cid, status=c["status"], dept=c["department"], dl=c["deadline"][:16]),
                     chips=[f"Open tracking: {cid}"])
    if low in CANCEL:
        session["draft"] = {"stage": "idle"}
        return reply(t("cancel", lang))
    if low in THANKS:
        return reply(t("thanks", lang))
    if low in GREETINGS and draft["stage"] == "idle":
        return reply(t("greet", lang))

    stage = draft.get("stage", "idle")

    if stage == "need_location":
        draft["location"] = clean_location_answer(msg)
        return save(_next_step(draft))

    if stage == "need_duration":
        if low in SKIP:
            draft["duration_skipped"] = True
        else:
            h, _ = extract_duration(msg)
            if h is None:
                draft["duration_skipped"] = True
                # the citizen probably gave a better location instead of a time -> use it
                if len(msg.split()) <= 5 and not re.search(r"\d", msg):
                    better = clean_location_answer(msg)
                    old = draft.get("location") or ""
                    draft["location"] = f"{better} ({old})" if old.lower().startswith("near") else better
            draft["duration_hours"] = h
        return save(_next_step(draft))

    if stage == "need_category":
        if msg in DEPARTMENTS:
            draft["forced_category"] = msg
        else:
            draft["text"] = draft["text"] + ". " + msg
        return save(_next_step(draft))

    # ---------- new complaint (idle or confirm stage -> treat as new / extra detail)
    if stage == "confirm":
        draft["text"] = draft["text"] + ". " + msg
        return save(_next_step(draft))

    draft = {"stage": "idle", "text": msg, "lang": lang, "location": None, "duration_hours": None}
    a = analyse(msg)
    if not a["has_domain_words"] and a["confidence"] < 45:
        draft["stage"] = "need_category"
        return save(reply(t("unclear", lang), "need_category", a, chips=list(DEPARTMENTS.keys())))
    return save(_next_step(draft))


def submit(session, user):
    draft = session.get("draft") or {}
    if draft.get("stage") != "confirm":
        return None
    text = draft["text"]
    if draft.get("forced_category"):
        text = text + " (" + draft["forced_category"] + ")"
    cid, a = create_complaint(user, text, draft.get("location"), draft.get("duration_hours"))
    session["draft"] = {"stage": "idle", "lang": draft.get("lang", "en")}
    session.modified = True
    return reply(t("done", draft.get("lang", "en"), cid=cid, dept=a["department"], h=a["deadline_hours"]),
                 done={"id": cid}, chips=[f"Open tracking: {cid}"])

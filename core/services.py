"""
Business logic:
  - analyse()            : run the full AI pipeline on a complaint text
  - create_complaint()   : unique ID, routing, deadline, duplicate/repeat detection, notifications
  - run_escalation()     : reminders -> extension -> Level 1 -> Level 2 -> Level 3 (CM Helpdesk)
  - update_status()      : officer actions
  - submit_feedback()    : AI checks if the citizen is really satisfied, otherwise REOPENS
  - analytics()          : dashboard numbers, department performance score, hotspot prediction
"""

import json
import random
from collections import Counter, defaultdict
from datetime import timedelta

from ai.engine import (ComplaintClassifier, SimilarityEngine, compute_severity, detect_language,
                       detect_subtype, evaluate_feedback, extract_duration, extract_location, LANG_NAMES)
from ai.training_data import DEPARTMENTS
from core import db

print(" * Training the AI model (English + Hindi + Hinglish)...")
CLASSIFIER = ComplaintClassifier()
print(f" * AI ready. Accuracy on unseen test sentences: {CLASSIFIER.test_accuracy}%")
SIMILARITY = SimilarityEngine()

OPEN_STATUSES = ("Submitted", "Assigned", "Under Review", "Action Initiated", "Escalated", "Reopened")


# ================================================================ AI pipeline
def open_or_recent(category, ref=None):
    """Complaints of this category that were open, or resolved in the last 30 days, at time `ref`."""
    ref = ref or db.now()
    cutoff, ref_s = db.ts(ref - timedelta(days=30)), db.ts(ref)
    rows = db.query("SELECT id, description, location, category, status, created_at, resolved_at FROM complaints "
                    "WHERE category=? AND created_at <= ?", (category, ref_s))
    out = []
    for r in rows:
        if r["resolved_at"] and r["resolved_at"] > ref_s:
            r["status"], r["resolved_at"] = "Assigned", None      # it was still open at that time
        if r["status"] in OPEN_STATUSES or (r["resolved_at"] and r["resolved_at"] >= cutoff):
            out.append(r)
    return out


def analyse(text, location=None, duration_hours=None, ref=None):
    lang = detect_language(text)
    pred = CLASSIFIER.predict(text)
    cat = pred["category"]
    sub = detect_subtype(text, cat)
    loc = location or extract_location(text)
    dur, dur_text = (duration_hours, None) if duration_hours is not None else extract_duration(text)

    similar = SIMILARITY.find_similar(text, loc, cat, open_or_recent(cat, ref)) if loc else []
    similar_open = [s for s in similar if s["status"] in OPEN_STATUSES]
    similar_resolved = [s for s in similar if s["status"] not in OPEN_STATUSES]

    sev = compute_severity(text, cat, sub, dur, len(similar_open))
    dept = DEPARTMENTS[cat]
    return {
        "language": lang,
        "language_name": LANG_NAMES[lang],
        "category": cat,
        "confidence": pred["confidence"],
        "top3": pred["top3"],
        "keywords": pred["keywords"],
        "has_domain_words": CLASSIFIER.has_domain_words(text),
        "subtype": sub,
        "location": loc,
        "duration_hours": dur,
        "duration_text": dur_text,
        "department": dept["name"],
        "officer": dept["officer"],
        "severity": sev["score"],
        "priority": sev["priority"],
        "deadline_hours": sev["deadline_hours"],
        "breakdown": sev["breakdown"],
        "similar_open": [{"id": s["id"], "similarity": s["similarity"], "status": s["status"]} for s in similar_open],
        "similar_resolved": [{"id": s["id"], "similarity": s["similarity"], "resolved_at": s["resolved_at"]} for s in similar_resolved],
    }


# ================================================================ create
def new_id(code):
    n = db.now()
    while True:
        cid = f"CIV-{n:%y%m}-{code}-{random.randint(1000, 9999)}"
        if not db.query("SELECT 1 FROM complaints WHERE id=?", (cid,), one=True):
            return cid


def create_complaint(user, text, location, duration_hours, when=None, quiet=False):
    a = analyse(text, location, duration_hours, ref=when)
    dept = DEPARTMENTS[a["category"]]
    created = when or db.now()
    cid = new_id(dept["code"])
    deadline = created + timedelta(hours=a["deadline_hours"])

    repeat_flag = None
    if a["similar_resolved"]:
        prev = a["similar_resolved"][0]
        repeat_flag = (f"Same problem re-appeared at this location after {prev['id']} was marked resolved "
                       f"({prev['resolved_at'][:10]}). Possible temporary fix / poor quality work - needs review.")

    db.execute("""INSERT INTO complaints(id,user_id,description,language,location,duration_hours,category,subtype,department,
        officer,confidence,keywords,severity,priority,severity_breakdown,status,created_at,updated_at,window_start,deadline,
        base_hours,similar_count,similar_ids,repeat_flag) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
               (cid, user["id"], text, a["language"], a["location"], a["duration_hours"], a["category"], a["subtype"],
                a["department"], a["officer"], a["confidence"], json.dumps(a["keywords"]), a["severity"], a["priority"],
                json.dumps(a["breakdown"]), "Assigned", db.ts(created), db.ts(created), db.ts(created), db.ts(deadline),
                a["deadline_hours"], len(a["similar_open"]), json.dumps([s["id"] for s in a["similar_open"]]), repeat_flag))

    t = db.ts(created)
    db.log(cid, "Citizen", "Complaint registered via AI chatbot", "Submitted", f"Language: {a['language_name']}", when=t)
    db.log(cid, "AI Engine", f"Classified as {a['category']} / {a['subtype']} ({a['confidence']}% confidence). "
                             f"Severity {a['severity']}/100 -> {a['priority']}", None, None, when=t)
    db.log(cid, "AI Engine", f"Auto-assigned to {a['department']}", "Assigned",
           f"Officer: {a['officer']}. Deadline: {a['deadline_hours']} h", when=t)
    if a["similar_open"]:
        db.log(cid, "AI Engine", f"Linked with {len(a['similar_open'])} similar open complaint(s) in same area - priority boosted",
               None, ", ".join(s["id"] for s in a["similar_open"]), when=t)
    if repeat_flag:
        db.log(cid, "AI Engine", "REPEAT ISSUE flagged for strict administrative review", None, repeat_flag, when=t)
        db.notify("admin", cid, "Repeat issue detected", repeat_flag, when=t if quiet else None)

    ch = ("app",) if quiet else ("app", "sms", "email")
    db.notify("citizen", cid, "Complaint registered",
              f"Your complaint {cid} is registered and sent to {a['department']}. Expected resolution within {a['deadline_hours']} hours.",
              user_id=user["id"], channels=ch, when=t if quiet else None)
    db.notify(a["category"], cid, f"New {a['priority']} complaint",
              f"{cid}: {a['subtype']} at {a['location']}. Resolve within {a['deadline_hours']} h.", when=t if quiet else None)
    return cid, a


# ================================================================ escalation engine
def _staff_note(c, title, msg, when):
    db.notify(c["category"], c["id"], title, msg, when=when)


def run_escalation():
    """Called every few seconds by a background thread (and after Time-Machine jumps).
    Walks each open complaint through: 3 reminders -> 1 extension -> L1 main office -> L2 citizen confirmation -> L3 CM helpdesk."""
    now = db.now()
    events = 0
    rows = db.query("SELECT * FROM complaints WHERE status IN (%s) AND escalation_level < 3" % ",".join("?" * len(OPEN_STATUSES)),
                    OPEN_STATUSES)
    for c in rows:
        for _ in range(10):  # several steps may be due after a big time jump
            ws, dl = db.parse(c["window_start"]), db.parse(c["deadline"])
            span = (dl - ws).total_seconds()
            lvl = c["escalation_level"]

            # --- reminders in the first window
            if lvl == 0 and not c["extension_used"] and c["reminders_sent"] < 3:
                frac = [0.5, 0.75, 0.9][c["reminders_sent"]]
                at = ws + timedelta(seconds=span * frac)
                if now >= at and at < dl:
                    n = c["reminders_sent"] + 1
                    t = db.ts(at)
                    db.execute("UPDATE complaints SET reminders_sent=? WHERE id=?", (n, c["id"]))
                    db.log(c["id"], "Timeline Monitor", f"Automated reminder {n}/3 sent to department", None,
                           f"{int(frac * 100)}% of time used", when=t)
                    _staff_note(c, f"Reminder {n}/3", f"{c['id']} ({c['priority']}) is still unresolved. Deadline {c['deadline'][:16]}.", t)
                    c["reminders_sent"] = n
                    events += 1
                    continue

            if now < dl:
                break

            t = db.ts(dl)
            half = timedelta(hours=max(2, c["base_hours"] * 0.5))
            if lvl == 0 and not c["extension_used"]:
                new_dl = dl + half
                db.execute("UPDATE complaints SET extension_used=1, window_start=?, deadline=?, updated_at=? WHERE id=?",
                           (t, db.ts(new_dl), t, c["id"]))
                db.log(c["id"], "Timeline Monitor", "Deadline missed - ONE final extension granted", None,
                       f"New deadline {db.ts(new_dl)[:16]}", when=t)
                _staff_note(c, "Deadline missed - final chance", f"{c['id']}: extended once till {db.ts(new_dl)[:16]}. Next step is escalation.", t)
                c.update(extension_used=1, window_start=t, deadline=db.ts(new_dl))
            elif lvl == 0:
                new_dl = dl + half
                db.execute("UPDATE complaints SET escalation_level=1, status='Escalated', window_start=?, deadline=?, updated_at=? WHERE id=?",
                           (t, db.ts(new_dl), t, c["id"]))
                db.log(c["id"], "Escalation Engine", "LEVEL 1: Escalated to Main Administrative Office", "Escalated",
                       f"Forwarded with full timeline, {c['reminders_sent']} reminder logs and officer details", when=t)
                db.notify("admin", c["id"], "Level 1 escalation", f"{c['id']} ({c['department']}) not resolved after reminders + extension.", when=t)
                db.notify("citizen", c["id"], "Complaint escalated",
                          f"Your complaint {c['id']} was not resolved in time and has been escalated to the Main Office.",
                          user_id=c["user_id"], when=t)
                c.update(escalation_level=1, status="Escalated", window_start=t, deadline=db.ts(new_dl))
            elif lvl == 1:
                new_dl = dl + timedelta(hours=max(4, c["base_hours"] * 0.25))
                db.execute("UPDATE complaints SET escalation_level=2, citizen_confirm='pending', window_start=?, deadline=?, updated_at=? WHERE id=?",
                           (t, db.ts(new_dl), t, c["id"]))
                db.log(c["id"], "Escalation Engine", "LEVEL 2: Asking citizen to confirm the issue is still unresolved", "Escalated", None, when=t)
                db.notify("citizen", c["id"], "Please confirm",
                          f"Is your issue {c['id']} still unresolved? Open tracking page and answer - if yes, it goes to the CM Helpdesk.",
                          user_id=c["user_id"], when=t)
                c.update(escalation_level=2, citizen_confirm="pending", window_start=t, deadline=db.ts(new_dl))
            else:  # lvl == 2 and citizen did not answer in time
                escalate_to_cm(c, t, "Citizen confirmation window expired without resolution")
                break
            events += 1
    return events


def escalate_to_cm(c, t, why):
    db.execute("UPDATE complaints SET escalation_level=3, status='Escalated', updated_at=?, "
               "citizen_confirm=CASE WHEN citizen_confirm='pending' THEN 'no reply' ELSE citizen_confirm END WHERE id=?", (t, c["id"]))
    db.log(c["id"], "Escalation Engine", "LEVEL 3: Accountability report sent to CM Helpdesk", "Escalated", why, when=t)
    db.notify("admin", c["id"], "CM Helpdesk escalation", f"{c['id']}: accountability report generated for {c['department']}.", when=t)
    db.notify("citizen", c["id"], "Sent to CM Helpdesk",
              f"Your complaint {c['id']} has been forwarded to the Chief Minister Helpdesk with a full accountability report.",
              user_id=c["user_id"], when=t)


def citizen_confirm(cid, still_unresolved: bool):
    c = db.query("SELECT * FROM complaints WHERE id=?", (cid,), one=True)
    if not c or c["citizen_confirm"] != "pending":
        return False
    t = db.now_s()
    if still_unresolved:
        db.execute("UPDATE complaints SET citizen_confirm='unresolved' WHERE id=?", (cid,))
        db.log(cid, "Citizen", "Confirmed: issue is STILL unresolved", None, None)
        escalate_to_cm(c, t, "Citizen confirmed the issue is still unresolved")
    else:
        db.execute("UPDATE complaints SET citizen_confirm='resolved', status='Resolved', resolved_at=?, updated_at=? WHERE id=?", (t, t, cid))
        db.log(cid, "Citizen", "Confirmed: issue has been resolved", "Resolved", None)
    return True


# ================================================================ officer actions
def update_status(cid, status, remarks, contractor, actor):
    c = db.query("SELECT * FROM complaints WHERE id=?", (cid,), one=True)
    if not c:
        return False
    t = db.now_s()
    resolved_at = t if status == "Resolved" else c["resolved_at"]
    db.execute("UPDATE complaints SET status=?, remarks=COALESCE(NULLIF(?,''),remarks), contractor=COALESCE(NULLIF(?,''),contractor), "
               "updated_at=?, resolved_at=? WHERE id=?", (status, remarks, contractor, t, resolved_at, cid))
    db.log(cid, actor, f"Status changed to {status}", status, remarks or None)
    msg = f"Your complaint {cid} is now '{status}'." + (f" Remark: {remarks}" if remarks else "")
    if status == "Resolved":
        msg += " Please give feedback - was it really fixed?"
    db.notify("citizen", cid, f"Status: {status}", msg, user_id=c["user_id"], channels=("app", "sms", "email"))
    return True


# ================================================================ feedback
def submit_feedback(cid, rating, text):
    c = db.query("SELECT * FROM complaints WHERE id=?", (cid,), one=True)
    if not c or c["status"] != "Resolved":
        return None
    ev = evaluate_feedback(rating, text)
    t = db.now_s()
    db.execute("UPDATE complaints SET rating=?, feedback=? WHERE id=?", (rating, text, cid))
    db.log(cid, "Citizen", f"Feedback: {rating}/5", None, text or None)
    if ev["genuinely_resolved"]:
        db.execute("UPDATE complaints SET status='Closed', updated_at=? WHERE id=?", (t, cid))
        db.log(cid, "AI Engine", "Feedback verified - complaint closed", "Closed", f"Sentiment {ev['sentiment']:+.2f}")
    else:
        new_dl = db.now() + timedelta(hours=max(2, c["base_hours"] * 0.5))
        pr = {"Low": "Medium", "Medium": "High", "High": "Critical", "Critical": "Critical"}[c["priority"]]
        db.execute("UPDATE complaints SET status='Reopened', reopen_count=reopen_count+1, priority=?, resolved_at=NULL, "
                   "window_start=?, deadline=?, reminders_sent=0, extension_used=0, updated_at=? WHERE id=?",
                   (pr, t, db.ts(new_dl), t, cid))
        db.log(cid, "AI Engine", f"AI REOPENED complaint: {ev['reason']}", "Reopened",
               f"Priority raised to {pr}. Signals: {', '.join(ev['signals']) or 'low rating'}")
        db.notify(c["category"], cid, "Complaint REOPENED", f"{cid} reopened after negative citizen feedback. Priority {pr}.")
        if c["reopen_count"] + 1 >= 2:
            db.notify("admin", cid, "Repeated negligence", f"{cid} reopened {c['reopen_count'] + 1} times - accountability review needed.")
    return ev


# ================================================================ analytics
def dept_performance():
    out = []
    now = db.now()
    for cat, d in DEPARTMENTS.items():
        rows = db.query("SELECT * FROM complaints WHERE category=?", (cat,))
        total = len(rows)
        resolved = [r for r in rows if r["resolved_at"]]
        res_hours = [(db.parse(r["resolved_at"]) - db.parse(r["created_at"])).total_seconds() / 3600 for r in resolved]
        avg_res = round(sum(res_hours) / len(res_hours), 1) if res_hours else None
        escalated = sum(1 for r in rows if r["escalation_level"] > 0)
        reopened = sum(1 for r in rows if r["reopen_count"] > 0)
        ratings = [r["rating"] for r in rows if r["rating"]]
        pending = sum(1 for r in rows if r["status"] in OPEN_STATUSES)
        overdue = sum(1 for r in rows if r["status"] in OPEN_STATUSES and db.parse(r["deadline"]) < now)
        within = sum(1 for r, h in zip(resolved, res_hours) if h <= r["base_hours"] * 1.0)
        if total == 0:
            score = None
        else:
            score = 100.0
            score -= 35 * (escalated / total)
            score -= 25 * (reopened / total)
            score -= 15 * (overdue / total)
            if resolved:
                score -= 15 * (1 - within / len(resolved))
            if ratings:
                score -= 10 * (1 - (sum(ratings) / len(ratings) - 1) / 4)
            score = max(0, round(score))
        grade = None if score is None else ("A" if score >= 85 else "B" if score >= 70 else "C" if score >= 55 else "D" if score >= 40 else "E")
        out.append({"category": cat, "department": d["name"], "officer": d["officer"], "total": total, "pending": pending,
                    "overdue": overdue, "resolved": len(resolved), "avg_resolution_h": avg_res, "escalated": escalated,
                    "reopened": reopened, "avg_rating": round(sum(ratings) / len(ratings), 1) if ratings else None,
                    "score": score, "grade": grade})
    return out


def hotspots():
    """Predictive governance: same problem repeating at same place -> warn before it becomes critical."""
    cutoff = db.ts(db.now() - timedelta(days=14))
    rows = db.query("SELECT location, category, COUNT(*) n, MAX(severity) s FROM complaints WHERE created_at >= ? AND location IS NOT NULL "
                    "GROUP BY lower(location), category HAVING n >= 3 ORDER BY n DESC", (cutoff,))
    tips = {"Water Supply": "possible pipeline failure - schedule inspection of the main line",
            "Electricity": "transformer/feeder may be overloaded - preventive maintenance advised",
            "Roads & Infrastructure": "road quality issue - audit the contractor's work",
            "Sanitation & Garbage": "collection route is being skipped - review vehicle GPS logs",
            "Drainage & Sewage": "sewer line likely damaged - high flood/disease risk in rain",
            "Public Safety": "increase patrolling in this area",
            "Health & Hygiene": "possible outbreak - send health team and fogging"}
    return [{"location": r["location"], "category": r["category"], "count": r["n"], "max_severity": r["s"],
             "prediction": tips[r["category"]]} for r in rows]


def analytics():
    rows = db.query("SELECT * FROM complaints")
    total = len(rows)
    by_status = Counter(r["status"] for r in rows)
    by_cat = Counter(r["category"] for r in rows)
    by_pri = Counter(r["priority"] for r in rows)
    by_lang = Counter(r["language"] for r in rows)
    ratings = [r["rating"] for r in rows if r["rating"]]
    satisfied = sum(1 for r in ratings if r >= 3)
    res_h = [(db.parse(r["resolved_at"]) - db.parse(r["created_at"])).total_seconds() / 3600 for r in rows if r["resolved_at"]]
    days = defaultdict(int)
    for i in range(13, -1, -1):
        days[(db.now() - timedelta(days=i)).strftime("%d %b")] = 0
    for r in rows:
        k = db.parse(r["created_at"]).strftime("%d %b")
        if k in days:
            days[k] += 1
    return {
        "total": total,
        "open": sum(by_status[s] for s in OPEN_STATUSES),
        "resolved": by_status["Resolved"] + by_status["Closed"],
        "escalated": sum(1 for r in rows if r["escalation_level"] > 0),
        "cm_level": sum(1 for r in rows if r["escalation_level"] == 3),
        "reopened": sum(1 for r in rows if r["reopen_count"] > 0),
        "avg_resolution_h": round(sum(res_h) / len(res_h), 1) if res_h else 0,
        "satisfaction": round(100 * satisfied / len(ratings)) if ratings else 0,
        "by_status": dict(by_status), "by_category": dict(by_cat), "by_priority": dict(by_pri),
        "by_language": {("Hindi" if k == "hi" else "Hinglish" if k == "hinglish" else "English"): v for k, v in by_lang.items()},
        "trend": dict(days),
        "departments": dept_performance(),
        "hotspots": hotspots(),
        "model": {"test_accuracy": CLASSIFIER.test_accuracy, "ml_only_accuracy": CLASSIFIER.ml_only_accuracy,
                  "per_language": CLASSIFIER.per_lang_accuracy, "train_size": CLASSIFIER.train_size, "test_size": CLASSIFIER.test_size,
                  "categories": len(DEPARTMENTS)},
        "clock": db.now_s(),
        "offset_hours": db.get_offset_hours(),
    }

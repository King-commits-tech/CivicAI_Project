"""
CivicAI - AI-Driven Complaint Management System
SAGE University, Indore | B.Tech (Advance CSE) Micro Project | Gulshan Jhala

Run:  python app.py      then open  http://127.0.0.1:5000
"""

import os
import sys
import threading
import time
import webbrowser
from functools import wraps

from flask import Flask, jsonify, redirect, render_template, request, session, url_for, flash
from werkzeug.security import check_password_hash, generate_password_hash

from ai.training_data import DEPARTMENTS
from core import db
from core import chatbot
from core.seed import seed
from core.services import (analytics, citizen_confirm, run_escalation, submit_feedback, update_status, OPEN_STATUSES)

# Windows consoles can't always print Hindi text - never crash because of a print()
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "civicai-sage-university-demo-key")
app.json.ensure_ascii = False
app.json.sort_keys = False  # keep chart order (e.g. dates) as produced


# ------------------------------------------------------------------ auth helpers
def current_user():
    uid = session.get("user_id")
    return db.query("SELECT * FROM users WHERE id=?", (uid,), one=True) if uid else None


def login_required(role=None):
    def deco(f):
        @wraps(f)
        def wrapper(*a, **kw):
            u = current_user()
            if not u:
                if request.path.startswith("/api/"):
                    return jsonify({"error": "login required"}), 401
                return redirect(url_for("login", next=request.path))
            if role and u["role"] not in (role if isinstance(role, tuple) else (role,)):
                if request.path.startswith("/api/"):
                    return jsonify({"error": "not allowed"}), 403
                return redirect(url_for("home"))
            return f(*a, **kw)
        return wrapper
    return deco


@app.context_processor
def inject():
    return {"me": current_user(), "departments": DEPARTMENTS}


# ------------------------------------------------------------------ pages
@app.route("/")
def home():
    stats = db.query("SELECT COUNT(*) n, SUM(CASE WHEN status IN ('Resolved','Closed') THEN 1 ELSE 0 END) r FROM complaints", one=True)
    return render_template("home.html", stats=stats)


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = db.query("SELECT * FROM users WHERE lower(email)=lower(?)", (request.form["email"].strip(),), one=True)
        if u and check_password_hash(u["password_hash"], request.form["password"]):
            session.clear()
            session["user_id"] = u["id"]
            nxt = request.args.get("next")
            if u["role"] in ("officer", "admin"):
                return redirect(url_for("admin"))
            return redirect(nxt or url_for("chat"))
        flash("Wrong e-mail or password.", "error")
    return render_template("login.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        f = request.form
        if len(f["password"]) < 6:
            flash("Password must be at least 6 characters.", "error")
        elif not f["mobile"].strip().isdigit() or len(f["mobile"].strip()) != 10:
            flash("Please enter a valid 10-digit mobile number.", "error")
        elif db.query("SELECT 1 FROM users WHERE lower(email)=lower(?)", (f["email"].strip(),), one=True):
            flash("This e-mail is already registered. Please login.", "error")
        else:
            uid = db.execute("INSERT INTO users(name,email,mobile,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                             (f["name"].strip(), f["email"].strip(), f["mobile"].strip(),
                              generate_password_hash(f["password"]), "citizen", db.now_s()))
            session.clear()
            session["user_id"] = uid
            return redirect(url_for("chat"))
    return render_template("register.html")


@app.route("/forgot", methods=["GET", "POST"])
def forgot():
    if request.method == "POST":
        f = request.form
        u = db.query("SELECT * FROM users WHERE lower(email)=lower(?) AND mobile=?", (f["email"].strip(), f["mobile"].strip()), one=True)
        if not u:
            flash("No account found with this e-mail and mobile number.", "error")
        elif len(f["password"]) < 6:
            flash("New password must be at least 6 characters.", "error")
        else:
            db.execute("UPDATE users SET password_hash=? WHERE id=?", (generate_password_hash(f["password"]), u["id"]))
            flash("Password changed. Please login.", "ok")
            return redirect(url_for("login"))
    return render_template("forgot.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


@app.route("/chat")
@login_required("citizen")
def chat():
    session["draft"] = {"stage": "idle"}
    return render_template("chat.html")


@app.route("/my")
@login_required("citizen")
def my_complaints():
    rows = db.query("SELECT * FROM complaints WHERE user_id=? ORDER BY created_at DESC", (current_user()["id"],))
    return render_template("my.html", rows=rows)


@app.route("/track")
@app.route("/track/<cid>")
def track(cid=None):
    cid = (cid or request.args.get("id") or "").strip().upper()
    return render_template("track.html", cid=cid)


@app.route("/admin")
@login_required(("officer", "admin"))
def admin():
    return render_template("admin.html")


@app.route("/report/<cid>")
@login_required(("officer", "admin"))
def report(cid):
    c = db.complaint_dict(db.query("SELECT * FROM complaints WHERE id=?", (cid,), one=True))
    if not c:
        return "Not found", 404
    hist = db.query("SELECT * FROM history WHERE complaint_id=? ORDER BY time, id", (cid,))
    citizen = db.query("SELECT name, mobile, email FROM users WHERE id=?", (c["user_id"],), one=True)
    delay = (db.now() - db.parse(c["created_at"]))
    return render_template("report.html", c=c, hist=hist, citizen=citizen, now=db.now_s(),
                           delay_h=round(delay.total_seconds() / 3600, 1))


# ------------------------------------------------------------------ chatbot API
@app.post("/api/chat")
@login_required("citizen")
def api_chat():
    return jsonify(chatbot.handle(session, request.json.get("message", "")))


@app.post("/api/submit")
@login_required("citizen")
def api_submit():
    r = chatbot.submit(session, current_user())
    if not r:
        return jsonify({"error": "nothing to submit"}), 400
    return jsonify(r)


# ------------------------------------------------------------------ tracking API
@app.get("/api/track/<cid>")
def api_track(cid):
    c = db.complaint_dict(db.query("SELECT * FROM complaints WHERE id=?", (cid.upper(),), one=True))
    if not c:
        return jsonify({"error": "Complaint not found"}), 404
    u = current_user()
    owner = bool(u and u["id"] == c["user_id"])
    staff = bool(u and u["role"] in ("officer", "admin"))
    hist = db.query("SELECT time, actor, action, status, note FROM history WHERE complaint_id=? ORDER BY time, id", (c["id"],))
    if not (owner or staff):  # public view hides personal info
        c.pop("user_id", None)
    c["owner"] = owner
    c["now"] = db.now_s()
    return jsonify({"complaint": c, "history": hist})


@app.post("/api/feedback/<cid>")
@login_required("citizen")
def api_feedback(cid):
    c = db.query("SELECT user_id FROM complaints WHERE id=?", (cid,), one=True)
    if not c or c["user_id"] != current_user()["id"]:
        return jsonify({"error": "not allowed"}), 403
    ev = submit_feedback(cid, int(request.json.get("rating", 3)), request.json.get("text", ""))
    if ev is None:
        return jsonify({"error": "Feedback can be given only after the complaint is resolved"}), 400
    return jsonify(ev)


@app.post("/api/confirm/<cid>")
@login_required("citizen")
def api_confirm(cid):
    c = db.query("SELECT user_id FROM complaints WHERE id=?", (cid,), one=True)
    if not c or c["user_id"] != current_user()["id"]:
        return jsonify({"error": "not allowed"}), 403
    return jsonify({"ok": citizen_confirm(cid, bool(request.json.get("still_unresolved")))})


# ------------------------------------------------------------------ notifications
@app.get("/api/notifications")
@login_required()
def api_notifications():
    u = current_user()
    if u["role"] == "citizen":
        rows = db.query("SELECT * FROM notifications WHERE user_id=? AND channel='app' ORDER BY time DESC, id DESC LIMIT 30", (u["id"],))
    elif u["role"] == "admin":
        rows = db.query("SELECT * FROM notifications WHERE target='admin' ORDER BY time DESC, id DESC LIMIT 40")
    else:
        rows = db.query("SELECT * FROM notifications WHERE target=? ORDER BY time DESC, id DESC LIMIT 40", (u["department"],))
    unread = sum(1 for r in rows if not r["is_read"])
    return jsonify({"items": rows, "unread": unread})


@app.post("/api/notifications/read")
@login_required()
def api_notifications_read():
    u = current_user()
    if u["role"] == "citizen":
        db.execute("UPDATE notifications SET is_read=1 WHERE user_id=?", (u["id"],))
    elif u["role"] == "admin":
        db.execute("UPDATE notifications SET is_read=1 WHERE target='admin'")
    else:
        db.execute("UPDATE notifications SET is_read=1 WHERE target=?", (u["department"],))
    return jsonify({"ok": True})


# ------------------------------------------------------------------ admin API
@app.get("/api/admin/complaints")
@login_required(("officer", "admin"))
def api_admin_complaints():
    u = current_user()
    sql, params = "SELECT * FROM complaints", []
    where = []
    if u["role"] == "officer":
        where.append("category=?")
        params.append(u["department"])
    f = request.args
    if f.get("status") == "open":
        where.append("status IN (%s)" % ",".join("?" * len(OPEN_STATUSES)))
        params += OPEN_STATUSES
    elif f.get("status") == "escalated":
        where.append("escalation_level > 0")
    elif f.get("status"):
        where.append("status=?")
        params.append(f["status"])
    if f.get("category"):
        where.append("category=?")
        params.append(f["category"])
    if f.get("q"):
        where.append("(id LIKE ? OR description LIKE ? OR location LIKE ?)")
        params += ["%" + f["q"] + "%"] * 3
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY CASE priority WHEN 'Critical' THEN 0 WHEN 'High' THEN 1 WHEN 'Medium' THEN 2 ELSE 3 END, created_at DESC"
    rows = [db.complaint_dict(r) for r in db.query(sql, params)]
    return jsonify({"items": rows, "now": db.now_s()})


@app.post("/api/admin/update/<cid>")
@login_required(("officer", "admin"))
def api_admin_update(cid):
    u = current_user()
    c = db.query("SELECT category FROM complaints WHERE id=?", (cid,), one=True)
    if not c:
        return jsonify({"error": "not found"}), 404
    if u["role"] == "officer" and c["category"] != u["department"]:
        return jsonify({"error": "This complaint belongs to another department"}), 403
    d = request.json
    if d.get("status") not in ("Under Review", "Action Initiated", "Resolved", "Rejected"):
        return jsonify({"error": "invalid status"}), 400
    update_status(cid, d["status"], d.get("remarks", "").strip(), d.get("contractor", "").strip(), u["name"])
    return jsonify({"ok": True})


@app.get("/api/admin/analytics")
@login_required(("officer", "admin"))
def api_analytics():
    return jsonify(analytics())


@app.post("/api/admin/timewarp")
@login_required(("officer", "admin"))
def api_timewarp():
    hours = float(request.json.get("hours", 6))
    if request.json.get("reset"):
        db.execute("DELETE FROM settings WHERE key='time_offset'")
    else:
        db.add_offset_hours(max(0.0, min(hours, 24 * 30)))
    events = run_escalation()
    return jsonify({"clock": db.now_s(), "offset_hours": db.get_offset_hours(), "events": events})


# ------------------------------------------------------------------ background timeline monitor
def monitor_loop():
    while True:
        try:
            run_escalation()
        except Exception as e:  # never let the monitor die
            print("monitor error:", e)
        time.sleep(15)


if __name__ == "__main__":
    seed()
    threading.Thread(target=monitor_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 5000))
    url = f"http://127.0.0.1:{port}"
    print("\n" + "=" * 60)
    print("  CivicAI is running!  Open:  " + url)
    print("  Citizen login : citizen@demo.com   / demo123")
    print("  Admin login   : admin@civicai.gov  / admin123")
    print("  Officer login : water@civicai.gov  / officer123")
    print("  Press CTRL + C to stop")
    print("=" * 60 + "\n")
    if not os.environ.get("NO_BROWSER"):
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)

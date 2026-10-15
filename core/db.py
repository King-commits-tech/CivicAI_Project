"""
Database layer (SQLite - built into Python, so no installation is needed).
The same tables can be moved to MySQL later without changing the rest of the code much.
"""

import json
import os
import sqlite3
import threading
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "civicai.db")
_lock = threading.RLock()

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    mobile TEXT,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'citizen',      -- citizen / officer / admin
    department TEXT,                            -- category handled (officers only)
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS complaints (
    id TEXT PRIMARY KEY,
    user_id INTEGER,
    description TEXT NOT NULL,
    language TEXT,
    location TEXT,
    duration_hours INTEGER,
    category TEXT,
    subtype TEXT,
    department TEXT,
    officer TEXT,
    confidence REAL,
    keywords TEXT,
    severity INTEGER,
    priority TEXT,
    severity_breakdown TEXT,
    status TEXT,
    created_at TEXT,
    updated_at TEXT,
    window_start TEXT,
    deadline TEXT,
    base_hours INTEGER,
    reminders_sent INTEGER DEFAULT 0,
    extension_used INTEGER DEFAULT 0,
    escalation_level INTEGER DEFAULT 0,        -- 0 none, 1 main office, 2 citizen confirmation, 3 CM helpdesk
    citizen_confirm TEXT,                       -- NULL / pending / unresolved / resolved
    similar_count INTEGER DEFAULT 0,
    similar_ids TEXT,
    repeat_flag TEXT,
    contractor TEXT,
    remarks TEXT,
    resolved_at TEXT,
    rating INTEGER,
    feedback TEXT,
    reopen_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS history (           -- audit trail: every action with timestamp
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    complaint_id TEXT,
    time TEXT,
    actor TEXT,
    action TEXT,
    status TEXT,
    note TEXT
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,                            -- citizen receiving it (NULL for staff notices)
    target TEXT,                                -- 'citizen' / department name / 'admin'
    complaint_id TEXT,
    channel TEXT,                               -- app / sms / email
    title TEXT,
    message TEXT,
    time TEXT,
    is_read INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT);
"""


def connect():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False, timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


_conn = None


def get_conn():
    global _conn
    if _conn is None:
        _conn = connect()
        _conn.executescript(SCHEMA)
        _conn.commit()
    return _conn


def query(sql, params=(), one=False):
    with _lock:
        cur = get_conn().execute(sql, params)
        rows = [dict(r) for r in cur.fetchall()]
    return (rows[0] if rows else None) if one else rows


def execute(sql, params=()):
    with _lock:
        conn = get_conn()
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


# ----------------------------------------------------------- simulated clock
# The "Time Machine" lets a teacher/examiner jump forward in time during the demo
# to watch reminders and escalations happen without waiting for days.
def get_offset_hours() -> float:
    row = query("SELECT value FROM settings WHERE key='time_offset'", one=True)
    return float(row["value"]) if row else 0.0


def add_offset_hours(h: float):
    execute("INSERT OR REPLACE INTO settings(key,value) VALUES('time_offset', ?)", (str(get_offset_hours() + h),))


def now() -> datetime:
    return datetime.now().replace(microsecond=0) + timedelta(hours=get_offset_hours())


def ts(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def parse(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")


def now_s() -> str:
    return ts(now())


# ----------------------------------------------------------- helpers
def log(complaint_id, actor, action, status=None, note=None, when=None):
    execute("INSERT INTO history(complaint_id,time,actor,action,status,note) VALUES(?,?,?,?,?,?)",
            (complaint_id, when or now_s(), actor, action, status, note))


def notify(target, complaint_id, title, message, user_id=None, channels=("app",), when=None):
    """Store notification. SMS / e-mail are simulated (printed to console) - plug in Twilio / SMTP later."""
    for ch in channels:
        execute("INSERT INTO notifications(user_id,target,complaint_id,channel,title,message,time) VALUES(?,?,?,?,?,?,?)",
                (user_id, target, complaint_id, ch, title, message, when or now_s()))
        if ch in ("sms", "email") and not when:
            try:
                print(f"   [{ch.upper()} -> {target}] {title}: {message}")
            except Exception:
                pass


def complaint_dict(row):
    if not row:
        return None
    d = dict(row)
    for k in ("keywords", "severity_breakdown", "similar_ids"):
        try:
            d[k] = json.loads(d[k]) if d.get(k) else []
        except Exception:
            d[k] = []
    return d

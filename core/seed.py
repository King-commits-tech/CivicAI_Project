"""
Creates demo accounts and ~40 realistic sample complaints on the first run,
so the dashboard, analytics, hotspots and escalations have something to show.

FIX: pehle yahan 'location_type' aur 'coordinates' naam ke columns me likha ja raha tha,
jo database me hain hi nahi (schema me lat, lng, loc_source, gps_accuracy, landmark hain).
Isse pehli run par app crash ho jaati thi. Ab coordinates ko lat/lng me todkar sahi columns me save kiya jaata hai.
"""

from datetime import timedelta
from werkzeug.security import generate_password_hash

from ai.training_data import DEPARTMENTS
from core import db
from core.services import create_complaint

DEMO_ACCOUNTS = [
    ("Gulshan Jhala", "citizen@demo.com", "9876543210", "demo123", "citizen", None),
    ("Central Admin (Main Office)", "admin@civicai.gov", "9000000000", "admin123", "admin", None),
]
OFFICER_EMAILS = {
    "Water Supply": "water@civicai.gov", "Electricity": "electricity@civicai.gov", "Roads & Infrastructure": "roads@civicai.gov",
    "Sanitation & Garbage": "sanitation@civicai.gov", "Drainage & Sewage": "drainage@civicai.gov",
    "Public Safety": "safety@civicai.gov", "Health & Hygiene": "health@civicai.gov",
}
OTHER_CITIZENS = [
    ("Priya Sharma", "priya@demo.com"), ("Rahul Verma", "rahul@demo.com"), ("Anita Devi", "anita@demo.com"),
    ("Mohd. Irfan", "irfan@demo.com"), ("Suresh Patel", "suresh@demo.com")
]

# (text, location, "lat, lng", duration_h, created_hours_ago, outcome, resolve_after_h, rating, feedback)
SAMPLES = [
    ("3 din se pani nahi aa raha, bahut pareshani hai", "Vijay Nagar", "22.7533, 75.8937", 72, 300, "closed", 30, 4, "pani aa gaya, shukriya"),
    ("water pipeline leaking near the main road, water wasting", "Vijay Nagar", "22.7540, 75.8945", 24, 200, "closed", 20, 5, "fixed quickly thank you"),
    ("low water pressure in the whole colony", "Vijay Nagar", "22.7552, 75.8912", 48, 90, "open", 0, 0, ""),
    ("Vijay Nagar me nal ka pani ganda aa raha hai, bachche bimar ho rahe", "Vijay Nagar", "22.7512, 75.8960", 48, 40, "open", 0, 0, ""),
    ("पानी की पाइप फट गई है सड़क पर पानी बह रहा है", "Vijay Nagar", "22.7565, 75.8920", 12, 10, "open", 0, 0, ""),
    ("transformer is sparking near the school, very dangerous", "Palasia", "22.7244, 75.8839", 6, 60, "closed", 3, 5, "very fast action, great"),
    ("kal raat se light nahi hai puri colony me andhera", "Khajrana", "22.7305, 75.8988", 12, 30, "open", 0, 0, ""),
    ("street light not working on our lane for a week", "Sudama Nagar", "22.6980, 75.8340", 168, 150, "open", 0, 0, ""),
    ("बिजली का बिल गलत और बहुत ज्यादा आया है", "Rajendra Nagar", "22.6840, 75.8290", 240, 120, "closed", 70, 3, "ठीक हो गया"),
    ("voltage fluctuation damaged our fridge and tv", "Nipania", "22.7710, 75.9140", 24, 20, "progress", 0, 0, ""),
    ("big potholes on the main road causing accidents daily", "AB Road", "22.7420, 75.8890", 360, 400, "closed", 110, 2, "still potholes, only gravel thrown"),
    ("main road par bade gadde hai bike fisal rahi hai", "AB Road", "22.7435, 75.8898", 72, 50, "open", 0, 0, ""),
    ("road dug up for pipeline and left incomplete for months", "Scheme 54", "22.7580, 75.8970", 1440, 230, "open", 0, 0, ""),
    ("traffic signal not working at the square", "Bengali Square", "22.7280, 75.9090", 24, 26, "progress", 0, 0, ""),
    ("footpath toota hua hai log gir rahe hai", "MG Road", "22.7190, 75.8580", 240, 100, "closed", 90, 4, "theek ho gaya accha kaam"),
    ("garbage has not been collected for a week, smell is terrible", "Bhawarkua", "22.6990, 75.8650", 168, 180, "closed", 40, 4, "clean now thanks"),
    ("ek hafte se kachra nahi uthaya gali me gandagi", "Bhawarkua", "22.6985, 75.8632", 168, 70, "open", 0, 0, ""),
    ("dustbin overflowing near the vegetable market", "Bhawarkua", "22.7002, 75.8675", 48, 30, "open", 0, 0, ""),
    ("dead animal lying on the road for two days", "Musakhedi", "22.7120, 75.9010", 48, 45, "closed", 8, 5, "removed same day"),
    ("public toilet is very dirty and not cleaned", "Rajwada", "22.7195, 75.8537", 72, 20, "open", 0, 0, ""),
    ("सीवर line jaam hai aur sadak par ganda pani bah raha hai", "Malharganj", "22.7270, 75.8420", 72, 160, "open", 0, 0, ""),
    ("open manhole near the school gate, children at risk", "Tilak Nagar", "22.7290, 75.8820", 24, 15, "open", 0, 0, ""),
    ("barish ke baad colony me pani bhar gaya, gharon me ghus raha", "Banganga", "22.7680, 75.8450", 24, 110, "closed", 28, 1, "unresolved"),
    ("gutter chok hai ganda pani fail raha hai", "Banganga", "22.7692, 75.8465", 96, 60, "open", 0, 0, ""),
    ("nali ka pani gharon me ghus raha hai", "Banganga", "22.7671, 75.8432", 48, 25, "open", 0, 0, ""),
    ("stray dogs are attacking children in the street", "Saket Nagar", "22.7380, 75.9020", 72, 80, "closed", 36, 4, "dogs caught by team"),
    ("school ke paas daru bik rahi hai", "Annapurna", "22.6990, 75.8410", 240, 35, "progress", 0, 0, ""),
    ("loud music at night till 2 am disturbing everyone", "Geeta Bhawan", "22.7190, 75.8810", 48, 12, "open", 0, 0, ""),
    ("purani building girne wali hai, log andar rehte hai", "Chhoti Gwaltoli", "22.7130, 75.8690", 720, 18, "open", 0, 0, ""),
    ("mosquito breeding and dengue cases in the area, no fogging", "Pipliyahana", "22.7100, 75.9080", 168, 140, "closed", 20, 3, "fogging done"),
    ("colony me fogging nahi hui machhar bahut hai", "Pipliyahana", "22.7112, 75.9095", 168, 55, "open", 0, 0, ""),
    ("ilake me machhar aur dengue ke mamle badh rahe hain", "Pipliyahana", "22.7090, 75.9062", 96, 22, "open", 0, 0, ""),
    ("government hospital has no doctor available at night", "Rau", "22.6390, 75.8050", 72, 44, "progress", 0, 0, ""),
    ("medicines not available at the health centre", "Mhow", "22.5540, 75.7640", 168, 260, "closed", 50, 5, "available now"),
    ("tanker aaj nahi aaya, peene ka pani nahi hai", "Silicon City", "22.6210, 75.8020", 10, 8, "open", 0, 0, ""),
    ("electric pole is bent and may fall on houses", "Navlakha", "22.7010, 75.8740", 48, 5, "open", 0, 0, ""),
    ("kachra jalaya ja raha hai dhuan ho raha hai", "Super Corridor", "22.7950, 75.8120", 24, 4, "open", 0, 0, ""),
    ("road par ped gira hua hai rasta band hai", "Khandwa Road", "22.6890, 75.8790", 5, 3, "open", 0, 0, ""),
]


def _split_coords(text):
    """'22.7533, 75.8937' -> (22.7533, 75.8937)"""
    lat, lng = [float(x) for x in text.split(",")]
    return lat, lng


def seed():
    if db.query("SELECT 1 FROM users LIMIT 1", one=True):
        return
    print(" * First run: creating demo accounts and sample complaints...")
    now = db.now()

    for name, email, mobile, pw, role, dept in DEMO_ACCOUNTS:
        db.execute("INSERT INTO users(name,email,mobile,password_hash,role,department,created_at) VALUES(?,?,?,?,?,?,?)",
                   (name, email, mobile, generate_password_hash(pw), role, dept, db.ts(now)))

    for cat, email in OFFICER_EMAILS.items():
        db.execute("INSERT INTO users(name,email,mobile,password_hash,role,department,created_at) VALUES(?,?,?,?,?,?,?)",
                   (DEPARTMENTS[cat]["officer"], email, "9000000001", generate_password_hash("officer123"), "officer", cat, db.ts(now)))

    for name, email in OTHER_CITIZENS:
        # hash() har run me alag aata hai, isliye mobile number ke liye email ke characters se fixed number banate hain
        digits = str(sum(ord(ch) * (i + 1) for i, ch in enumerate(email)) % 100000).zfill(5)
        db.execute("INSERT INTO users(name,email,mobile,password_hash,role,created_at) VALUES(?,?,?,?,?,?)",
                   (name, email, "98000" + digits, generate_password_hash("demo123"), "citizen", db.ts(now)))

    users = db.query("SELECT * FROM users WHERE role='citizen'")

    for i, (text, loc, coords_val, dur, ago, outcome, res_after, rating, fb) in enumerate(SAMPLES):
        user = users[i % len(users)]
        created = now - timedelta(hours=ago)

        cid, a = create_complaint(user, text, loc, dur, when=created, quiet=True)

        # Map ke liye GPS location: sahi columns (lat, lng, loc_source) me save
        lat, lng = _split_coords(coords_val)
        db.execute("UPDATE complaints SET lat=?, lng=?, loc_source=? WHERE id=?",
                   (lat, lng, "gps" if i % 2 == 0 else "dropdown", cid))

        if outcome == "closed":
            r_at = created + timedelta(hours=res_after)
            db.execute("UPDATE complaints SET status='Closed', resolved_at=?, updated_at=?, rating=?, feedback=?, remarks=? WHERE id=?",
                       (db.ts(r_at), db.ts(r_at), rating, fb, "Work completed by field team", cid))
            db.log(cid, a["officer"], "Status changed to Action Initiated", "Action Initiated", "Field team sent",
                   when=db.ts(created + timedelta(hours=res_after * 0.4)))
            db.log(cid, a["officer"], "Status changed to Resolved", "Resolved", "Work completed by field team", when=db.ts(r_at))
            db.log(cid, "Citizen", f"Feedback: {rating}/5", None, fb, when=db.ts(r_at + timedelta(hours=2)))

            if rating <= 2:
                db.execute("UPDATE complaints SET status='Reopened', reopen_count=1, resolved_at=NULL, window_start=?, deadline=?, "
                           "reminders_sent=0 WHERE id=?", (db.ts(r_at + timedelta(hours=2)),
                                                            db.ts(r_at + timedelta(hours=2 + a["deadline_hours"] * 0.5)), cid))
                db.log(cid, "AI Engine", "AI REOPENED complaint: Citizen says the issue is not really solved", "Reopened",
                       f"Feedback: {fb}", when=db.ts(r_at + timedelta(hours=2)))
            else:
                db.log(cid, "AI Engine", "Feedback verified - complaint closed", "Closed", None, when=db.ts(r_at + timedelta(hours=2)))
        elif outcome == "progress":
            t_at = created + timedelta(hours=ago * 0.5)
            db.execute("UPDATE complaints SET status='Action Initiated', updated_at=?, remarks=? WHERE id=?",
                       (db.ts(t_at), "Field operator dispatched to the spot", cid))
            db.log(cid, a["officer"], "Status changed to Action Initiated", "Action Initiated",
                   "Field operator dispatched to the spot", when=db.ts(t_at))

    print("=" * 50)
    print(" Demo data ready: %d users, %d complaints" % (
        db.query("SELECT COUNT(*) n FROM users", one=True)["n"],
        db.query("SELECT COUNT(*) n FROM complaints", one=True)["n"]))
    print("=" * 50)
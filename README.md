# 🏛️ CivicAI: AI-Driven Complaint Management System

**B.Tech (Advance CSE) Micro Project, SAGE University, Indore**
Student: **Gulshan Jhala (25ADV8CSE0010)** · Guides: **Dr. Ati Jain, Prof. Vaishali Bajpai**

Citizens type or **speak** their problem in **English, Hindi or Hinglish**.
The AI works out the problem, sends it to the right department, gives the citizen a tracking ID and sets a deadline.
If nobody acts in time, it **escalates the complaint on its own**, up to the CM Helpdesk.

---

## ▶️ How to run (one click)

### Windows
1. Install **Python 3.10 or newer** from https://www.python.org/downloads/
   → during installation **tick ✅ "Add Python to PATH"**.
2. Unzip this folder.
3. **Double-click `RUN_PROJECT.bat`**.
4. The first run installs 2 libraries (about 1 minute, needs internet). After that the browser opens at **http://127.0.0.1:5000**.

### Mac / Linux
```bash
./run.sh
```

### Manual (any OS / VS Code / PyCharm)
```bash
pip install -r requirements.txt
python app.py
```

Press **CTRL + C** in the black window to stop the app.

---

## 🔑 Demo logins (also shown on the login page, click to fill)

| Role | E-mail | Password |
|---|---|---|
| 👤 Citizen | `citizen@demo.com` | `demo123` |
| 🛡️ Admin (Main Office + CM Helpdesk) | `admin@civicai.gov` | `admin123` |
| 🏢 Water officer | `water@civicai.gov` | `officer123` |
| 🏢 Electricity officer | `electricity@civicai.gov` | `officer123` |
| 🏢 Others | `roads@` `sanitation@` `drainage@` `safety@` `health@` civicai.gov | `officer123` |

You can also register a new citizen account.

---

## 🎤 5-minute demo script for your viva / presentation

1. **Home page**: explain the problem (long forms, language barrier, manual routing).
2. **Login as citizen**, then open **New Complaint**.
3. Type or speak (🎤, works in Chrome/Edge): `Transformer is sparking near the school in Palasia since last night!`
   - Watch the **🧠 AI Brain** panel on the right: language, category %, the keywords that decided it, the severity score with 5 factors, the department and the deadline.
   - Press **Submit** to get a unique ID like `CIV-2609-ELE-4821`, plus an SMS/e-mail notification (simulated).
4. Try Hindi: `सड़क पर बड़े गड्ढे हैं राजवाड़ा के पास`. The bot replies in Hindi.
5. Try something with a missing place: `kachra nahi uthaya`. The bot **asks for the location**, just like in your DFD.
6. Open **Track** to see the status stepper, live countdown, escalation ladder and full audit trail.
7. **Logout, then login as the electricity officer**. Open the complaint, set it to **Resolved** and add a remark.
8. **Login as citizen again** and open the complaint. Give **2 stars** with the feedback `abhi bhi chingari nikal rahi hai`.
   → The **AI reopens the complaint** with higher priority (fake-fix detection).
9. **Login as admin** and use the **⏳ Time Machine** (`+6 h`, `+1 day`). You can watch reminders go out, then the extension, then Level 1, Level 2 and Level 3 escalation.
10. Open an escalated complaint and click **📑 Accountability Report** (printable, can be saved as PDF).
11. Show the **Analytics**, **Department Performance** (AI grade A to E), **Predictive Hotspots** and **AI Model** (accuracy) tabs.

To start again with fresh sample data, double-click **`RESET_DEMO_DATA.bat`** (or delete `civicai.db`).

---

## ✨ Features (mapped to the synopsis)

| Synopsis requirement | Where it is in the project |
|---|---|
| User registration, login, password reset | `/register`, `/login`, `/forgot` (passwords stored as secure hashes) |
| Text + voice complaint (multilingual) | Chatbot + 🎤 Web Speech API (English / हिंदी), replies can be read aloud 🔊 |
| AI classification (NLP / ML) | `ai/engine.py`: TF-IDF + Logistic Regression (scikit-learn) + keyword lexicon (hybrid) |
| Sub-type detection | e.g. Water → Leakage / Contamination / Supply interruption / Long-term failure |
| Severity prediction 0 to 100 | keywords + sentiment + repeats in same area + duration + service criticality |
| Unique complaint ID | `CIV-YYMM-DEPT-NNNN` |
| Automatic department routing | 7 departments, configurable in `ai/training_data.py` |
| Status tracking | Submitted → Assigned → Under Review → Action Initiated → Resolved → Closed |
| Deadlines + 3 reminders + extension | `core/services.py → run_escalation()` (runs every 15 s in the background) |
| Multi-level escalation | L1 Main Office → L2 Citizen confirmation → L3 CM Helpdesk report |
| Duplicate / repeat detection | Cosine similarity + same location; "re-appeared after resolved" flag |
| AI feedback verification + reopen | `evaluate_feedback()` reads the rating and text (Hindi/Hinglish too) |
| Admin / department dashboard | `/admin`: filter, update status, remarks, contractor |
| Notifications (App / SMS / e-mail) | 🔔 bell in the app; SMS/e-mail are simulated (printed in the console) |
| Analytics & reports | charts, department performance score, satisfaction rate |
| Predictive governance | hotspot alerts, e.g. "possible pipeline failure in Vijay Nagar" |
| Audit trail | every action is saved with a timestamp (`history` table) |
| Responsive design | works on mobile, tablet and desktop |

---

## 🗂️ Project structure

```
CivicAI/
├── app.py                 ← Flask web server + REST APIs (start here)
├── ai/
│   ├── training_data.py   ← training sentences (EN/HI/Hinglish) + department config
│   └── engine.py          ← all AI: language, classifier, sub-type, location,
│                             duration, sentiment, severity, similarity, feedback
├── core/
│   ├── db.py              ← SQLite database, simulated clock, audit log, notifications
│   ├── services.py        ← complaint creation, escalation engine, analytics
│   ├── chatbot.py         ← conversation flow (asks for missing info)
│   └── seed.py            ← demo accounts + 38 sample complaints
├── templates/             ← HTML pages (Jinja2)
├── static/                ← CSS + JavaScript (chat, voice, dashboard charts)
├── requirements.txt
├── RUN_PROJECT.bat        ← one-click start (Windows)
├── run.sh                 ← one-command start (Mac/Linux)
└── RESET_DEMO_DATA.bat
```

**Tech used:** HTML5, CSS3, JavaScript (frontend) · Python + Flask, REST APIs (backend) · scikit-learn (AI/NLP) · SQLite database · session-based login.

> **Note on the database:** the synopsis mentions MySQL. The project uses **SQLite** so that it runs with one click and needs no database server. The tables are standard SQL, so moving to MySQL later only means changing `core/db.py`.

> **Note on SMS / e-mail:** real SMS needs a paid gateway (e.g. Twilio), so the notifications are simulated. They appear in the 🔔 panel and are printed in the console. Add the gateway in `db.notify()`.

---

## ❓ Common problems

| Problem | Fix |
|---|---|
| `python is not recognized` | Re-install Python and tick **Add Python to PATH** |
| Voice button does nothing | Use **Google Chrome or Microsoft Edge** and allow microphone access |
| Port 5000 is busy | Close the other app, or run `set PORT=5050` then `python app.py` |
| Want fresh data | Run `RESET_DEMO_DATA.bat` |

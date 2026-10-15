"""
CivicAI - The AI Engine
=======================
Everything "intelligent" in the project lives here:

 1. detect_language()      -> English / Hindi / Hinglish
 2. ComplaintClassifier    -> ML model (TF-IDF + Logistic Regression, scikit-learn)
                              predicts the category + shows WHICH words made it decide
 3. detect_subtype()       -> e.g. Water -> Leakage / Supply interruption / Contamination
 4. extract_location()     -> finds "Vijay Nagar", "ward 12", "sector 5", "near bus stand"...
 5. extract_duration()     -> "3 days", "kal se", "2 हफ्ते" -> hours
 6. sentiment_score()      -> how angry / negative the text is
 7. compute_severity()     -> hybrid 0-100 score (5 factors) -> Critical / High / Medium / Low
 8. SimilarityEngine       -> finds duplicate / repeated complaints (cosine similarity)
 9. evaluate_feedback()    -> reads citizen feedback and decides "really solved?" or REOPEN
"""

import re
import random
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline, FeatureUnion
from sklearn.metrics.pairwise import cosine_similarity

from ai.training_data import CATEGORIES, DEPARTMENTS, OPENERS, CLOSERS

DEVANAGARI = re.compile(r"[ऀ-ॿ]")

HINGLISH_WORDS = {
    "hai", "hain", "nahi", "nahin", "raha", "rahi", "rahe", "kar", "karo", "ho", "gaya", "gayi", "se",
    "me", "mein", "ka", "ki", "ke", "ko", "par", "pani", "bijli", "sadak", "kachra", "hamare", "hamari",
    "bahut", "kab", "kyu", "kyon", "aur", "bhi", "abhi", "tak", "din", "kal", "aaj", "raat", "subah",
    "gali", "nali", "theek", "jaldi", "koi", "kuch", "wala", "wali", "mera", "meri", "hamara", "aa", "aaya",
}


# ---------------------------------------------------------------- 1. language
def detect_language(text: str) -> str:
    if DEVANAGARI.search(text):
        return "hi"
    words = re.findall(r"[a-zA-Z]+", text.lower())
    if not words:
        return "en"
    hits = sum(1 for w in words if w in HINGLISH_WORDS)
    return "hinglish" if hits >= 2 or (hits >= 1 and len(words) <= 4) else "en"


LANG_NAMES = {"en": "English", "hi": "Hindi (हिंदी)", "hinglish": "Hinglish"}


# ---------------------------------------------------------------- 2. classifier
def _augment(rows, rng):
    texts, labels = [], []
    for text, cat, lang in rows:
        texts.append(text)
        labels.append(cat)
        for _ in range(3):
            texts.append(rng.choice(OPENERS[lang]) + text + rng.choice(CLOSERS[lang]))
            labels.append(cat)
    return texts, labels


def _make_pipeline():
    # Two views of the text: whole words + character pieces.
    # Character n-grams make the model robust to spelling mistakes ("paani", "pani", "panni")
    # and work for Hindi script without needing a separate tokenizer.
    features = FeatureUnion([
        ("words", TfidfVectorizer(analyzer="word", ngram_range=(1, 2), sublinear_tf=True, token_pattern=r"[^\s,.!?।:;()\"']+")),
        ("chars", TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 5), sublinear_tf=True, min_df=2)),
    ])
    return Pipeline([("features", features), ("clf", LogisticRegression(max_iter=3000, C=8))])


# Strong domain keywords. The final decision is a HYBRID of the ML model and this lexicon:
# the ML model generalises to new sentences, the lexicon makes sure obvious words are never missed.
LEXICON = {
    "Water Supply": ["water", "pani", "paani", "पानी", "tap", "nal", "नल", "pipeline", "पाइपलाइन", "tanker", "टैंकर", "jal", "जल", "borewell", "handpump", "hand pump"],
    "Electricity": ["electric", "electricity", "power", "bijli", "बिजली", "light", "लाइट", "current", "transformer", "ट्रांसफार्मर", "voltage", "वोल्टेज", "wire", "taar", "तार", "pole", "khamba", "खंभा", "meter", "मीटर"],
    "Roads & Infrastructure": ["road", "sadak", "सड़क", "pothole", "gadde", "gadda", "गड्ढे", "गड्ढा", "footpath", "फुटपाथ", "bridge", "pul", "पुल", "signal", "सिग्नल", "divider", "speed breaker", "highway"],
    "Sanitation & Garbage": ["garbage", "kachra", "kachre", "कचरा", "कचरे", "dustbin", "कूड़ेदान", "kooda", "kuda", "कूड़ा", "waste", "sweep", "safai", "सफाई", "toilet", "शौचालय", "dead animal", "gandagi", "गंदगी"],
    "Drainage & Sewage": ["drain", "nali", "naali", "नाली", "sewer", "sewage", "सीवर", "सीवेज", "gutter", "गटर", "manhole", "मैनहोल", "nala", "नाला", "waterlog", "जलभराव", "chamber"],
    "Public Safety": ["dog", "dogs", "kutte", "kutta", "कुत्ते", "cattle", "गाय", "police", "पुलिस", "theft", "chori", "चोरी", "snatch", "liquor", "daru", "शराब", "gambl", "jua", "जुआ", "noise", "loud", "monkey", "bandar", "बंदर", "eve teas", "harass", "collapse", "unsafe", "crime"],
    "Health & Hygiene": ["mosquito", "machhar", "मच्छर", "dengue", "डेंगू", "malaria", "मलेरिया", "hospital", "अस्पताल", "doctor", "डॉक्टर", "medicine", "dawai", "दवाई", "fogging", "फॉगिंग", "fever", "bukhar", "बुखार", "ambulance", "एम्बुलेंस", "vaccin", "adulter", "milawat", "मिलावट"],
}


def lexicon_scores(text):
    t = text.lower()
    return {cat: sum(1 for k in keys if k in t) for cat, keys in LEXICON.items()}


def hybrid_probs(ml_probs, classes, text, ml_weight=0.55):
    lex = lexicon_scores(text)
    total = sum(lex.values())
    if total == 0:
        return list(ml_probs)
    return [ml_weight * p + (1 - ml_weight) * (lex[c] / total) for p, c in zip(ml_probs, classes)]


class ComplaintClassifier:
    def __init__(self):
        rows = [(p, cat, lang) for cat, langs in CATEGORIES.items() for lang, ps in langs.items() for p in ps]
        rng = random.Random(7)

        # ---- honest evaluation: hold out 20% of ORIGINAL sentences the model never sees
        shuffled = rows[:]
        rng.shuffle(shuffled)
        cut = int(len(shuffled) * 0.8)
        train_rows, test_rows = shuffled[:cut], shuffled[cut:]
        eval_model = _make_pipeline()
        eval_model.fit(*_augment(train_rows, rng))
        ml_only = eval_model.predict([r[0] for r in test_rows])
        self.ml_only_accuracy = round(100 * sum(p == r[1] for p, r in zip(ml_only, test_rows)) / len(test_rows), 1)
        classes = list(eval_model.classes_)
        preds = []
        for r in test_rows:
            hp = hybrid_probs(eval_model.predict_proba([r[0]])[0], classes, r[0])
            preds.append(classes[max(range(len(hp)), key=lambda i: hp[i])])
        correct = sum(1 for p, r in zip(preds, test_rows) if p == r[1])
        self.test_accuracy = round(100 * correct / len(test_rows), 1)
        self.per_lang_accuracy = {}
        for lang in ("en", "hi", "hinglish"):
            idx = [i for i, r in enumerate(test_rows) if r[2] == lang]
            if idx:
                self.per_lang_accuracy[lang] = round(100 * sum(preds[i] == test_rows[i][1] for i in idx) / len(idx), 1)
        self.test_size = len(test_rows)

        # ---- final model trained on everything
        texts, labels = _augment(rows, rng)
        self.train_size = len(texts)
        self.model = _make_pipeline()
        self.model.fit(texts, labels)
        self.classes = list(self.model.classes_)

        # word-level vectorizer used for explanations
        self._word_vec = self.model.named_steps["features"].transformer_list[0][1]
        self._n_word_feats = len(self._word_vec.vocabulary_)
        self._coef = self.model.named_steps["clf"].coef_

    def has_domain_words(self, text):
        return sum(lexicon_scores(text).values()) > 0

    def predict(self, text: str):
        probs = hybrid_probs(self.model.predict_proba([text])[0], self.classes, text)
        ranked = sorted(zip(self.classes, probs), key=lambda x: -x[1])
        top_cat = ranked[0][0]
        return {
            "category": top_cat,
            "confidence": round(float(ranked[0][1]) * 100, 1),
            "top3": [{"category": c, "prob": round(float(p) * 100, 1)} for c, p in ranked[:3]],
            "keywords": self.explain(text, top_cat),
        }

    def explain(self, text: str, category: str, k: int = 5):
        """Which words pushed the model towards this category? (Explainable AI)"""
        ci = self.classes.index(category)
        vec = self._word_vec.transform([text])
        inv = {v: k for k, v in self._word_vec.vocabulary_.items()}
        contrib = []
        for j, val in zip(vec.indices, vec.data):
            w = self._coef[ci][j] * val
            if w > 0:
                contrib.append((inv[j], w))
        contrib.sort(key=lambda x: -x[1])
        t = text.lower()
        lex_hits = [w for w in LEXICON.get(category, []) if w in t]
        out = []
        junk = (STOP - {"water", "light", "garbage", "road", "whole", "entire", "main", "big", "new", "old"}) | {"hai", "hain", "है", "हैं", "रहा", "रही", "रहे", "हो", "गया", "गई", "कि", "और", "भी", "का", "की", "के", "में", "से", "पर", "very", "please", "sir", "ho", "raha hai"}
        for w in lex_hits + [w for w, _ in contrib]:
            if all(part in junk for part in w.split()):
                continue
            if w not in out and not any(w in o or o in w for o in out):
                out.append(w)
        return out[:k]


# ---------------------------------------------------------------- 3. sub-type
SUBTYPES = {
    "Water Supply": [
        ("Water Leakage", ["leak", "burst", "pipe fat", "fat gayi", "wasting", "beh", "लीक", "फट", "बर्बाद"]),
        ("Water Contamination", ["dirty", "smell", "contamin", "muddy", "yellow", "ganda", "badbu", "dooshit", "matmaila", "गंदा", "दूषित", "बदबू"]),
        ("Low Pressure", ["pressure", "प्रेशर", "kam time"]),
        ("Long-term Supply Failure", ["week", "days", "hafte", "din se", "हफ्ते", "दिन से", "teen din", "तीन दिन"]),
        ("Temporary Supply Interruption", ["no water", "not coming", "nahi aa", "pani nahi", "नहीं आ", "tanker", "टैंकर", "cut"]),
    ],
    "Electricity": [
        ("Dangerous Live Wire / Sparking", ["spark", "live", "wire", "fallen", "chingari", "taar", "चिंगारी", "तार", "hanging", "burst", "fat gaya", "फट"]),
        ("Street Light Fault", ["street light", "streetlight", "स्ट्रीट लाइट", "dark at night"]),
        ("Voltage Fluctuation", ["voltage", "वोल्टेज", "upar niche", "fluctuat"]),
        ("Billing / Meter Issue", ["bill", "meter", "बिल", "मीटर"]),
        ("Pole Damage", ["pole", "khamba", "खंभा"]),
        ("Power Outage", ["power cut", "no current", "light nahi", "bijli", "बिजली", "electricity", "current", "light"]),
    ],
    "Roads & Infrastructure": [
        ("Potholes", ["pothole", "gadde", "gadda", "गड्ढ", "pits", "pit"]),
        ("Bridge / Railing Damage", ["bridge", "railing", "pul", "पुल", "रेलिंग"]),
        ("Traffic Signal Fault", ["signal", "सिग्नल"]),
        ("Encroachment", ["encroach", "kabza", "अतिक्रमण"]),
        ("Incomplete Construction", ["incomplete", "adhura", "अधूरा", "dug", "khod", "खोद"]),
        ("Footpath Damage", ["footpath", "फुटपाथ"]),
        ("Broken Road", ["broken", "crack", "tooti", "टूटी", "damaged", "kharab"]),
    ],
    "Sanitation & Garbage": [
        ("Dead Animal", ["dead animal", "mara hua", "मरा हुआ"]),
        ("Garbage Burning", ["burn", "jala", "जला", "smoke", "dhuan"]),
        ("Public Toilet Issue", ["toilet", "urinal", "शौचालय"]),
        ("Overflowing Dustbin", ["overflow", "dustbin", "कूड़ेदान", "bhara"]),
        ("Garbage Not Collected", ["not collected", "pick", "lifted", "nahi uthaya", "नहीं उठाया", "van", "gadi", "गाड़ी", "vehicle"]),
        ("Street Not Cleaned", ["swept", "sweeper", "safai", "सफाई"]),
    ],
    "Drainage & Sewage": [
        ("Open Manhole", ["manhole", "मैनहोल", "lid", "dhakkan", "ढक्कन"]),
        ("Sewage Mixing in Drinking Water", ["drinking", "peene", "पीने"]),
        ("Waterlogging", ["waterlog", "rain", "barish", "बारिश", "जलभराव", "bhar gaya", "भर गया", "ghus", "घुस", "entering"]),
        ("Sewer Overflow", ["overflow", "sewer", "सीवर", "chamber", "beh"]),
        ("Blocked Drain", ["block", "choke", "chok", "jam", "जाम", "चोक", "clog", "band"]),
    ],
    "Public Safety": [
        ("Stray Animal Menace", ["dog", "kutte", "कुत्ते", "cattle", "gaay", "पशु", "monkey", "bandar"]),
        ("Structural Danger", ["collapse", "building", "girne", "इमारत", "tree", "ped", "पेड़"]),
        ("Women Safety", ["eve teas", "chheda", "छेड़छाड़"]),
        ("Crime / Theft", ["snatch", "theft", "chori", "चोरी", "स्नैचिंग"]),
        ("Illegal Activity", ["illegal", "liquor", "daru", "शराब", "gambl", "jua", "जुआ", "license"]),
        ("Noise Pollution", ["loud", "music", "noise", "gaane", "संगीत"]),
    ],
    "Health & Hygiene": [
        ("Vector-borne Disease Risk", ["mosquito", "dengue", "malaria", "machhar", "मच्छर", "डेंगू", "fogging", "फॉगिंग"]),
        ("Disease Outbreak", ["fever", "diarr", "bukhar", "बुखार", "dast", "दस्त"]),
        ("Hospital / Doctor Unavailable", ["doctor", "hospital", "health centre", "phc", "अस्पताल", "डॉक्टर", "ambulance", "एम्बुलेंस"]),
        ("Medicine Shortage", ["medicine", "dawai", "दवा"]),
        ("Food Safety", ["food", "khana", "खाना", "milk", "doodh", "दूध", "adulter", "milawat", "मिलावट"]),
    ],
}


def detect_subtype(text: str, category: str) -> str:
    t = text.lower()
    for name, keys in SUBTYPES.get(category, []):
        if any(k in t for k in keys):
            return name
    return "General"


# ---------------------------------------------------------------- 4. location
KNOWN_PLACES = [
    "vijay nagar", "palasia", "rajwada", "bhawarkua", "sapna sangeeta", "annapurna", "rau", "mhow",
    "khajrana", "sudama nagar", "scheme 54", "scheme 78", "lig colony", "mig colony", "super corridor",
    "rajendra nagar", "nipania", "bengali square", "musakhedi", "aerodrome road", "mg road", "ab road",
    "geeta bhawan", "chhoti gwaltoli", "malharganj", "banganga", "pipliyahana", "tilak nagar", "saket nagar",
    "old palasia", "new palasia", "navlakha", "khandwa road", "silicon city", "bicholi mardana",
    "sage university", "baikunth dham",
]
HINDI_PLACES = {"विजय नगर": "Vijay Nagar", "पलासिया": "Palasia", "राजवाड़ा": "Rajwada", "भंवरकुआं": "Bhawarkua",
                "खजराना": "Khajrana", "सुदामा नगर": "Sudama Nagar", "राऊ": "Rau", "अन्नपूर्णा": "Annapurna",
                "निपानिया": "Nipania", "तिलक नगर": "Tilak Nagar"}

SUFFIX = r"(?:nagar|colony|road|marg|chowk|square|vihar|puri|ganj|market|bazaar|layout|enclave|society|apartments?|basti|gaon|village|mohalla|chauraha)"
STOP = HINGLISH_WORDS | {"the", "a", "an", "our", "my", "in", "at", "is", "are", "of", "on", "and", "since", "for", "from",
                         "near", "there", "this", "that", "whole", "entire", "full", "all", "no", "not", "water", "light",
                         "garbage", "road", "raha", "rahi", "every", "main", "big", "new", "old"}

LOC_PATTERNS = [
    r"\b(ward\s*(?:no\.?|number)?\s*\d+)",
    r"\b(sector\s*[-\s]?\d+[a-z]?)",
    r"\b(scheme\s*(?:no\.?)?\s*\d+)",
    r"\b(\d+\s*(?:no\.?)?\s*(?:gali|lane|street|cross))",
]
HI_LOC_PATTERNS = [r"(वार्ड\s*(?:नंबर|नं\.?)?\s*\d+)", r"(सेक्टर\s*\d+)",
                   r"([\u0900-\u097F]+\s(?:नगर|कॉलोनी|मार्ग|चौक|बाज़ार|गांव|बस्ती))"]


def _trim_place(words):
    """keep the last 1-3 meaningful words before the suffix (drops 'raha hai' etc.)"""
    keep = []
    for w in reversed(words):
        if w in STOP or len(keep) == 3:
            break
        keep.insert(0, w)
    return keep


def extract_location(text: str):
    t = text.lower().strip()
    for hi_name, en_name in HINDI_PLACES.items():
        if hi_name in text:
            return en_name
    for place in sorted(KNOWN_PLACES, key=len, reverse=True):
        if re.search(r"\b" + re.escape(place) + r"\b", t):
            return place.title().replace("Mg ", "MG ").replace("Ab ", "AB ").replace("Lig ", "LIG ").replace("Mig ", "MIG ")
    for pat in LOC_PATTERNS:
        m = re.search(pat, t)
        if m:
            return m.group(1).strip().title()
    for pat in HI_LOC_PATTERNS:
        m = re.search(pat, text)
        if m:
            return m.group(1).strip()
    # "<name> nagar/colony/road..."
    for m in re.finditer(r"([a-z0-9 .'-]+?)\s(" + SUFFIX + r")\b", t):
        words = re.findall(r"[a-z0-9]+", m.group(1))
        keep = _trim_place(words)
        if keep:
            return (" ".join(keep) + " " + m.group(2)).title()
    # "near the bus stand", "opposite city hospital"
    m = re.search(r"\b(?:near|opposite|behind|in front of|beside|ke paas|ke pass)\s+(?:the\s+)?([a-z0-9 ]{3,30})", t)
    if m:
        words = re.findall(r"[a-z0-9]+", m.group(1))
        keep = []
        for w in words:
            if w in STOP - {"main", "old", "new"} or len(keep) == 3:
                break
            keep.append(w)
        if keep:
            return "Near " + " ".join(keep).title()
    m = re.search(r"([a-z0-9 ]{3,40})\s(?:ke paas|ke pass|ke samne)", t)
    if m:
        keep = _trim_place(re.findall(r"[a-z0-9]+", m.group(1)))
        if keep:
            return "Near " + " ".join(keep).title()
    m = re.search(r"([\u0900-\u097F ]{2,20})\s(?:के पास|के सामने)", text)
    if m:
        return m.group(1).strip() + " के पास"
    return None


def clean_location_answer(text: str) -> str:
    """User answered 'where?' directly - use their answer, lightly cleaned."""
    found = extract_location(text)
    if found:
        return found
    t = re.sub(r"^(it is|its|it's|in|at|near|location is|address is|mera address|hamara area)\s+", "", text.strip(), flags=re.I)
    return t.strip(" .").title()[:60]


# ---------------------------------------------------------------- 5. duration
NUM_WORDS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "ten": 10, "a": 1, "an": 1,
             "ek": 1, "do": 2, "teen": 3, "char": 4, "chaar": 4, "paanch": 5, "panch": 5, "das": 10,
             "एक": 1, "दो": 2, "तीन": 3, "चार": 4, "पांच": 5, "दस": 10}
UNITS = {"hour": 1, "hr": 1, "ghante": 1, "ghanta": 1, "घंटे": 1, "घंटा": 1,
         "day": 24, "din": 24, "दिन": 24,
         "week": 168, "hafte": 168, "hafta": 168, "हफ्ते": 168, "हफ्ता": 168, "सप्ताह": 168,
         "month": 720, "mahine": 720, "mahina": 720, "महीने": 720, "महीना": 720}


def extract_duration(text: str):
    """Return (hours, human_text) or (None, None)."""
    t = text.lower()
    m = re.search(r"(\d+|" + "|".join(map(re.escape, NUM_WORDS)) + r")\s*(" + "|".join(map(re.escape, UNITS)) + r")", t)
    if m:
        n = int(m.group(1)) if m.group(1).isdigit() else NUM_WORDS[m.group(1)]
        unit = next(u for u in UNITS if m.group(2).startswith(u))
        return n * UNITS[unit], m.group(0)
    simple = [
        (["since morning", "subah se", "सुबह से", "since afternoon", "dopahar se"], 6),
        (["since last night", "since night", "kal raat", "raat se", "रात से"], 12),
        (["since yesterday", "kal se", "कल से", "yesterday"], 24),
        (["for a week", "last week", "ek hafte", "एक हफ्ते"], 168),
        (["for months", "mahino se", "महीनों से"], 1440),
        (["for many days", "kai din", "कई दिन", "for days"], 96),
        (["today", "aaj", "आज", "just now", "abhi"], 2),
    ]
    for keys, hrs in simple:
        for k in keys:
            if k in t:
                return hrs, k
    return None, None


# ---------------------------------------------------------------- 6. sentiment
NEG_WORDS = ["not", "no", "never", "worst", "bad", "terrible", "horrible", "useless", "angry", "frustrat", "fed up",
             "nobody", "ignored", "again", "still", "pathetic", "disgust", "unbearable", "dangerous", "suffer",
             "nahi", "nahin", "bekar", "bakwas", "ganda", "pareshan", "koi sun nahi", "phir se", "abhi bhi", "khatarnak",
             "नहीं", "बेकार", "खराब", "परेशान", "गंदा", "फिर से", "अभी भी", "खतरनाक", "असहनीय", "कोई सुन नहीं"]
POS_WORDS = ["thank", "thanks", "good", "great", "fixed", "solved", "resolved", "happy", "satisfied", "excellent", "working now",
             "quick", "fast", "done", "shukriya", "dhanyawad", "accha", "badhiya", "theek ho gaya", "sahi", "khush",
             "धन्यवाद", "अच्छा", "बढ़िया", "ठीक हो गया", "संतुष्ट", "शुक्रिया", "खुश"]


def sentiment_score(text: str) -> float:
    """-1 (very negative) ... +1 (very positive)"""
    t = text.lower()
    neg = sum(t.count(w) for w in NEG_WORDS)
    pos = sum(t.count(w) for w in POS_WORDS)
    neg += text.count("!") * 0.5
    caps = sum(1 for w in re.findall(r"[A-Z]{3,}", text))
    neg += caps * 0.5
    total = neg + pos
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 2)


# ---------------------------------------------------------------- 7. severity
URGENT_WORDS = {
    # word: points
    "danger": 8, "dangerous": 8, "fire": 10, "spark": 9, "electrocut": 12, "shock": 8, "live wire": 12, "accident": 9,
    "child": 6, "children": 6, "school": 4, "hospital": 6, "emergency": 10, "urgent": 6, "death": 12, "died": 12,
    "injur": 9, "collapse": 10, "attack": 8, "bite": 7, "outbreak": 9, "dengue": 7, "cholera": 10, "sick": 5,
    "ill": 4, "burst": 6, "flood": 8, "overflow": 4, "open manhole": 10, "elderly": 5, "houses": 5, "gharon": 5, "घरों": 5, "whole colony": 5, "entire area": 5,
    "khatra": 8, "khatarnak": 8, "aag": 10, "chingari": 9, "bachon": 6, "bachche": 6, "turant": 6, "maut": 12,
    "hadsa": 9, "bimar": 5, "puri colony": 5,
    "खतरा": 8, "खतरनाक": 8, "आग": 10, "चिंगारी": 9, "बच्चों": 6, "तुरंत": 6, "मौत": 12, "दुर्घटना": 9, "बीमार": 5,
    "हमला": 8, "पूरी कॉलोनी": 5, "अस्पताल": 6,
}
SUBTYPE_BONUS = {"Dangerous Live Wire / Sparking": 6, "Open Manhole": 6, "Sewage Mixing in Drinking Water": 6,
                 "Water Contamination": 4, "Disease Outbreak": 5, "Structural Danger": 5, "Women Safety": 4,
                 "Stray Animal Menace": 2, "Billing / Meter Issue": -6, "Noise Pollution": -4}


def compute_severity(text, category, subtype, duration_hours, similar_count):
    t = text.lower()
    found = [w for w in URGENT_WORDS if w in t]
    f_keywords = min(30, sum(URGENT_WORDS[w] for w in found))

    s = sentiment_score(text)
    f_sentiment = round(max(0.0, -s) * 15)

    f_repeat = min(20, similar_count * 5)

    if duration_hours is None:
        f_duration = 0
    elif duration_hours >= 168:
        f_duration = 15
    elif duration_hours >= 72:
        f_duration = 11
    elif duration_hours >= 24:
        f_duration = 7
    else:
        f_duration = 3

    f_critical = max(0, min(20, DEPARTMENTS[category]["criticality"] + SUBTYPE_BONUS.get(subtype, 0)))

    score = int(min(100, f_keywords + f_sentiment + f_repeat + f_duration + f_critical))
    if score >= 65:
        priority = "Critical"
    elif score >= 45:
        priority = "High"
    elif score >= 25:
        priority = "Medium"
    else:
        priority = "Low"

    factor = {"Critical": 0.25, "High": 0.5, "Medium": 1.0, "Low": 1.5}[priority]
    deadline_hours = max(2, round(DEPARTMENTS[category]["base_hours"] * factor))

    return {
        "score": score,
        "priority": priority,
        "deadline_hours": deadline_hours,
        "breakdown": [
            {"factor": "Urgent keywords", "points": f_keywords, "max": 30, "detail": ", ".join(found[:4]) or "none found"},
            {"factor": "Sentiment intensity", "points": f_sentiment, "max": 15, "detail": f"sentiment {s:+.2f}"},
            {"factor": "Repeated in same area", "points": f_repeat, "max": 20, "detail": f"{similar_count} similar open complaint(s)"},
            {"factor": "Duration of issue", "points": f_duration, "max": 15, "detail": f"{duration_hours} h" if duration_hours else "not mentioned"},
            {"factor": "Service criticality", "points": f_critical, "max": 20, "detail": f"{category} / {subtype}"},
        ],
    }


# ---------------------------------------------------------------- 8. similarity
class SimilarityEngine:
    def __init__(self):
        self.vec = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 4), sublinear_tf=True)

    def find_similar(self, text, location, category, past, threshold=0.30):
        """past = list of dicts with id, description, location, category, status, created_at"""
        cands = [p for p in past if p["category"] == category]
        if not cands:
            return []
        docs = [text] + [p["description"] for p in cands]
        m = self.vec.fit_transform(docs)
        sims = cosine_similarity(m[0:1], m[1:])[0]
        out = []
        loc = (location or "").lower().strip()
        for p, s in zip(cands, sims):
            same_loc = bool(loc) and (p["location"] or "").lower().strip() == loc
            score = s + (0.35 if same_loc else 0)
            if score >= threshold and same_loc:
                out.append({**p, "similarity": round(min(1.0, score) * 100)})
        out.sort(key=lambda x: -x["similarity"])
        return out[:5]


# ---------------------------------------------------------------- 9. feedback
NOT_FIXED = ["not fixed", "not solved", "not resolved", "still", "again", "same problem", "nothing done", "fake",
             "no work", "didn't", "did not", "hasn't", "has not", "nahi hua", "theek nahi", "abhi bhi", "phir se",
             "kuch nahi kiya", "jhooth", "नहीं हुआ", "ठीक नहीं", "अभी भी", "फिर से", "कुछ नहीं किया", "झूठ"]


def evaluate_feedback(rating: int, text: str):
    t = (text or "").lower()
    s = sentiment_score(text or "")
    flags = [w for w in NOT_FIXED if w in t]
    if flags or rating <= 2 or (s < -0.3 and rating <= 3):
        reason = "Citizen says the issue is not really solved" if flags else "Low satisfaction / negative feedback"
        return {"genuinely_resolved": False, "sentiment": s, "reason": reason, "signals": flags}
    return {"genuinely_resolved": True, "sentiment": s, "reason": "Citizen is satisfied", "signals": []}

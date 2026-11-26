"""What the student wants from Owl, worked out from the words (fast, works without AI, easy to test).

study        a study question → step-by-step answer (the Ask AI tutor)
tutors       find teachers (by name, subject or topic)
new_tutors   teachers who joined recently
lectures     pre-recorded lectures
groups       group / combined classes
learn_where  "where do I learn X" → teachers + lectures + classes on it
help         how to use NeuralHub (help articles)
support      a problem for the NeuralHub team (ticket)
"""
from __future__ import annotations

import re

WORD = re.compile(r"[a-z]+")
TEACHER = {"teacher", "teachers", "tutor", "tutors", "ustad", "ustaad", "ustaz", "sir", "miss", "madam", "mam", "maam",
           "instructor", "instructors"}
NEW = {"new", "newest", "naye", "naya", "nae", "nai", "latest", "recent", "recently", "joined"}
FIND = {"find", "search", "show", "list", "best", "top", "who", "kaun", "kon", "dikhao", "dikha", "batao", "btao",
        "chahiye", "need", "available", "recommend", "suggest", "good", "acha", "achay", "ache", "konsa", "kaunsa", "which",
        "all", "sab", "sare", "saray", "teaches", "parhata", "parhati", "padhata", "padhati"}
LECTURE = {"lecture", "lectures", "recorded", "recording", "recordings"}
GROUP_PHRASES = ("group class", "combined class", "live class", "upcoming class", "group classes", "combined classes",
                 "live classes", "upcoming classes", "class kab", "classes kab", "seat reserve", "reserve a seat",
                 "reserve seat")
WHERE = ("where can i learn", "where can i study", "where should i learn", "where should i study", "where to learn",
         "where to study", "where do i learn", "where do i study", "kahan se parh", "kahan se padh", "kahan sy parh",
         "kahan se seekh", "kahan se sikh", "kahan parh", "kidhar se parh", "kis se parh", "kis se padh", "kahan se study",
         "how do i learn", "how can i learn", "how to learn", "kaise seekh", "kaise parh", "kaise padh")
SUPPORT = ("support", "ticket", "complaint", "complain", "not working", "doesn't work", "does not work", "kaam nahi",
           "kam nahi", "nahi chal", "nahi chalta", "bug", "error aa", "masla", "problem with", "refund", "blocked",
           "contact the team", "contact team", "admin se", "talk to a person", "human")
HOWISH = ("how do i", "how can i", "how to", "how does", "how do", "where is", "where do i", "where can i find", "what is the",
          "kaise", "kese", "kaisay", "kesy", "kahan hai", "kahan he", "kidhar hai", "kya hota", "ka tareeqa", "tarika",
          "what is", "kya hai")
APP = {"neuralhub", "owl", "certificate", "certificates", "course", "courses", "quiz", "quizzes", "assessment",
       "assessments", "assignment", "assignments", "settings", "profile", "notification", "notifications", "messages",
       "request", "requests", "book", "booking", "session", "sessions", "password", "account", "language", "feature",
       "app", "button", "progress", "streak", "games", "flashcards", "lecture", "lectures", "seat", "meet", "camera",
       "avatar", "logout", "login", "signup", "upload", "tutor", "tutors", "teacher", "teachers"}
APP_PHRASES = ("study set", "talk mode", "dark mode", "mood camera", "ai tutor", "ai professor", "live example",
               "class notes", "spaced review", "my courses", "find tutors", "live class", "group class")
URDU = {"kya", "hai", "hain", "ka", "ki", "ke", "ko", "mujhe", "muje", "mjhe", "mujhay", "kaise", "kese", "kahan", "kaun",
        "kon", "batao", "btao", "dikhao", "chahiye", "mein", "mn", "par", "koi", "hafte", "aaj", "kal", "naye", "nae", "kab", "aur", "se", "sy", "krna", "karna",
        "parhna", "samjhao", "samjha", "samjhayen", "hy", "nahi", "ye", "yeh", "wo", "woh", "kar", "kr", "do", "dein"}
EXPLAIN = {"explain", "samjhao", "samjha", "samjhayen", "samjhaein", "samjhain", "why", "kyun", "kyon", "meaning",
           "matlab", "difference", "farq", "define", "definition"}
SUBJECTS = {"biology": "Biology", "bio": "Biology", "chemistry": "Chemistry", "chem": "Chemistry", "physics": "Physics",
            "maths": "Mathematics", "math": "Mathematics", "mathematics": "Mathematics", "english": "English",
            "computer": "Computer Science", "coding": "Computer Science", "programming": "Computer Science"}
STOP = TEACHER | NEW | FIND | LECTURE | URDU | EXPLAIN | {
    "the", "and", "for", "you", "your", "with", "this", "that", "are", "what", "where", "when", "how", "can", "should",
    "learn", "study", "studying", "parh", "parhun", "parhna", "padh", "seekh", "sikh", "class", "classes", "group",
    "combined", "live", "upcoming", "please", "plz", "pls", "about", "there", "any", "koi", "some", "from", "want",
    "teach", "teaching", "tell", "give", "have", "has", "does", "kidhar", "liye", "lye", "wala", "wali", "walay", "subject",
    "topic", "video", "videos", "me", "my", "is", "on", "in", "of", "a", "an", "to", "it", "do", "i", "we", "chapter",
    "week", "today", "tomorrow", "hafte", "aaj", "kal", "seats", "seat", "reserve", "joined", "app", "neuralhub", "owl",
    "solve", "said", "says", "milta", "milti", "working", "work", "help", "know", "understand", "samajh", "aaya", "aya",
    "aye", "hoti", "hota", "kaam", "question", "answer"}
HONORIFIC = {"dr", "mr", "mrs", "ms", "miss", "sir", "prof", "professor", "madam", "mam"}


def words(text: str) -> list[str]:
    return WORD.findall((text or "").lower())


def is_urdu(text: str) -> bool:
    w = words(text)
    return sum(1 for x in w if x in URDU) >= 2


def subject_of(text: str) -> str:
    for w in words(text):
        if w in SUBJECTS:
            return SUBJECTS[w]
    return ""


def topic_words(text: str) -> list[str]:
    """Words that say WHAT the student wants (for matching lectures, classes and teachers)."""
    out = []
    for w in words(text):
        if len(w) >= 4 and w not in STOP and w not in SUBJECTS and w not in out:
            out.append(w)
    return out[:8]


def name_tokens(name: str) -> set[str]:
    return {w for w in words(name) if len(w) >= 3 and w not in HONORIFIC}


def detect(text: str, tutor_names: dict[str, str] | None = None) -> tuple[str, list[str]]:
    """(intent, ids of teachers named in the text)."""
    t = " ".join((text or "").lower().split())
    w = set(words(t))
    named = []
    for tid, name in (tutor_names or {}).items():
        toks = name_tokens(name)
        if toks and toks & w:
            named.append(tid)
    has_teacher = bool(w & TEACHER)
    howish = any(p in t for p in HOWISH)

    if any(p in t for p in SUPPORT):
        return "support", named
    if has_teacher and w & NEW:
        return "new_tutors", named
    if any(p in t for p in GROUP_PHRASES):
        return "groups", named
    if any(p in t for p in WHERE):
        return "learn_where", named
    if w & LECTURE:
        return "lectures", named
    app = bool(w & APP) or any(p in t for p in APP_PHRASES)
    if named and (has_teacher or len(w) <= 6 or w & FIND):
        return "tutors", named
    if howish and app:
        return "help", named  # "how do I book a tutor?" → help (with teacher cards, see router)
    if has_teacher and (w & FIND or len(w) <= 5):
        return "tutors", named
    if "neuralhub" in w or "owl" in w:
        return "help", named
    return "study", named


def study_mode(text: str, chosen: str) -> str:
    if chosen in ("solve", "explain", "hint", "check", "practice"):
        return chosen
    return "explain" if set(words(text)) & EXPLAIN or "what is" in (text or "").lower() or "kya hai" in (text or "").lower() \
        else "solve"

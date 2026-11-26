"""Fact-check pass for a generated course book (runs after writing, before the student sees it).

A second AI acts as a strict examiner for each day: it lists sentences that are factually wrong (or wrong for the
level) with the exact wrong words and a corrected version. Only exact matches are replaced, so nothing else in the
book can change. The five days are checked at the same time. If the checker is unavailable the course is returned
unchanged (never blocked).
"""
from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel, Field

log = logging.getLogger("neuralhub.syllabus.fact_check")

MAX_FIXES_PER_DAY = 12
DAY_RE = re.compile(r"^## Day \d+.*$", re.M)


class Fix(BaseModel):
    wrong: str
    correct: str
    why: str = ""


class Fixes(BaseModel):
    fixes: list[Fix] = Field(default_factory=list)


def enabled() -> bool:
    return os.getenv("SYLLABUS_FACT_CHECK", "on").lower() not in ("off", "false", "0")


def check_prompt(topic: str, level: str, day_text: str, subject: str = "Biology") -> str:
    return f"""You are a strict {subject} examiner checking one day of a course book on "{topic}" for a {level or 'school'}
student before it is published. Find ONLY real errors:
- wrong facts (wrong bone/muscle/nerve/vessel, wrong origin/insertion/innervation/drainage, wrong function, wrong
  order of a process, wrong numbers, a term used for the wrong thing, a structure placed in the wrong region),
- statements that contradict each other inside the text,
- wrong names of phases/parts (e.g. a phase listed in the wrong part of a cycle).
Do NOT report style, length, simplifications that are still true, or missing extra detail.
For each error give "wrong": the EXACT words copied from the text (a short phrase or one sentence, character for
character), "correct": the corrected words that can replace it in the same place (same style and length), and
"why": one short line. If there are no real errors return an empty list.

TEXT OF THE DAY:
\"\"\"
{day_text[:14000]}
\"\"\"
Return ONLY JSON: {{"fixes": [{{"wrong": "...", "correct": "...", "why": "..."}}]}}"""


def split_days(text: str) -> list[tuple[int, int]]:
    """(start, end) of each '## Day N' section."""
    starts = [m.start() for m in DAY_RE.finditer(text)]
    out = []
    for i, s in enumerate(starts):
        nxt = re.search(r"^## (?!Day \d)", text[s + 3:], re.M)
        end = starts[i + 1] if i + 1 < len(starts) else (s + 3 + nxt.start() if nxt else len(text))
        out.append((s, end))
    return out


def _check_day(gateway, topic: str, level: str, day_text: str) -> list[Fix]:
    res = gateway.generate_json("evaluate", check_prompt(topic, level, day_text), Fixes,
                                prompt_version="course-factcheck@1.0", temperature=0.0, max_tokens=2500,
                                timeout_s=90, skip=("ollama",))
    return res.data.fixes[:MAX_FIXES_PER_DAY]


def apply_fixes(day_text: str, fixes: list[Fix]) -> tuple[str, list[dict]]:
    applied = []
    for f in fixes:
        w, c = (f.wrong or "").strip(), (f.correct or "").strip()
        if len(w) < 8 or not c or w == c or day_text.count(w) != 1:
            continue                     # must be an exact, unique quote — never guess where it goes
        day_text = day_text.replace(w, c, 1)
        applied.append({"wrong": w, "correct": c, "why": f.why})
    return day_text, applied


def fact_check(text: str, topic: str, level: str, gateway=None) -> tuple[str, list[dict]]:
    """Corrected course text + the list of fixes made (for the logs)."""
    if not enabled() or not text:
        return text, []
    if gateway is None:
        from modules.professor.llm.gateway import gateway as gw

        gateway = gw
    spans = split_days(text)
    if not spans:
        return text, []

    def run(span):
        s, e = span
        try:
            return _check_day(gateway, topic, level, text[s:e])
        except Exception as ex:  # noqa: BLE001 - a checker failure never blocks the course
            log.info("Fact-check of a day failed: %s", ex)
            return []

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(run, spans))
    out, done = [], []
    last = 0
    for (s, e), fixes in zip(spans, results):
        out.append(text[last:s])
        fixed, applied = apply_fixes(text[s:e], fixes)
        out.append(fixed)
        done += applied
        last = e
    out.append(text[last:])
    if done:
        log.info("Course fact-check fixed %d statement(s) in %r", len(done), topic)
    return "".join(out), done

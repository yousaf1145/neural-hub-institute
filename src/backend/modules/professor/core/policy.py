"""Pedagogy Policy Engine (Phase 2 · Step 8) — the AI Professor's brain.

    decide(PolicyInput) -> Decision(action, strategy, reason, ...)

The policy decides WHAT to do next; the LLM only decides HOW to say it. Pure functions, no AI, no database,
so every rule is predictable, testable and explainable. Every decision carries a `reason` that is logged.

Order of checks (first match wins):
  1. Session start / resume ................................. INTRODUCE (or a warm-up later in V2)
  2. Student asks their own question ......................... ANSWER_DOUBT
  3. Student asks to repeat / is confused .................... next untried strategy from the ladder
  4. Student is frustrated ................................... ENCOURAGE (+ simpler next step, no new question)
  5. Student wants to move on / bored and already strong ..... SPEED_UP to the check (or NEXT if mastered)
  6. A check answer was just graded .......................... correct → advance · partial → HINT · wrong → remediate
  7. No check question in the last 3 tutor turns ............. CHECK_QUESTION
  8. Otherwise follow the teaching loop ...................... INTRODUCE → EXPLAIN → CHECK → APPLY → RECAP → NEXT
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from modules.professor.core.state import ConceptProgress


class Action(str, Enum):
    INTRODUCE = "INTRODUCE"
    EXPLAIN = "EXPLAIN"
    SIMPLIFY = "SIMPLIFY"
    GIVE_EXAMPLE = "GIVE_EXAMPLE"
    CHECK_QUESTION = "CHECK_QUESTION"
    HINT = "HINT"
    ENCOURAGE = "ENCOURAGE"
    SPEED_UP = "SPEED_UP"
    REVIEW_PREREQUISITE = "REVIEW_PREREQUISITE"
    RECAP = "RECAP"
    NEXT_CONCEPT = "NEXT_CONCEPT"
    ANSWER_DOUBT = "ANSWER_DOUBT"
    SUGGEST_TUTOR = "SUGGEST_TUTOR"
    SESSION_COMPLETE = "SESSION_COMPLETE"
    DAY_INTRO = "DAY_INTRO"              # start of a syllabus day: the big picture + today's plan, then topic 1
    WARM_UP = "WARM_UP"                  # start of a class: quick questions on topics found hard last time
    REVIEW_BLOCK = "REVIEW_BLOCK"        # block flow: recap the topics just taught, then the questions begin


# How each remediation strategy (teaching.yaml strategy_ladder) is carried out.
STRATEGY_ACTION = {
    "plain_words": Action.SIMPLIFY,
    "everyday_example": Action.GIVE_EXAMPLE,
    "board_visual": Action.EXPLAIN,
    "worked_example": Action.GIVE_EXAMPLE,
    "interest_analogy": Action.GIVE_EXAMPLE,
    "prerequisite_review": Action.REVIEW_PREREQUISITE,
    "learner_does_step": Action.CHECK_QUESTION,
    "switch_language": Action.SIMPLIFY,
    "tutor_handoff": Action.SUGGEST_TUTOR,
}

WRONG_LIMIT = 3          # after this many wrong answers in a row: mark weak and move on
CHECK_EVERY = 3          # ask a check question at least every 3 tutor turns


@dataclass
class PolicyInput:
    progress: ConceptProgress
    ladder: list[str]                              # the subject pack's strategy_ladder
    event: str = "message"                         # "start" | "message" | "graded"
    intent: str = "chat"                           # answer | question | next | repeat | chat
    affect: str = "neutral"
    verdict: Optional[str] = None                  # when event == "graded": correct | partial | wrong
    has_prerequisites: bool = False
    prerequisite_weak: bool = False                # a prerequisite of this concept is weak/new
    turns_since_check: int = 0
    is_last_concept: bool = False
    mastered_threshold: float = 0.8


@dataclass
class Decision:
    action: Action
    reason: str
    strategy: Optional[str] = None                 # remediation strategy used (logged for self-learning)
    question_stage: Optional[str] = None           # "check" | "apply" when a question should be asked
    mark_weak: bool = False
    next_stage: Optional[str] = None               # stage the concept moves to after this turn
    follow_up: Optional[Action] = None             # e.g. ENCOURAGE now, then SIMPLIFY in the same reply
    meta: dict = field(default_factory=dict)


def next_strategy(p: PolicyInput) -> Optional[str]:
    """First strategy on the ladder not yet tried for this concept (skips ones that cannot apply)."""
    for s in p.ladder:
        if s in p.progress.tried:
            continue
        if s == "prerequisite_review" and not p.has_prerequisites:
            continue
        if s == "tutor_handoff":
            continue  # only used when the student keeps failing (handled by WRONG_LIMIT)
        return s
    return None


def _remediate(p: PolicyInput, why: str) -> Decision:
    # two wrong answers and a weak prerequisite: go back to the prerequisite first
    if (p.progress.wrong_streak >= 2 and p.has_prerequisites and p.prerequisite_weak
            and "prerequisite_review" not in p.progress.tried):
        return Decision(Action.REVIEW_PREREQUISITE, f"{why}→prerequisite_review (2 wrong + weak prerequisite)",
                        strategy="prerequisite_review", next_stage="check")
    # help given BEFORE the concept was explained must not skip the explanation
    after = "check" if p.progress.stage in ("check", "apply", "recap", "done") else "explain"
    s = next_strategy(p)
    if s is None:  # ladder used up
        return Decision(Action.SUGGEST_TUTOR, f"{why}→ladder exhausted", strategy="tutor_handoff",
                        mark_weak=True, next_stage="done")
    action = STRATEGY_ACTION[s]
    if s == "learner_does_step":
        return Decision(action, f"{why}→{s}", strategy=s, question_stage="check", next_stage="check")
    return Decision(action, f"{why}→{s}", strategy=s, next_stage=after)


def _advance(p: PolicyInput, why: str) -> Decision:
    """Move one step along the teaching loop after a correct answer."""
    stage = p.progress.stage
    if stage in ("intro", "explain", "check"):
        return Decision(Action.CHECK_QUESTION, f"{why}→apply question", question_stage="apply", next_stage="apply")
    if stage == "apply":
        return Decision(Action.RECAP, f"{why}→recap", next_stage="recap")
    return _next_concept(p, why)


def _next_concept(p: PolicyInput, why: str) -> Decision:
    if p.is_last_concept:
        return Decision(Action.SESSION_COMPLETE, f"{why}→last concept done", next_stage="done")
    return Decision(Action.NEXT_CONCEPT, f"{why}→next concept", next_stage="done")


def decide(p: PolicyInput) -> Decision:
    pr = p.progress

    # 1. session start: introduce the current concept with a real-life hook
    #    (NEXT_CONCEPT replies already introduce the following concept, so "intro" is only used at start)
    if p.event == "start" or (pr.stage == "intro" and p.event != "graded" and p.intent != "question"):
        return Decision(Action.INTRODUCE, "loop:intro (hook)", next_stage="explain")

    # 2. the student's own question
    if p.intent == "question" and p.event != "graded":
        return Decision(Action.ANSWER_DOUBT, "rule:student question→ANSWER_DOUBT", next_stage=pr.stage)

    # 3. "I don't understand" / confused
    if p.event != "graded" and (p.intent == "repeat" or p.affect == "confused"):
        return _remediate(p, "rule:confused" if p.affect == "confused" else "rule:asked to repeat")

    # 4. frustrated: encourage first, then a smaller step (no new question straight away)
    if p.affect == "frustrated" and p.verdict != "correct" and not (p.event == "graded" and pr.wrong_streak >= WRONG_LIMIT):
        nxt = next_strategy(p) or "plain_words"
        return Decision(Action.ENCOURAGE, f"rule:frustrated→ENCOURAGE+{nxt}", strategy=nxt,
                        follow_up=STRATEGY_ACTION.get(nxt, Action.SIMPLIFY), next_stage="check")

    # 5. wants to move on / bored
    if p.event != "graded" and (p.intent == "next" or p.affect == "bored"):
        if pr.stage in ("recap", "done"):
            return _next_concept(p, "rule:next after recap")
        if pr.mastery >= p.mastered_threshold:
            return _next_concept(p, "rule:bored+mastered")
        if p.intent == "next" and pr.stage in ("intro", "explain"):
            # "next" before the concept was taught means "go on", not "test me": teach first
            return Decision(Action.EXPLAIN, "rule:next before explaining→EXPLAIN", next_stage="check")
        if p.intent == "next":  # "go on" is not "this is easy": no praise, just the next step (the check)
            return Decision(Action.CHECK_QUESTION, "rule:next→check", question_stage="check", next_stage="check")
        if pr.mastery >= 0.7:
            return Decision(Action.SPEED_UP, "rule:bored→SPEED_UP to check", question_stage="check", next_stage="check")

    # 6. a check answer was graded
    if p.event == "graded":
        if p.verdict == "correct":
            if pr.mastery >= p.mastered_threshold and pr.stage in ("apply", "recap"):
                return Decision(Action.RECAP, "graded:correct+mastered→recap", next_stage="recap")
            return _advance(p, "graded:correct")
        if p.verdict == "partial":
            return Decision(Action.HINT, "graded:partial→HINT", question_stage=pr.stage if pr.stage in ("check", "apply") else "check",
                            next_stage=pr.stage if pr.stage in ("check", "apply") else "check")
        # wrong
        if pr.wrong_streak >= WRONG_LIMIT:
            return Decision(Action.SUGGEST_TUTOR, f"graded:wrong×{pr.wrong_streak}→weak, encourage, move on",
                            strategy="tutor_handoff", mark_weak=True, next_stage="done",
                            follow_up=Action.NEXT_CONCEPT if not p.is_last_concept else Action.SESSION_COMPLETE)
        return _remediate(p, f"graded:wrong×{pr.wrong_streak}")

    # 7. keep checking understanding
    if p.turns_since_check >= CHECK_EVERY and pr.stage in ("explain", "check"):
        return Decision(Action.CHECK_QUESTION, f"rule:{p.turns_since_check} turns without a check", question_stage="check",
                        next_stage="check")

    # 8. the normal teaching loop
    if pr.stage == "explain":
        return Decision(Action.EXPLAIN, "loop:explain (+key terms)", next_stage="check")
    if pr.stage == "check":
        return Decision(Action.CHECK_QUESTION, "loop:check", question_stage="check", next_stage="check")
    if pr.stage == "apply":
        return Decision(Action.CHECK_QUESTION, "loop:apply", question_stage="apply", next_stage="apply")
    if pr.stage == "recap":
        return _next_concept(p, "loop:recap done")
    return _next_concept(p, "loop:concept done")


def apply_decision(progress: ConceptProgress, d: Decision) -> None:
    """Update the concept's progress after the tutor turn (the session manager calls this)."""
    if d.strategy and d.strategy not in progress.tried:
        progress.tried.append(d.strategy)
    if d.mark_weak:
        progress.status = "weak"
    if d.next_stage:
        progress.stage = d.next_stage

"""Prompt Builder (Phase 2 · Step 10).

Five layers on every turn, then the recent conversation and the student's message:
  1. persona + pedagogy (fixed)            2. language + culture rules
  3. concept content (grounding)           4. student state (mastery, mood, misconception, last result)
  5. the ONE action the policy chose, with its exact instruction

The model returns strict JSON (TutorTurn). It never writes the check question itself and never sees the
answer of a question that is still open — questions come from the verified question bank.
"""
from __future__ import annotations

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel, Field

from modules.professor.core.policy import Action, Decision

PROMPT_VERSION = "teach@1.7"


class TutorTurn(BaseModel):
    speech: str = Field(min_length=1)          # what the professor says (no markdown)
    board: str = ""                            # markdown for the notes panel: steps, tables, terms
    expression: Literal["neutral", "happy", "surprised", "relaxed", "concerned", "thinking"] = "neutral"


PERSONA = """You are "AI Professor", a warm, patient {subject} teacher for a {level} student on NeuralHub.
How you teach: one idea per turn; short, clear sentences (max {max_sentences} in "speech" unless told otherwise);
teach clearly FIRST, test later (the app asks the check questions); build on what the student already knows;
use real biology terms and explain each one. Praise must be earned and specific: only after a correct answer, and
never claim the student "gets it quickly" when they only asked to move on. Never make the student feel stupid.
Never reveal the answer of an open question. Stay on the lesson; if the student goes off-topic, answer in one line
and bring them back. Facts must be correct for the level; if unsure, say so."""

from modules.professor.languages import LANGS as LANGUAGE  # noqa: E402,F401 (kept for imports)

ACTION_INSTRUCTIONS = {
    Action.INTRODUCE: "Greet briefly, give ONE sentence of real-life hook, then TEACH the core idea in 2–3 simple "
                      "sentences (what it is and why it matters). Put the concept name and 2–3 key terms on the board. "
                      "End with something like 'Next, let's see how it works.' Do not quiz the student yet.",
    Action.EXPLAIN: "Teach the concept properly, like a good biology teacher, in up to 8 short sentences, in this order: "
                    "what it is → its parts (name EVERY key term and say its job) → how it works → why it matters. "
                    "Continue from the introduction; do not repeat it. Cover every fact listed under 'Must teach'. Put numbered steps or a small table with the key terms "
                    "(with Urdu meaning) on the board.",
    Action.SIMPLIFY: "Explain the same idea again in much simpler words and a smaller step. Shorter than before.",
    Action.GIVE_EXAMPLE: "Explain using the example given below (adapt it naturally). Connect it back to the concept.",
    Action.CHECK_QUESTION: "In ONE short sentence, say it is time for a quick check (the app displays the question below "
                           "with its options). Do NOT ask any other question, do NOT answer it or hint at the answer.",
    Action.HINT: "The answer was partly right. Say exactly what was right, then give ONE small hint (not the answer). "
                 "A new question follows in the app; do not ask your own.",
    Action.ENCOURAGE: "The student is frustrated. Acknowledge the feeling kindly, say mistakes are part of learning, "
                      "then take a much smaller step as described below. No new question in this turn.",
    Action.SPEED_UP: "The student seems bored. In ONE neutral sentence, move straight to the question shown below. "
                     "No praise, and do not ask any other question.",
    Action.REVIEW_PREREQUISITE: "Revise the earlier concept listed below in 2–3 sentences, then link it to the current concept.",
    Action.RECAP: "Give a one-line summary of the concept and one memory trick (mnemonic). Praise the progress.",
    Action.NEXT_CONCEPT: "Close the current concept in one sentence, then introduce the NEXT concept (given below): "
                         "one sentence of real-life hook and its core idea in 2–3 simple sentences. Do not quiz yet.",
    Action.ANSWER_DOUBT: "The student asked for something. Answer EXACTLY what they asked, even if it is broader than or "
                         "different from the current concept (e.g. 'structure of the eye' = ALL main parts of the eye, "
                         "not only today's topic). Use the course outline below to stay consistent with the course. "
                         "Use as many sentences as the request needs (up to 10). For a structure / overview request, put "
                         "a numbered table on the board: Part | Where it is | Job (with Urdu meaning), and, when useful, "
                         "the pathway as arrows (e.g. light: cornea → pupil → lens → retina → optic nerve). "
                         "Only state facts you are sure of at this level; never invent anatomy; if something is not "
                         "certain, say so. End with ONE short sentence that brings them back to the lesson.",
    Action.SUGGEST_TUTOR: "The student has struggled with this concept several times. Be kind: say it is a tricky one, "
                          "give the key idea once more in ONE simple sentence, say we will revise it next time "
                          "(it will come back in the warm-up), and in ONE short sentence that a NeuralHub tutor can also help "
                          "with it (the student decides; a button below shares their AI report). Then continue.",
    Action.DAY_INTRO: "Start of a new day of the course. Welcome the student to this day (number and title below). "
                      "Using the day's overview from the notes, give the big picture in 3–4 sentences: the theme and "
                      "why it matters. Put today's topics on the board as a numbered plan, in order. End by saying we "
                      "start with the first topic. Do NOT teach the first topic yet.",
    Action.WARM_UP: "Start-of-class warm-up. In one or two sentences: say we will begin with a few quick questions on "
                    "topics from last time (listed below) to refresh them, then introduce the first question below.",
    Action.REVIEW_BLOCK: "You have just taught the topics listed below. Say we will now review them: give a one-line "
                         "recap of each (also as a numbered list on the board), say there will be a few MCQs and then "
                         "short written questions, then introduce the first question shown below in one sentence.",
    Action.SESSION_COMPLETE: "The course part is finished. Congratulate the student, summarise what they learned in 2 lines "
                             "and mention which concepts to revise.",
}

STRATEGY_HINTS = {
    "plain_words": "Use very plain words, no jargon.",
    "everyday_example": "Use the everyday example below.",
    "board_visual": "Draw it on the board: a numbered flow (A → B → C) or a small comparison table.",
    "worked_example": "Walk through one concrete case step by step.",
    "interest_analogy": "Use an analogy from cricket, cooking or daily life in Pakistan.",
    "prerequisite_review": "Revise the earlier concept first.",
    "learner_does_step": "Start the explanation and ask the student to complete the next step themselves.",
    "switch_language": "Explain again in Roman Urdu (or Urdu) even if the student wrote in English.",
}


def build_prompt(
    *,
    pack,
    level: str,
    language: str,
    decision: Decision,
    concept: dict,
    notes: str,
    example: Optional[dict],
    prerequisites: list[dict],
    next_concept: Optional[dict],
    must_teach: Optional[list[str]] = None,
    note: str = "",
    helps: Optional[list[str]] = None,
    outline: Optional[list[dict]] = None,
    diagram: Optional[dict] = None,
    pace: str = "normal",
    mastery: float,
    affect: str,
    misconception: str,
    last_feedback: Optional[dict],
    question: Optional[dict],
    history: list[dict],
    student_message: str,
) -> str:
    style = pack.teaching.style or {}
    persona = PERSONA.format(subject=pack.meta.name, level=level or pack.meta.default_level,
                             max_sentences=style.get("max_sentences_per_turn", 5))
    from modules.professor.languages import instruction

    lang = instruction(language)
    culture = "Use Pakistani everyday analogies (cricket, chai, bazaar, rickshaw, water tank) when they help."

    layers = [
        f"## 1. Who you are\n{persona}\n\nSubject rules:\n{pack.rules}",
        f"## 2. Language & culture\n{lang} \"board\" may be in English. {culture}"
        + ("\nThe student chose a SLOW pace: smaller steps, the simplest words, one extra everyday example, "
           "and check the meaning of every new term." if pace == "slow" else ""),
        "## 3. Concept\n" + json.dumps(
            {"title": concept["title"], "summary": concept["summary"], "key_terms": concept["key_terms"]}, ensure_ascii=False)
        + (f"\nThe student's course notes for this topic (generated syllabus; the student sees them in the side "
           f"panel right now). TEACH FROM THESE NOTES: follow their points and order, use the examples, analogies "
           f"and tables they give first, and never contradict them:\n\"\"\"\n{notes[:3000]}\n\"\"\"" if notes else ""),
        "## 4. Student\n" + json.dumps({
            "mastery_of_this_concept": round(mastery, 2), "mood": affect, "misconception": misconception or None,
            "last_answer": last_feedback,
            **({"what_helps_this_student": helps} if helps else {}),
        }, ensure_ascii=False),
    ]
    act = decision.action
    instr = ACTION_INSTRUCTIONS[act]
    if decision.strategy in STRATEGY_HINTS and act != Action.SUGGEST_TUTOR:
        instr += " " + STRATEGY_HINTS[decision.strategy]
    if decision.follow_up and decision.follow_up in ACTION_INSTRUCTIONS and act == Action.ENCOURAGE:
        instr += " Smaller step: " + ACTION_INSTRUCTIONS[decision.follow_up]
    extra = []
    if example:
        extra.append(f"Example to use: {example['text']}" + (f" (Roman Urdu: {example['roman_ur']})" if example.get("roman_ur") else ""))
    if prerequisites and act in (Action.REVIEW_PREREQUISITE, Action.ENCOURAGE):
        extra.append("Earlier concept(s): " + json.dumps(prerequisites, ensure_ascii=False))
    if next_concept and act == Action.NEXT_CONCEPT:
        extra.append("Next concept: " + json.dumps(next_concept, ensure_ascii=False))
    if note:
        extra.append(note)
    if outline and act == Action.ANSWER_DOUBT:
        extra.append("Course outline (current concept marked *):\n" + "\n".join(
            f"{'*' if o.get('current') else '-'} {o['title']}: {o.get('summary', '')[:160]}" for o in outline))
    if diagram and act == Action.ANSWER_DOUBT:
        extra.append(f"A labeled diagram titled '{diagram['title']}' is shown on the board ABOVE your notes. "
                     "Refer to it ('see the diagram on the board') and walk through its main labels in order.")
        from modules.professor.content.diagrams import seen_text

        if seen_text(diagram):
            extra.append(seen_text(diagram))
    if must_teach and act in (Action.EXPLAIN, Action.SIMPLIFY):
        extra.append("Must teach (the student will be checked on these facts later; teach them, do not quiz):\n"
                     + "\n".join(f"- {f}" for f in must_teach))
    if question:
        extra.append("Question the app will show after your speech (do not answer it, do not ask any other question): "
                     + question["question"])
    if last_feedback and last_feedback.get("verdict"):
        v = last_feedback["verdict"]
        extra.append({
            "correct": "The student's last answer was CORRECT. Start with short, specific praise naming what they got right.",
            "partial": "The student's last answer was PARTLY correct. Say what was right, then what was missing. "
                       "Do not call it correct.",
            "wrong": "The student's last answer was WRONG. Do not praise the answer (no 'great', 'good job'). Kindly give "
                     "the right idea in one sentence, then continue.",
        }.get(v, ""))
    if act not in (Action.CHECK_QUESTION, Action.SPEED_UP, Action.HINT, Action.ANSWER_DOUBT) and not question:
        instr += (" Teach, do not test: do NOT end with a question the student has to answer "
                  "(the app asks check questions separately, when the student is ready).")
    layers.append(f"## 5. Your task this turn: {act.value}\n{instr}" + ("\n" + "\n".join(extra) if extra else ""))

    convo = "\n".join(f"{h['role']}: {h['text'][:400]}" for h in history[-8:]) or "(start of session)"
    return (
        "\n\n".join(layers)
        + f"\n\n## Recent conversation\n{convo}\n\n## Student's latest message\n{student_message or '(none — you start)'}\n\n"
        + 'Return ONLY JSON: {"speech": "...", "board": "markdown or empty", '
          '"expression": "neutral|happy|surprised|relaxed|concerned|thinking"}'
    )


def fallback_turn(decision: Decision, concept: dict, example: Optional[dict], question: Optional[dict]) -> TutorTurn:
    """Used when every model is down, so the lesson continues with the verified material."""
    a = decision.action
    if a in (Action.GIVE_EXAMPLE,) and example:
        return TutorTurn(speech=example["text"], expression="relaxed")
    if a in (Action.CHECK_QUESTION, Action.SPEED_UP, Action.HINT) and question:
        return TutorTurn(speech="Let's check your understanding with a quick question.", expression="neutral")
    if a == Action.SESSION_COMPLETE:
        return TutorTurn(speech="Great work today! That's the end of this part.", expression="happy")
    if a == Action.ANSWER_DOUBT:  # never answer a different question with the current concept's summary
        return TutorTurn(speech="Good question! The AI teacher is busy right now, so I can't answer it properly. "
                                "Please ask again in a minute (or press Next to continue the lesson).",
                         expression="concerned")
    if a == Action.DAY_INTRO:
        return TutorTurn(speech="Welcome to today's lesson! We will go through today's topics one by one — the plan "
                                "is in the side panel. Press Next to start with the first topic.", expression="happy")
    if a == Action.WARM_UP and question:
        return TutorTurn(speech="Welcome back! Let's warm up with a quick question from last time.", expression="happy")
    if a == Action.REVIEW_BLOCK and question:
        return TutorTurn(speech="Let's review what we just learned. First, a quick question.", expression="neutral")
    terms = "\n".join(f"- **{t.get('term')}**: {t.get('meaning')}" for t in concept.get("key_terms") or [])
    summary = (concept.get("summary") or "").strip()
    if summary:  # honest: this is the prepared summary, not a live explanation
        note = "" if a in (Action.INTRODUCE, Action.NEXT_CONCEPT) else (
            "\n\n_(The AI teacher is busy right now, so here is the prepared summary. Try again in a minute.)_")
        return TutorTurn(speech=f"**{concept['title']}**: {summary}{note}", board=terms, expression="neutral")
    return TutorTurn(  # no AI and no prepared material: say so honestly instead of showing an empty lesson
        speech=(f"Today's topic is **{concept['title']}**. The AI models are not answering right now "
                "(busy or out of free quota), so I can't explain it properly yet. Please try again in a minute."),
        board=terms, expression="concerned")


_SENT = re.compile(r"[^.!?]*[.!?]+[\"')\]]*\s*|[^.!?]+$")
TEACHING_ACTIONS = {Action.DAY_INTRO, Action.INTRODUCE, Action.REVIEW_BLOCK, Action.WARM_UP, Action.EXPLAIN, Action.SIMPLIFY, Action.GIVE_EXAMPLE, Action.NEXT_CONCEPT,
                    Action.RECAP, Action.REVIEW_PREREQUISITE}


def clean_speech(speech: str, action: Action, has_card: bool) -> str:
    """Safety net for what the prompt asks: with a question card on screen the professor must not ask a DIFFERENT
    question out loud; when teaching it should not end on a quiz question (the app checks separately)."""
    text = (speech or "").strip()
    if not text:
        return text
    parts = [p for p in _SENT.findall(text) if p.strip()]
    if has_card:
        kept = [p for p in parts if not p.rstrip(" \"')]").endswith("?")]
        return "".join(kept).strip() or "Quick check — answer the question below."
    if action in TEACHING_ACTIONS and len(parts) > 1 and parts[-1].rstrip(" \"')]").endswith("?"):
        return "".join(parts[:-1]).strip()
    return text

"""Lesson flow in blocks (v61): how a good teacher runs a class.

    teach topic 1 → teach topic 2 → teach topic 3 → review all three → MCQs (one per topic) → short written
    questions (one per topic) → next block of topics

A day's topics are split into blocks of at most 3 (balanced: 4 → 2+2, 5 → 3+2). A wrong answer in the review
re-teaches that topic in a new way and asks it again (3 wrong in a row → marked weak, move on).
Pure functions only; the session manager keeps the state.
"""
from __future__ import annotations

import math

BLOCK_MAX = 3
MCQ_TYPES = ("mcq", "match", "order")
WRITTEN_TYPES = ("short_why", "compare", "apply")


def make_blocks(days: list[int], size: int = BLOCK_MAX) -> list[list[int]]:
    """Concept indexes grouped by day, then cut into balanced blocks of at most `size`."""
    out, i = [], 0
    while i < len(days):
        j = i
        while j < len(days) and days[j] == days[i]:
            j += 1
        n = j - i
        k = math.ceil(n / size)
        base, extra = divmod(n, k)
        start = i
        for b in range(k):
            ln = base + (1 if b < extra else 0)
            out.append(list(range(start, start + ln)))
            start += ln
        i = j
    return out


def block_of(blocks: list[list[int]], index: int) -> tuple[int, list[int]]:
    for bi, b in enumerate(blocks):
        if index in b:
            return bi, b
    return len(blocks) - 1, blocks[-1] if blocks else []


def review_queue(concept_ids: list[str], block: list[int]) -> list[dict]:
    """All MCQs first (one per topic, in teaching order), then the written questions."""
    return ([{"cid": concept_ids[i], "kind": "mcq"} for i in block]
            + [{"cid": concept_ids[i], "kind": "written"} for i in block])


def types_for(kind: str) -> tuple[str, ...]:
    return MCQ_TYPES if kind == "mcq" else WRITTEN_TYPES


WARMUP_MAX = 3


def warmup_targets(concept_ids: list[str], progress: dict, before_index: int, mastered: float,
                   limit: int = WARMUP_MAX) -> list[str]:
    """Topics studied earlier that are still weak (lowest mastery first): asked again at the start of a class."""
    cands = [cid for cid in concept_ids[:before_index + 1]
             if progress[cid].get("attempts", 0) > 0 and progress[cid].get("status") != "mastered"
             and progress[cid].get("mastery", 0) < mastered]
    cands.sort(key=lambda c: (progress[c].get("status") != "weak", progress[c].get("mastery", 0)))
    return cands[:limit]

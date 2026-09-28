"""Stage 1 — objective metrics.

Runs on the whole formatted paper, before slicing (R1.1). Stdlib only, no
LLM, so it is importable and testable with no network (N1). Output is
report-only: it is merged into `comparison.yaml` at Stage 4 and never shown
to the Stage 3 prompt (ADR-013).
"""

from __future__ import annotations

import re

_WORD = re.compile(r"\b\w+\b")
_SENTENCE_END = re.compile(r"[.!?]+(?=\s|$)")


def compute_metrics(md_a: str, md_b: str) -> dict:
    """Compute paper-level, LLM-free metrics for a pair of formatted papers.

    In: the Stage 0 output for paper A and paper B.
    Out: a dict with `word_count_a`, `word_count_b`, `sentence_count_a`,
    `sentence_count_b`, and `jaccard_similarity` (over lowercased word sets,
    whole paper).
    Belongs to: Stage 1 (objective metrics).
    """
    return {
        "word_count_a": _word_count(md_a),
        "word_count_b": _word_count(md_b),
        "sentence_count_a": _sentence_count(md_a),
        "sentence_count_b": _sentence_count(md_b),
        "jaccard_similarity": _jaccard(md_a, md_b),
    }


def _word_count(text: str) -> int:
    return len(_WORD.findall(text))


def _sentence_count(text: str) -> int:
    return len(_SENTENCE_END.findall(text))


def _word_set(text: str) -> set[str]:
    return {word.lower() for word in _WORD.findall(text)}


def _jaccard(md_a: str, md_b: str) -> float:
    words_a = _word_set(md_a)
    words_b = _word_set(md_b)
    if not words_a and not words_b:
        return 1.0
    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return intersection / union

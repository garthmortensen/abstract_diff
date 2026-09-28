"""Stage 4 — assemble and validate comparison.

Merges each paper's summaries and grounded assertion tree, Stage 1's
metrics, and Stage 3's comparison into one shape, and validates that shape
with a single Pydantic model (R4.2). A `grounded: false` flag is not a shape
violation (R4.3) — Pydantic only checks structure, grounding already ran at
Stage 2c (ADR-008). The per-matched-pair quote similarity (R1.4) is computed
here with stdlib `difflib`, since this is the first point where both quotes
in a matched pair are available together.
"""

from __future__ import annotations

import difflib
from typing import Literal

from pydantic import BaseModel

AssertionType = Literal[
    "research_question",
    "hypothesis",
    "method",
    "data",
    "assumption",
    "limitation",
    "finding",
    "conclusion",
    "claim",
]


class Assertion(BaseModel):
    type: AssertionType
    block_index: int
    quote: str
    grounded: bool
    index_corrected: bool


class Section(BaseModel):
    header: str
    summary: str
    assertions: list[Assertion]


class ComparisonRecord(BaseModel):
    evidence: list[str]
    interpretation: str
    quote_similarity: float | None = None


class Metrics(BaseModel):
    word_count_a: int
    word_count_b: int
    sentence_count_a: int
    sentence_count_b: int
    jaccard_similarity: float


class Comparison(BaseModel):
    paper_a_sections: list[Section]
    paper_b_sections: list[Section]
    matched: list[ComparisonRecord]
    a_only: list[ComparisonRecord]
    b_only: list[ComparisonRecord]
    metrics: Metrics


def assemble(
    paper_a_summary: dict,
    paper_a_assertions: dict,
    paper_b_summary: dict,
    paper_b_assertions: dict,
    metrics: dict,
    stage3_result: dict,
) -> Comparison:
    """Merge every stage's output into one validated `Comparison`.

    In: paper A and paper B's `{header: summary}` dicts, their grounded
    `{header: {"assertions": [...]}}` trees, Stage 1's metrics dict, and
    Stage 3's `{matched, a_only, b_only}` result.
    Out: a validated `Comparison`. Raises `pydantic.ValidationError` if the
    shape is wrong.
    Belongs to: Stage 4 (assemble and validate comparison).
    """
    return Comparison(
        paper_a_sections=_build_sections(paper_a_summary, paper_a_assertions),
        paper_b_sections=_build_sections(paper_b_summary, paper_b_assertions),
        matched=[_build_record(record) for record in stage3_result.get("matched", [])],
        a_only=[_build_record(record) for record in stage3_result.get("a_only", [])],
        b_only=[_build_record(record) for record in stage3_result.get("b_only", [])],
        metrics=Metrics(**metrics),
    )


def _build_sections(summaries: dict, assertions: dict) -> list[Section]:
    sections = []
    for header, body in assertions.items():
        sections.append(
            Section(
                header=header,
                summary=summaries.get(header, ""),
                assertions=[_normalize_assertion(raw) for raw in body["assertions"]],
            )
        )
    return sections


def _normalize_assertion(raw: dict) -> Assertion:
    path_key = next(key for key in raw if key.startswith("$.blocks["))
    index = int(path_key[len("$.blocks[") : -1])
    return Assertion(
        type=raw["type"],
        block_index=index,
        quote=raw[path_key],
        grounded=raw["grounded"],
        index_corrected=raw["index_corrected"],
    )


def _build_record(raw: dict) -> ComparisonRecord:
    evidence = raw["evidence"]
    similarity = _quote_similarity(evidence[0], evidence[1]) if len(evidence) == 2 else None
    return ComparisonRecord(
        evidence=evidence, interpretation=raw["interpretation"], quote_similarity=similarity
    )


def _quote_similarity(quote_a: str, quote_b: str) -> float:
    return difflib.SequenceMatcher(None, quote_a, quote_b).ratio()

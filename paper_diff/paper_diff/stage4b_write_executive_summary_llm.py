"""Stage 4b — write executive summary.

One LLM call, fed the validated Stage 4 comparison (the three record lists
plus both papers' section summaries), producing a pyramid-principle brief:
one governing thought, 3-4 MECE pillars, verbatim evidence under each.
Paper A is the champion (incumbent), Paper B the challenger (ADR-018).

Every evidence quote the model returns is checked deterministically against
the quotes it was given and flagged `grounded: false` if it cannot be found,
mirroring Stage 2c's grounding (N2).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from paper_diff import llm_client_with_cache
from paper_diff.stage4_assemble_and_validate_comparison import Comparison, ComparisonRecord

_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "stage4b_write_executive_summary_llm.md"
)
_MAX_TOKENS = 8192
_WHITESPACE_RE = re.compile(r"\s+")


class Evidence(BaseModel):
    source: Literal["challenger", "champion", "both"]
    quote: str
    why_it_matters: str
    grounded: bool = True


class Pillar(BaseModel):
    claim: str
    evidence: list[Evidence] = Field(min_length=1)


class Counts(BaseModel):
    challenger_only: int
    champion_only: int
    shared: int


class ExecutiveSummary(BaseModel):
    headline: str
    governing_thought: str
    recommendation: str
    pillars: list[Pillar] = Field(min_length=3, max_length=5)
    challenger_brings: list[str] = Field(min_length=1)
    challenger_lacks: list[str]
    shared_ground: str
    who_should_care: str
    counts: Counts


class EvidenceReply(BaseModel):
    source: Literal["challenger", "champion", "both"]
    quote: str
    why_it_matters: str


class PillarReply(BaseModel):
    claim: str
    evidence: list[EvidenceReply]


class ExecutiveSummaryReply(BaseModel):
    """What the model writes: `ExecutiveSummary` minus the fields Python fills in.

    List-length rules live on `ExecutiveSummary`, which validates the result;
    structured outputs can't enforce them.
    """

    headline: str
    governing_thought: str
    recommendation: str
    pillars: list[PillarReply]
    challenger_brings: list[str]
    challenger_lacks: list[str]
    shared_ground: str
    who_should_care: str


def write_executive_summary(comparison: Comparison) -> ExecutiveSummary:
    """Write the answer-first brief for a reader who will not open either paper.

    In: the validated `Comparison` from Stage 4.
    Out: a validated `ExecutiveSummary` whose evidence quotes are each marked
    `grounded` (found verbatim among the comparison's quotes) or not.
    Belongs to: Stage 4b (write executive summary).
    """
    input_text = _format_input(comparison)
    reply = llm_client_with_cache.ask(
        _PROMPT_FILE, input_text, max_tokens=_MAX_TOKENS, schema=ExecutiveSummaryReply
    )
    parsed = reply.model_dump()
    parsed["counts"] = {
        "challenger_only": len(comparison.b_only),
        "champion_only": len(comparison.a_only),
        "shared": len(comparison.matched),
    }
    _ground_evidence(parsed, _quote_pool(comparison))
    return ExecutiveSummary(**parsed)


def _format_input(comparison: Comparison) -> str:
    payload = {
        "champion_section_summaries": {s.header: s.summary for s in comparison.paper_a_sections},
        "challenger_section_summaries": {s.header: s.summary for s in comparison.paper_b_sections},
        "challenger_only": [_bare_record(r) for r in comparison.b_only],
        "champion_only": [_bare_record(r) for r in comparison.a_only],
        "shared": [_bare_record(r) for r in comparison.matched],
    }
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


def _bare_record(record: ComparisonRecord) -> dict:
    return {"evidence": record.evidence, "interpretation": record.interpretation}


def _quote_pool(comparison: Comparison) -> list[str]:
    pool = []
    for record in comparison.matched + comparison.a_only + comparison.b_only:
        pool.extend(_normalize(quote) for quote in record.evidence)
    return pool


def _ground_evidence(parsed: dict, pool: list[str]) -> None:
    for pillar in parsed.get("pillars", []):
        for item in pillar.get("evidence", []):
            needle = _normalize(item.get("quote", ""))
            item["grounded"] = bool(needle) and any(needle in quote for quote in pool)


def _normalize(text: str) -> str:
    return _WHITESPACE_RE.sub(" ", text).strip().lower()

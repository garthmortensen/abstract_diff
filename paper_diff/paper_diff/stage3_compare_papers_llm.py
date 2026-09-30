"""Stage 3 — compare and interpret.

One LLM call, fed exactly the two papers' nested assertion trees (grounding
flags included) and their two `summary.yaml` files — no metrics (ADR-013).
Falls back to a two-round, section-aligned comparison if either paper has
more than roughly 100 assertions (R3.3, ADR-012).

In two-round mode, each aligned section pair is split into chunks small
enough for one call, so no section is too big; sections the alignment left
unpaired are still compared, against an empty side, so their assertions
land in `a_only` / `b_only` instead of vanishing.
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel

from paper_diff import llm_client_with_cache

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "stage3_compare_papers_llm.md"
_ALIGN_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "stage3_align_sections_llm.md"
)
_ASSERTION_LIMIT = 100
_CHUNK_SIZE = _ASSERTION_LIMIT // 2


class Record(BaseModel):
    evidence: list[str]
    interpretation: str


class ComparisonReply(BaseModel):
    matched: list[Record]
    a_only: list[Record]
    b_only: list[Record]


class AlignmentReply(BaseModel):
    aligned_sections: list[list[str]]


def compare_papers(tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict) -> dict:
    """Match and interpret the assertions of two papers.

    In: each paper's `{header: {"assertions": [...]}}` tree (grounded) and
    each paper's `{header: summary}` dict.
    Out: a dict with `matched`, `a_only`, `b_only` lists, each record holding
    `evidence` (the quotes) and `interpretation` (the model's reading).
    Belongs to: Stage 3 (compare papers).
    """
    if _assertion_count(tree_a) > _ASSERTION_LIMIT or _assertion_count(tree_b) > _ASSERTION_LIMIT:
        return _compare_in_two_rounds(tree_a, tree_b, summary_a, summary_b)
    return _compare_once(tree_a, tree_b, summary_a, summary_b)


def _compare_once(tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict) -> dict:
    """One comparison call. Never checks the limit, never recurses."""
    input_text = _format_input(tree_a, tree_b, summary_a, summary_b)
    reply = llm_client_with_cache.ask(
        _PROMPT_FILE, input_text, max_tokens=_max_tokens_for(input_text), schema=ComparisonReply
    )
    return reply.model_dump()


def _assertion_count(tree: dict) -> int:
    return sum(len(section["assertions"]) for section in tree.values())


_TOKEN_CEILING = 64_000


def _max_tokens_for(input_text: str) -> int:
    """A token budget generous enough for a full matched/a_only/b_only listing.

    The output echoes most of the input's quotes back plus interpretation
    sentences, so it scales with the input; two characters per token errs
    generous, and the client's retry grows it further if needed.
    """
    estimated_tokens = len(input_text) // 2 + 1500
    return min(max(8192, estimated_tokens), _TOKEN_CEILING)


def _format_input(tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict) -> str:
    payload = {
        "paper_a_summaries": summary_a,
        "paper_a_assertions": tree_a,
        "paper_b_summaries": summary_b,
        "paper_b_assertions": tree_b,
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _compare_in_two_rounds(tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict) -> dict:
    pairs = _aligned_pairs(tree_a, tree_b, summary_a, summary_b)
    paired_a = {header_a for header_a, _ in pairs}
    paired_b = {header_b for _, header_b in pairs}
    jobs = [(header_a, header_b) for header_a, header_b in pairs]
    jobs += [(header_a, None) for header_a in tree_a if header_a not in paired_a]
    jobs += [(None, header_b) for header_b in tree_b if header_b not in paired_b]

    cells = []
    for header_a, header_b in jobs:
        side_a = _side(tree_a, summary_a, header_a)
        side_b = _side(tree_b, summary_b, header_b)
        cells.extend(_compare_pair(side_a, side_b))
    return _merge_cells(cells)


def _aligned_pairs(
    tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict
) -> list[tuple[str, str]]:
    """Section pairs from the alignment call, keeping only headers that exist."""
    align_input = yaml.safe_dump({"align": summary_a, "to": summary_b})
    reply = llm_client_with_cache.ask(
        _ALIGN_PROMPT_FILE,
        align_input,
        max_tokens=_max_tokens_for(align_input),
        schema=AlignmentReply,
    )
    return [
        (pair[0], pair[1])
        for pair in reply.aligned_sections
        if len(pair) == 2 and pair[0] in tree_a and pair[1] in tree_b
    ]


def _side(tree: dict, summary: dict, header: str | None) -> tuple[str | None, list, dict]:
    if header is None:
        return None, [], {}
    return header, tree[header]["assertions"], {header: summary.get(header)}


def _compare_pair(side_a: tuple, side_b: tuple) -> list[dict]:
    """Compare two sections chunk by chunk, so each call stays under the limit.

    Every A chunk meets every B chunk, so no possible match is missed. A
    pair already under the limit is a single call, the same as before.
    """
    header_a, assertions_a, summaries_a = side_a
    header_b, assertions_b, summaries_b = side_b
    return [
        _compare_once(
            _subtree(header_a, chunk_a), _subtree(header_b, chunk_b), summaries_a, summaries_b
        )
        for chunk_a in _chunks(assertions_a)
        for chunk_b in _chunks(assertions_b)
    ]


def _chunks(assertions: list) -> list[list]:
    if not assertions:
        return [[]]
    return [assertions[i : i + _CHUNK_SIZE] for i in range(0, len(assertions), _CHUNK_SIZE)]


def _subtree(header: str | None, assertions: list) -> dict:
    return {} if header is None else {header: {"assertions": assertions}}


def _merge_cells(cells: list[dict]) -> dict:
    """Combine chunk results so each quote lands in exactly one outcome.

    Matched records are de-duplicated by their quote pair. A quote matched
    in any cell is dropped from its one-sided list everywhere; otherwise it
    keeps one one-sided record (the first cell's).
    """
    matched = _unique(record for cell in cells for record in cell["matched"])
    matched_a = {record["evidence"][0] for record in matched if record["evidence"]}
    matched_b = {record["evidence"][-1] for record in matched if record["evidence"]}
    a_only = _unique(r for cell in cells for r in cell["a_only"] if not _in(r, matched_a))
    b_only = _unique(r for cell in cells for r in cell["b_only"] if not _in(r, matched_b))
    return {"matched": matched, "a_only": a_only, "b_only": b_only}


def _in(record: dict, quotes: set[str]) -> bool:
    return bool(record["evidence"]) and record["evidence"][0] in quotes


def _unique(records) -> list[dict]:
    seen: set[tuple[str, ...]] = set()
    kept = []
    for record in records:
        key = tuple(record["evidence"])
        if key not in seen:
            seen.add(key)
            kept.append(record)
    return kept

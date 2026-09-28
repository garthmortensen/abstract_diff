"""Stage 3 — compare and interpret.

One LLM call, fed exactly the two papers' nested assertion trees (grounding
flags included) and their two `summary.yaml` files — no metrics (ADR-013).
Falls back to a two-round, section-aligned comparison if either paper has
more than roughly 100 assertions (R3.3, ADR-012).
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from paper_diff import llm_client_with_cache

_PROMPT_FILE = Path(__file__).resolve().parent.parent / "prompts" / "stage3_compare_papers_llm.md"
_ALIGN_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "stage3_align_sections_llm.md"
)
_ASSERTION_LIMIT = 100


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
    input_text = _format_input(tree_a, tree_b, summary_a, summary_b)
    max_tokens = _max_tokens_for(input_text)
    response = llm_client_with_cache.ask(_PROMPT_FILE, input_text, max_tokens=max_tokens)
    return json.loads(_strip_fences(response))


def _assertion_count(tree: dict) -> int:
    return sum(len(section["assertions"]) for section in tree.values())


_NONSTREAMING_TOKEN_CEILING = 16_000


def _max_tokens_for(input_text: str) -> int:
    """A token budget generous enough for a full matched/a_only/b_only listing.

    The output echoes most of the input's quotes back plus interpretation
    sentences, so it scales with the input; see Stage 0's version of this
    estimate for why it errs generous.
    """
    estimated_tokens = len(input_text) // 2 + 1500
    return min(max(8192, estimated_tokens), _NONSTREAMING_TOKEN_CEILING)


def _format_input(tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict) -> str:
    payload = {
        "paper_a_summaries": summary_a,
        "paper_a_assertions": tree_a,
        "paper_b_summaries": summary_b,
        "paper_b_assertions": tree_b,
    }
    return yaml.safe_dump(payload, sort_keys=False)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if not stripped.startswith("```"):
        return stripped
    lines = stripped.splitlines()[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines)


def _compare_in_two_rounds(tree_a: dict, tree_b: dict, summary_a: dict, summary_b: dict) -> dict:
    align_input = yaml.safe_dump({"align": summary_a, "to": summary_b})
    align_response = llm_client_with_cache.ask(
        _ALIGN_PROMPT_FILE, align_input, max_tokens=_max_tokens_for(align_input)
    )
    alignment = json.loads(_strip_fences(align_response))

    matched, a_only, b_only = [], [], []
    for header_a, header_b in alignment.get("aligned_sections", []):
        section_a = {header_a: tree_a.get(header_a, {"assertions": []})}
        section_b = {header_b: tree_b.get(header_b, {"assertions": []})}
        summaries_a = {header_a: summary_a.get(header_a)}
        summaries_b = {header_b: summary_b.get(header_b)}
        partial = compare_papers(section_a, section_b, summaries_a, summaries_b)
        matched.extend(partial.get("matched", []))
        a_only.extend(partial.get("a_only", []))
        b_only.extend(partial.get("b_only", []))
    return {"matched": matched, "a_only": a_only, "b_only": b_only}

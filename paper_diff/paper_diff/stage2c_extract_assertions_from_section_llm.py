"""Stage 2c (extract) — extract assertions from section.

One LLM call per section (R2c.2). Given the section text and its indexed
block list, asks for a list of typed assertions, each naming the block it
was quoted from. The reply is structured output, so quotes containing
apostrophes, LaTeX backslashes, or tables arrive exactly as written. Python
then builds the document rooted at the section header, with each quote
under a section-relative `$.blocks[i]` path, never paper-relative (ADR-006).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from paper_diff import llm_client_with_cache
from paper_diff.stage2a_slice_paper_into_sections import Section

_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "stage2c_extract_assertions_from_section_llm.md"
)

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


class ExtractedAssertion(BaseModel):
    type: AssertionType
    block: int
    quote: str


class SectionAssertions(BaseModel):
    assertions: list[ExtractedAssertion]


def extract_assertions(section: Section, blocks: list[str]) -> dict:
    """Extract typed, quoted assertions from one section.

    In: the `Section` being processed, and its `blocks` from
    `index_section_into_blocks.index_blocks`.
    Out: a dict `{section.header: {"assertions": [...]}}`, where each
    assertion is `{"type": ..., "$.blocks[i]": "verbatim quote"}`.
    Belongs to: Stage 2c, extraction step (extract_assertions_from_section).
    """
    input_text = _format_input(section, blocks)
    reply = llm_client_with_cache.ask(
        _PROMPT_FILE, input_text, max_tokens=_max_tokens_for(input_text), schema=SectionAssertions
    )
    assertions = [{"type": a.type, f"$.blocks[{a.block}]": a.quote} for a in reply.assertions]
    return {section.header: {"assertions": assertions}}


def _format_input(section: Section, blocks: list[str]) -> str:
    numbered_blocks = "\n\n".join(f"blocks[{i}]: {block}" for i, block in enumerate(blocks))
    return f"Section header: {section.header}\n\n{numbered_blocks}"


_TOKEN_CEILING = 64_000


def _max_tokens_for(input_text: str) -> int:
    """A token budget generous enough for this section's full assertion list.

    In the worst case, every block is quoted almost in full, so the output
    can approach the size of the input. Two characters per token errs
    generous, because truncation is worse than a larger budget (you pay for
    tokens written, not budgeted). The client's retry grows it further.
    """
    estimated_tokens = len(input_text) // 2 + 1500
    return min(max(8192, estimated_tokens), _TOKEN_CEILING)

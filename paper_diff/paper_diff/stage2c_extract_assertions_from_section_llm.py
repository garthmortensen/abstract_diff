"""Stage 2c (extract) — extract assertions from section.

One LLM call per section (R2c.2). Given the section text and its indexed
block list, asks for a YAML document rooted at the section header containing
a list of typed assertions, each pointing at the block it was quoted from
with a `$.blocks[i]` path. Paths are section-relative, never paper-relative
(ADR-006).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from paper_diff import llm_client_with_cache
from paper_diff.stage2a_slice_paper_into_sections import Section

_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent
    / "prompts"
    / "stage2c_extract_assertions_from_section_llm.md"
)


def extract_assertions(section: Section, blocks: list[str]) -> dict:
    """Extract typed, quoted assertions from one section.

    In: the `Section` being processed, and its `blocks` from
    `index_section_into_blocks.index_blocks`.
    Out: a dict `{section.header: {"assertions": [...]}}`, where each
    assertion is `{"type": ..., "$.blocks[i]": "verbatim quote"}`.
    Belongs to: Stage 2c, extraction step (extract_assertions_from_section).
    """
    input_text = _format_input(section, blocks)
    max_tokens = _max_tokens_for(input_text)
    response = llm_client_with_cache.ask(_PROMPT_FILE, input_text, max_tokens=max_tokens)
    return yaml.safe_load(_strip_fences(response))


def _format_input(section: Section, blocks: list[str]) -> str:
    numbered_blocks = "\n\n".join(f"blocks[{i}]: {block}" for i, block in enumerate(blocks))
    return f"Section header: {section.header}\n\n{numbered_blocks}"


_NONSTREAMING_TOKEN_CEILING = 16_000


def _max_tokens_for(input_text: str) -> int:
    """A token budget generous enough for this section's full assertion list.

    In the worst case, every block is quoted almost in full, so the YAML
    output can approach the size of the input; the estimate errs generous
    for the same reason as Stage 0's (see that module).
    """
    estimated_tokens = len(input_text) // 2 + 1500
    return min(max(8192, estimated_tokens), _NONSTREAMING_TOKEN_CEILING)


def _strip_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        lines = lines[1:] if lines[0].startswith("```") else lines
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        return "\n".join(lines)
    return stripped

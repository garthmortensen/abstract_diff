"""Stage 2c (index) — index section into blocks.

Deterministic pre-step for assertion extraction (ADR-007). Splits a
section's markdown on blank lines into a flat, ordered, untyped list of
blocks. A block may be a paragraph, a table, an equation, or a list; none of
that is distinguished here, so the indexer stays trivial.
"""

from __future__ import annotations

import re

_BLANK_LINE_RUN = re.compile(r"\n\s*\n")


def index_blocks(section_md: str) -> list[str]:
    """Split a section's markdown into an ordered list of blocks.

    In: one section's raw markdown text (including its header line).
    Out: `blocks[0..n]`, each block's text stripped of leading/trailing
    whitespace, blank blocks discarded.
    Belongs to: Stage 2c, indexing step (index_section_into_blocks).
    """
    raw_blocks = _BLANK_LINE_RUN.split(section_md.strip())
    return [block.strip() for block in raw_blocks if block.strip()]

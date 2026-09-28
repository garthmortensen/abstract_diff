"""Stage 0 — format markdown.

Runs on every input paper, unconditionally (ADR-001). Adds markdown headers
where none exist and leaves everything else byte-for-byte the same. The
deterministic post-check in this module (`check_body_unchanged`) is what
turns "the prompt promises not to reword" into something that is actually
verified (ADR-015).
"""

from __future__ import annotations

import re
from pathlib import Path

from paper_diff import llm_client_with_cache

_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "stage0_format_markdown_headers_llm.md"
)
_HEADER_MARKER = re.compile(r"^#{1,6}\s", re.MULTILINE)
_WHITESPACE_RUN = re.compile(r"\s+")


def format_paper(raw_md: str) -> str:
    """Add markdown headers to a paper that may or may not already have them.

    In: the raw markdown text of one paper.
    Out: the same text with headers added where none existed. Verified
    against `raw_md` with `check_body_unchanged` before being returned.
    Belongs to: Stage 0 (format markdown).
    """
    formatted = llm_client_with_cache.ask(_PROMPT_FILE, raw_md, max_tokens=_max_tokens_for(raw_md))
    check_body_unchanged(raw_md, formatted)
    return formatted


_NONSTREAMING_TOKEN_CEILING = 16_000


def _max_tokens_for(raw_md: str) -> int:
    """A token budget generous enough to echo back the whole paper.

    Two characters per token is a conservative estimate for text this dense
    with numbers, citations, and equations — plain English usually tokenizes
    closer to 4 characters per token, but this prompt's failure mode
    (silent truncation) is worse than its success mode (a slightly larger
    request), so the estimate errs generous. Capped below the SDK's
    ~10-minute non-streaming request ceiling (around 21,000 tokens) — a paper
    that needs more than this would need a streaming call instead, which is
    out of scope for these fixtures.
    """
    estimated_tokens = len(raw_md) // 2 + 1500
    return min(max(8192, estimated_tokens), _NONSTREAMING_TOKEN_CEILING)


def check_body_unchanged(raw_md: str, formatted_md: str) -> None:
    """Fail loudly if Stage 0 changed anything besides adding header markers.

    In: the raw input and the formatted output for the same paper.
    Out: nothing, on success. Raises `ValueError` if the header-stripped,
    whitespace-normalised bodies differ.
    Belongs to: Stage 0's post-check (R0.3, ADR-015).
    """
    raw_body = _strip_headers(raw_md)
    formatted_body = _strip_headers(formatted_md)
    if raw_body != formatted_body:
        raise ValueError(
            "Stage 0 changed body text: header-stripped input and output differ"
        )


def _strip_headers(md: str) -> str:
    """Remove header markers (`# ` through `###### `) but keep header text.

    A line's header *marker* is Stage 0's to add or remove; the text after it
    is body content like any other line, so removing only the marker (not
    the whole line) is what makes a paper with no headers comparable to its
    formatted, header-added output.
    """
    without_markers = _HEADER_MARKER.sub("", md)
    return _WHITESPACE_RUN.sub(" ", without_markers).strip()

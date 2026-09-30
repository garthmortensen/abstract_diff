"""Stage 0 — format markdown.

Runs on every input paper, unconditionally (ADR-001). Adds markdown headers
where none exist and leaves everything else byte-for-byte the same.

The model never retypes the paper. It reads the paper with numbered lines
and returns only which lines are headings and at what level; Python applies
those markers. That keeps the reply a few hundred tokens whatever the
paper's size, and makes body drift impossible. The deterministic post-check
(`check_body_unchanged`) still runs as a safety net against bugs in the
applying code (ADR-015).
"""

from __future__ import annotations

import re
from pathlib import Path

from pydantic import BaseModel

from paper_diff import llm_client_with_cache

_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "stage0_format_markdown_headers_llm.md"
)
_HEADER_MARKER = re.compile(r"^#{1,6}\s", re.MULTILINE)
_HEADER_LINE = re.compile(r"^(#{1,6}) (\S.*)$")
_WHITESPACE_RUN = re.compile(r"\s+")
_MAX_TOKENS = 8192


class HeaderInsertion(BaseModel):
    line: int
    header: str


class HeaderInsertions(BaseModel):
    insertions: list[HeaderInsertion]


def format_paper(raw_md: str) -> str:
    """Add markdown headers to a paper that may or may not already have them.

    In: the raw markdown text of one paper (a copy; this never writes files).
    Out: the same text with header markers added to heading lines that
    lacked them. Verified against `raw_md` with `check_body_unchanged`
    before being returned.
    Belongs to: Stage 0 (format markdown).
    """
    reply = llm_client_with_cache.ask(
        _PROMPT_FILE, number_lines(raw_md), max_tokens=_MAX_TOKENS, schema=HeaderInsertions
    )
    formatted = apply_insertions(raw_md, reply.insertions)
    check_body_unchanged(raw_md, formatted)
    return formatted


def number_lines(md: str) -> str:
    """Prefix every line with its 1-based number, as `12: text`."""
    return "\n".join(f"{n}: {line}" for n, line in enumerate(md.split("\n"), start=1))


def apply_insertions(raw_md: str, insertions: list[HeaderInsertion]) -> str:
    """Turn each named line into a header, after validating the whole list.

    In: the raw text and the model's `insertions`.
    Out: the text with those lines replaced by their headers. Raises
    `ValueError` for a line number out of range or out of order, a header
    that isn't 1-6 `#` and a space, a header whose text differs from its
    line, or a line that is already a header.
    """
    lines = raw_md.split("\n")
    _validate(lines, insertions)
    for insertion in reversed(insertions):
        lines[insertion.line - 1] = insertion.header
    return "\n".join(lines)


def _validate(lines: list[str], insertions: list[HeaderInsertion]) -> None:
    previous = 0
    for insertion in insertions:
        if not previous < insertion.line <= len(lines):
            raise ValueError(f"Stage 0 header line {insertion.line} is out of range or order")
        previous = insertion.line
        _validate_header(lines[insertion.line - 1], insertion)


def _validate_header(line: str, insertion: HeaderInsertion) -> None:
    match = _HEADER_LINE.match(insertion.header)
    if match is None:
        raise ValueError(f"Stage 0 header {insertion.header!r} is not a markdown header")
    if _HEADER_MARKER.match(line):
        raise ValueError(f"Stage 0 tried to change existing header on line {insertion.line}")
    if match.group(2).strip() != line.strip():
        raise ValueError(f"Stage 0 header text differs from line {insertion.line}")


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
        raise ValueError("Stage 0 changed body text: header-stripped input and output differ")


def _strip_headers(md: str) -> str:
    """Remove header markers (`# ` through `###### `) but keep header text.

    A line's header *marker* is Stage 0's to add or remove; the text after it
    is body content like any other line, so removing only the marker (not
    the whole line) is what makes a paper with no headers comparable to its
    formatted, header-added output.
    """
    without_markers = _HEADER_MARKER.sub("", md)
    return _WHITESPACE_RUN.sub(" ", without_markers).strip()

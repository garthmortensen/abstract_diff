"""Stage 2a — slice paper into sections.

Runs per paper, independently, with no LLM (ADR-002). Picks the shallowest
header level with at least 5 headers (or the deepest level present, if none
reaches 5), cuts the paper into one section per header at that level, and
recursively re-cuts any section that is still too big (ADR-004, ADR-005).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$")


@dataclass
class Section:
    """One slice of a paper: a header, its nesting level, and its body."""

    header: str
    level: int
    content: str


def slice_paper(md: str, word_threshold: int = 800) -> list[Section]:
    """Cut a formatted paper into sections.

    In: the Stage 0 output for one paper, and the word-count threshold above
    which an oversized section gets recursively re-cut on its sub-headers.
    Out: a flat, ordered list of leaf `Section` objects, each under the
    threshold or with no sub-headers left to cut on. Includes a synthetic
    "Front Matter" section when there is structured content before the first
    chosen-level header (ADR-003).
    Belongs to: Stage 2a (slice paper into sections).
    """
    lines = md.splitlines()
    counts = _count_headers_by_level(lines)
    level = _pick_level(counts)
    front_matter = _front_matter_section(lines, level)
    top_sections = _cut_at_level(lines, level)
    ordered = ([front_matter] if front_matter else []) + top_sections
    leaves: list[Section] = []
    for section in ordered:
        leaves.extend(_recursive_recut(section, word_threshold))
    return leaves


def _header_level(line: str) -> int | None:
    match = _HEADER_RE.match(line)
    return len(match.group(1)) if match else None


def _count_headers_by_level(lines: list[str]) -> dict[int, int]:
    counts: dict[int, int] = {}
    for line in lines:
        level = _header_level(line)
        if level is not None:
            counts[level] = counts.get(level, 0) + 1
    return counts


def _pick_level(counts: dict[int, int]) -> int:
    for level in range(1, 7):
        if counts.get(level, 0) >= 5:
            return level
    levels_present = [level for level in range(1, 7) if counts.get(level, 0) > 0]
    return max(levels_present) if levels_present else 0


def _cut_at_level(lines: list[str], level: int) -> list[Section]:
    if level == 0:
        return [Section(header="Full Text", level=0, content="\n".join(lines))]
    indices = [i for i, line in enumerate(lines) if _header_level(line) == level]
    sections = []
    for position, start in enumerate(indices):
        end = indices[position + 1] if position + 1 < len(indices) else len(lines)
        header_text = _HEADER_RE.match(lines[start]).group(2)
        content = "\n".join(lines[start:end])
        sections.append(Section(header=header_text, level=level, content=content))
    return sections


def _front_matter_section(lines: list[str], level: int) -> Section | None:
    """Content before the first chosen-level header, if it is worth its own section.

    A lone title line above the first section is treated as boilerplate and
    dropped. Content with no title at all, or a title plus further structure
    (a subtitle, a stray deeper header), is preserved as "Front Matter"
    (ADR-003).
    """
    if level == 0:
        return None
    first_index = next(
        (i for i, line in enumerate(lines) if _header_level(line) == level), len(lines)
    )
    prefix_lines = lines[:first_index]
    prefix_text = "\n".join(prefix_lines).strip()
    if not prefix_text:
        return None
    header_lines_in_prefix = [line for line in prefix_lines if _header_level(line) is not None]
    if len(header_lines_in_prefix) == 1:
        return None
    return Section(header="Front Matter", level=0, content="\n".join(prefix_lines))


def _recursive_recut(section: Section, threshold: int) -> list[Section]:
    if len(section.content.split()) <= threshold:
        return [section]
    lines = section.content.splitlines()
    levels_in_body = (_header_level(line) for line in lines[1:])
    sub_levels = {lvl for lvl in levels_in_body if lvl is not None and lvl > section.level}
    if not sub_levels:
        return [section]
    children = _split_on_sub_headers(lines, min(sub_levels))
    leaves: list[Section] = []
    for child in children:
        leaves.extend(_recursive_recut(child, threshold))
    return leaves


def _split_on_sub_headers(lines: list[str], sub_level: int) -> list[Section]:
    indices = [i for i, line in enumerate(lines) if _header_level(line) == sub_level]
    leading_text = "\n".join(lines[: indices[0]])
    children = []
    for position, start in enumerate(indices):
        end = indices[position + 1] if position + 1 < len(indices) else len(lines)
        header_text = _HEADER_RE.match(lines[start]).group(2)
        content = "\n".join(lines[start:end])
        children.append(Section(header=header_text, level=sub_level, content=content))
    if leading_text.strip():
        children[0].content = f"{leading_text}\n{children[0].content}"
    return children

"""Stage 2c (ground) — ground assertions against blocks.

Deterministic step that runs after every Stage 2c extraction, not folded
into Pydantic (ADR-008). Three tiers: exact substring hit, repoint on a
miss found elsewhere in the section, or flag as ungrounded. Assertions are
never dropped, only flagged (ADR-009); a repointed index is marked so the
repair stays auditable (ADR-016).
"""

from __future__ import annotations

import re

_PATH_RE = re.compile(r"^\$\.blocks\[(\d+)\]$")


def ground_assertions(assertions: dict, blocks: list[str]) -> dict:
    """Validate every assertion's quote against its section's blocks.

    In: the `{header: {"assertions": [...]}}` dict from
    `extract_assertions_from_section.extract_assertions`, and that section's
    `blocks` from `index_section_into_blocks.index_blocks`.
    Out: the same shape, with each assertion's path corrected if needed and
    `grounded` / `index_corrected` flags added.
    Belongs to: Stage 2c, grounding step (ground_assertions_against_blocks).
    """
    header, body = next(iter(assertions.items()))
    grounded = [_ground_one(assertion, blocks) for assertion in body["assertions"]]
    return {header: {"assertions": grounded}}


def _ground_one(assertion: dict, blocks: list[str]) -> dict:
    claimed_index, quote = _path_and_quote(assertion)

    assertion_type = assertion["type"]
    if 0 <= claimed_index < len(blocks) and quote in blocks[claimed_index]:
        return _result(assertion_type, claimed_index, quote, grounded=True, index_corrected=False)

    found_index = _search_blocks(quote, blocks)
    if found_index is not None:
        return _result(assertion_type, found_index, quote, grounded=True, index_corrected=True)

    return _result(assertion_type, claimed_index, quote, grounded=False, index_corrected=False)


def _result(
    assertion_type: str, index: int, quote: str, *, grounded: bool, index_corrected: bool
) -> dict:
    return {
        "type": assertion_type,
        f"$.blocks[{index}]": quote,
        "grounded": grounded,
        "index_corrected": index_corrected,
    }


def _path_and_quote(assertion: dict) -> tuple[int, str]:
    for key, value in assertion.items():
        match = _PATH_RE.match(key)
        if match:
            return int(match.group(1)), value
    raise ValueError(f"assertion has no $.blocks[i] path: {assertion}")


def _search_blocks(quote: str, blocks: list[str]) -> int | None:
    for i, block in enumerate(blocks):
        if quote in block:
            return i
    return None

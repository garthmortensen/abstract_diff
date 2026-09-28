"""Stage 2b — summarize each section.

One LLM call per sliced section, producing a short summary of that section
alone. Summaries accumulate into one `summary.yaml` per paper, keyed by
section header (R2b.2), which is written by `run_pipeline.py` after calling
this function once per section.
"""

from __future__ import annotations

from pathlib import Path

from paper_diff import llm_client_with_cache
from paper_diff.stage2a_slice_paper_into_sections import Section

_PROMPT_FILE = (
    Path(__file__).resolve().parent.parent / "prompts" / "stage2b_summarize_each_section_llm.md"
)


def summarize_section(section: Section) -> str:
    """Summarize one section in isolation.

    In: a `Section` (header, level, content) from Stage 2a.
    Out: a short (2-4 sentence) summary string of that section's content.
    Belongs to: Stage 2b (summarize each section).
    """
    return llm_client_with_cache.ask(_PROMPT_FILE, section.content).strip()

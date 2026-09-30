"""Entry point.

Calls the pipeline stages in order. Reading this file top to bottom is
reading the architecture diagram in `ADR.md`: format, metrics, slice +
summarize + extract + ground per section, compare, assemble, write the
executive summary, render the report, render the briefs.
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

import yaml

from paper_diff import stage0_format_markdown_headers_llm as stage0
from paper_diff import stage1_compute_objective_metrics as stage1
from paper_diff import stage2a_slice_paper_into_sections as stage2a
from paper_diff import stage2b_summarize_each_section_llm as stage2b
from paper_diff import stage2c_extract_assertions_from_section_llm as stage2c_extract
from paper_diff import stage2c_ground_assertions_against_blocks as stage2c_ground
from paper_diff import stage2c_index_section_into_blocks as stage2c_index
from paper_diff import stage3_compare_papers_llm as stage3
from paper_diff import stage4_assemble_and_validate_comparison as stage4
from paper_diff import stage4b_write_executive_summary_llm as stage4b
from paper_diff import stage5_render_html_report as stage5
from paper_diff import stage5b_render_executive_briefs as stage5b

_SLUG_RE = re.compile(r"[^a-z0-9]+")


def run_pipeline(paper_a_path: Path, paper_b_path: Path, output_dir: Path) -> Path:
    """Run Stages 0 through 5b on a pair of papers.

    In: paths to `paper_a.md` (the champion) and `paper_b.md` (the
    challenger), and a directory to write every stage's intermediate output
    plus the final report and executive briefs into.
    Out: the path to the written `report.html`; the `brief_*.html` files sit
    beside it.
    Belongs to: the pipeline entry point.
    """
    raw_a = copy_original(paper_a_path, output_dir / "paper_a").read_text()
    raw_b = copy_original(paper_b_path, output_dir / "paper_b").read_text()

    formatted_a = stage0.format_paper(raw_a)  # Stage 0 — format markdown
    formatted_b = stage0.format_paper(raw_b)
    _write(output_dir / "paper_a" / "formatted.md", formatted_a)
    _write(output_dir / "paper_b" / "formatted.md", formatted_b)

    metrics = stage1.compute_metrics(formatted_a, formatted_b)  # Stage 1 — objective metrics

    summary_a, tree_a = _process_paper(formatted_a, output_dir / "paper_a")  # Stage 2a/2b/2c
    summary_b, tree_b = _process_paper(formatted_b, output_dir / "paper_b")

    comparison_raw = stage3.compare_papers(tree_a, tree_b, summary_a, summary_b)  # Stage 3

    comparison = stage4.assemble(  # Stage 4 — assemble and validate
        summary_a, tree_a, summary_b, tree_b, metrics, comparison_raw
    )
    _write(output_dir / "comparison.yaml", yaml.safe_dump(comparison.model_dump(), sort_keys=False))

    executive_summary = stage4b.write_executive_summary(comparison)  # Stage 4b — executive summary
    _write(
        output_dir / "executive_summary.yaml",
        yaml.safe_dump(executive_summary.model_dump(), sort_keys=False, allow_unicode=True),
    )

    report_html = stage5.render_report(comparison)  # Stage 5 — render report
    report_path = output_dir / "report.html"
    _write(report_path, report_html)

    for filename, html in stage5b.render_briefs(executive_summary).items():  # Stage 5b — briefs
        _write(output_dir / filename, html)
    return report_path


def _process_paper(formatted_md: str, paper_dir: Path) -> tuple[dict, dict]:
    """Run Stages 2a, 2b and 2c on one paper's sections."""
    sections = stage2a.slice_paper(formatted_md)
    summary: dict = {}
    tree: dict = {}
    for section in sections:
        _write(paper_dir / "sections" / f"{_slugify(section.header)}.md", section.content)

        summary[section.header] = stage2b.summarize_section(section)

        blocks = stage2c_index.index_blocks(section.content)
        raw_assertions = stage2c_extract.extract_assertions(section, blocks)
        grounded = stage2c_ground.ground_assertions(raw_assertions, blocks)
        tree.update(grounded)
        _write(
            paper_dir / "assertions" / f"{_slugify(section.header)}.yaml",
            yaml.safe_dump(grounded, sort_keys=False),
        )

    _write(paper_dir / "summary.yaml", yaml.safe_dump(summary, sort_keys=False))
    return summary, tree


def copy_original(source_path: Path, paper_dir: Path) -> Path:
    """Copy a source paper to `paper_dir/original.md` and return the copy's path.

    Every stage works from the copy, so the source file is only ever read.
    """
    paper_dir.mkdir(parents=True, exist_ok=True)
    return Path(shutil.copyfile(source_path, paper_dir / "original.md"))


def _slugify(header: str) -> str:
    return _SLUG_RE.sub("-", header.lower()).strip("-") or "section"


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


if __name__ == "__main__":
    _lit_md = Path(__file__).resolve().parent.parent / "lit_md"
    run_pipeline(_lit_md / "champion.md", _lit_md / "challenger.md", Path("output"))

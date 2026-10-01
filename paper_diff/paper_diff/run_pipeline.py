"""Entry point.

Calls the pipeline stages in order. Reading this file top to bottom is
reading the architecture diagram in `ADR.md`: format, metrics, slice +
summarize + extract + ground per section, compare, assemble, write the
executive summary, render the report, render the briefs.

The pipeline is split in two halves so that each paper can be processed on
its own before any comparison happens:

- `prepare_paper` runs Stages 0, 2a, 2b and 2c on one paper and writes
  everything it learned into that paper's directory.
- `compare_prepared` reads two prepared directories and runs Stages 1, 3,
  4, 4b, 5 and 5b.

`run_pipeline` is the two halves back to back.
"""

from __future__ import annotations

import hashlib
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

# Files `prepare_paper` writes and `compare_prepared` reads back.
_PREPARED_FILES = ("formatted.md", "summary.yaml", "tree.yaml")


def run_pipeline(paper_a_path: Path, paper_b_path: Path, output_dir: Path) -> Path:
    """Run Stages 0 through 5b on a pair of papers.

    In: paths to `paper_a.md` (the champion) and `paper_b.md` (the
    challenger), and a directory to write every stage's intermediate output
    plus the final report and executive briefs into.
    Out: the path to the written `report.html`; the `brief_*.html` files sit
    beside it.
    Belongs to: the pipeline entry point.
    """
    paper_a_dir = prepare_paper(paper_a_path, output_dir / "paper_a")
    paper_b_dir = prepare_paper(paper_b_path, output_dir / "paper_b")
    return compare_prepared(paper_a_dir, paper_b_dir, output_dir)


def prepare_paper(paper_path: Path, paper_dir: Path) -> Path:
    """Run Stages 0, 2a, 2b and 2c on one paper, with no reference to any other.

    In: the path to one source paper and the directory to write into.
    Out: `paper_dir`, now holding `original.md`, `formatted.md`,
    `sections/*.md`, `assertions/*.yaml`, `summary.yaml` and `tree.yaml`.
    Belongs to: the per-paper half of the pipeline.
    """
    original = copy_original(paper_path, paper_dir)
    _write(
        paper_dir / "manifest.yaml",
        yaml.safe_dump({"source": str(paper_path), "sha256": _sha256(original)}, sort_keys=False),
    )
    formatted = stage0.format_paper(original.read_text())  # Stage 0 — format markdown
    _write(paper_dir / "formatted.md", formatted)
    _process_paper(formatted, paper_dir)  # Stage 2a/2b/2c
    return paper_dir


def compare_prepared(
    paper_a_dir: Path, paper_b_dir: Path, output_dir: Path, name: str | None = None
) -> Path:
    """Run Stages 1, 3, 4, 4b, 5 and 5b on two already-prepared papers.

    In: two directories written by `prepare_paper` (A is the champion, B the
    challenger), the directory to write the comparison and report into, and
    an optional display name for the comparison (defaults to the output
    directory's name).
    Out: the path to the written `report.html`; `comparison.yaml`,
    `executive_summary.yaml`, `manifest.yaml` and the `brief_*.html` files
    sit beside it.
    Belongs to: the pair-wise half of the pipeline.
    """
    formatted_a, summary_a, tree_a = load_prepared(paper_a_dir)
    formatted_b, summary_b, tree_b = load_prepared(paper_b_dir)
    _write(
        output_dir / "manifest.yaml",
        yaml.safe_dump(
            {
                "name": name or output_dir.name,
                "champion": _provenance(paper_a_dir),
                "challenger": _provenance(paper_b_dir),
            },
            sort_keys=False,
        ),
    )

    metrics = stage1.compute_metrics(formatted_a, formatted_b)  # Stage 1 — objective metrics

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


def _provenance(paper_dir: Path) -> dict:
    """Where a prepared paper came from: its directory, source path and content hash.

    The hash is recomputed from `original.md` so it is right even for a
    directory prepared before `manifest.yaml` existed.
    """
    manifest_path = paper_dir / "manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text()) if manifest_path.exists() else {}
    return {
        "dir": str(paper_dir),
        "source": manifest.get("source"),
        "sha256": _sha256(paper_dir / "original.md"),
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_prepared(paper_dir: Path) -> tuple[str, dict, dict]:
    """Read back what `prepare_paper` wrote: formatted text, summary, assertion tree.

    Raises `FileNotFoundError` naming the missing file if the directory was
    never prepared, so a bad path fails before any model call is made.
    """
    for name in _PREPARED_FILES:
        if not (paper_dir / name).exists():
            raise FileNotFoundError(
                f"{paper_dir / name} not found; run `paper-diff prepare` on this paper first"
            )
    formatted = (paper_dir / "formatted.md").read_text()
    summary = yaml.safe_load((paper_dir / "summary.yaml").read_text())
    tree = yaml.safe_load((paper_dir / "tree.yaml").read_text())
    return formatted, summary, tree


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
    _write(paper_dir / "tree.yaml", yaml.safe_dump(tree, sort_keys=False))
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
    _staging = Path(__file__).resolve().parent.parent / "staging"
    run_pipeline(_staging / "champion.md", _staging / "challenger.md", Path("output"))

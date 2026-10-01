"""Thin argparse wrapper: one subcommand per stage, plus `prepare`, `report` and `run`.

`prepare` runs the per-paper half of the pipeline on a single file, `report`
runs the pair-wise half on two prepared directories, and `run` does both.

Every subcommand reads plain markdown or YAML from disk and writes plain
markdown or YAML back to disk, so any stage can be run and inspected on its
own (A10). This module contains no pipeline logic itself — it only parses
arguments, loads files, and calls the one public function each stage
module exposes.
"""

from __future__ import annotations

import argparse
import re
from datetime import datetime
from pathlib import Path

import yaml

from paper_diff import run_pipeline
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
from paper_diff.stage2a_slice_paper_into_sections import Section

_HEADER_RE = re.compile(r"^(#{1,6})\s+(.*)$", re.MULTILINE)

# Default layout: prepared papers under one root, comparisons under another.
PAPERS_ROOT = Path("output") / "papers"
COMPARISONS_ROOT = Path("output") / "comparisons"


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: parse arguments and dispatch to a stage handler."""
    args = _build_parser().parse_args(argv)
    args.handler(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="paper-diff")
    subparsers = parser.add_subparsers(required=True)
    _add_format(subparsers)
    _add_metrics(subparsers)
    _add_slice(subparsers)
    _add_summarize(subparsers)
    _add_index(subparsers)
    _add_extract(subparsers)
    _add_ground(subparsers)
    _add_compare(subparsers)
    _add_assemble(subparsers)
    _add_brief(subparsers)
    _add_render(subparsers)
    _add_render_briefs(subparsers)
    _add_prepare(subparsers)
    _add_report(subparsers)
    _add_run(subparsers)
    return parser


def _add_format(subparsers) -> None:
    parser = subparsers.add_parser("format", help="Stage 0: format markdown headers")
    parser.add_argument("paper_md", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_format)


def _cmd_format(args: argparse.Namespace) -> None:
    formatted = stage0.format_paper(args.paper_md.read_text())
    _write_text(args.out, formatted)


def _add_metrics(subparsers) -> None:
    parser = subparsers.add_parser("metrics", help="Stage 1: objective metrics")
    parser.add_argument("formatted_a_md", type=Path)
    parser.add_argument("formatted_b_md", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_metrics)


def _cmd_metrics(args: argparse.Namespace) -> None:
    metrics = stage1.compute_metrics(
        args.formatted_a_md.read_text(), args.formatted_b_md.read_text()
    )
    _write_yaml(args.out, metrics)


def _add_slice(subparsers) -> None:
    parser = subparsers.add_parser("slice", help="Stage 2a: slice paper into sections")
    parser.add_argument("formatted_md", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.set_defaults(handler=_cmd_slice)


def _cmd_slice(args: argparse.Namespace) -> None:
    sections = stage2a.slice_paper(args.formatted_md.read_text())
    for section in sections:
        _write_text(args.out_dir / f"{_slugify(section.header)}.md", section.content)


def _add_summarize(subparsers) -> None:
    parser = subparsers.add_parser("summarize", help="Stage 2b: summarize a section")
    parser.add_argument("section_md", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_summarize)


def _cmd_summarize(args: argparse.Namespace) -> None:
    summary = stage2b.summarize_section(_load_section(args.section_md))
    _write_text(args.out, summary)


def _add_index(subparsers) -> None:
    parser = subparsers.add_parser("index", help="Stage 2c: index a section into blocks")
    parser.add_argument("section_md", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_index)


def _cmd_index(args: argparse.Namespace) -> None:
    blocks = stage2c_index.index_blocks(args.section_md.read_text())
    _write_yaml(args.out, blocks)


def _add_extract(subparsers) -> None:
    parser = subparsers.add_parser("extract", help="Stage 2c: extract assertions from a section")
    parser.add_argument("section_md", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_extract)


def _cmd_extract(args: argparse.Namespace) -> None:
    section = _load_section(args.section_md)
    blocks = stage2c_index.index_blocks(section.content)
    assertions = stage2c_extract.extract_assertions(section, blocks)
    _write_yaml(args.out, assertions)


def _add_ground(subparsers) -> None:
    parser = subparsers.add_parser("ground", help="Stage 2c: ground assertions against blocks")
    parser.add_argument("assertions_yaml", type=Path)
    parser.add_argument("section_md", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_ground)


def _cmd_ground(args: argparse.Namespace) -> None:
    assertions = _read_yaml(args.assertions_yaml)
    blocks = stage2c_index.index_blocks(args.section_md.read_text())
    grounded = stage2c_ground.ground_assertions(assertions, blocks)
    _write_yaml(args.out, grounded)


def _add_compare(subparsers) -> None:
    parser = subparsers.add_parser("compare", help="Stage 3: compare two papers")
    parser.add_argument("tree_a_yaml", type=Path)
    parser.add_argument("tree_b_yaml", type=Path)
    parser.add_argument("summary_a_yaml", type=Path)
    parser.add_argument("summary_b_yaml", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_compare)


def _cmd_compare(args: argparse.Namespace) -> None:
    result = stage3.compare_papers(
        _read_yaml(args.tree_a_yaml),
        _read_yaml(args.tree_b_yaml),
        _read_yaml(args.summary_a_yaml),
        _read_yaml(args.summary_b_yaml),
    )
    _write_yaml(args.out, result)


def _add_assemble(subparsers) -> None:
    parser = subparsers.add_parser("assemble", help="Stage 4: assemble and validate comparison")
    parser.add_argument("summary_a_yaml", type=Path)
    parser.add_argument("tree_a_yaml", type=Path)
    parser.add_argument("summary_b_yaml", type=Path)
    parser.add_argument("tree_b_yaml", type=Path)
    parser.add_argument("metrics_yaml", type=Path)
    parser.add_argument("comparison_raw_yaml", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_assemble)


def _cmd_assemble(args: argparse.Namespace) -> None:
    comparison = stage4.assemble(
        _read_yaml(args.summary_a_yaml),
        _read_yaml(args.tree_a_yaml),
        _read_yaml(args.summary_b_yaml),
        _read_yaml(args.tree_b_yaml),
        _read_yaml(args.metrics_yaml),
        _read_yaml(args.comparison_raw_yaml),
    )
    _write_yaml(args.out, comparison.model_dump())


def _add_brief(subparsers) -> None:
    parser = subparsers.add_parser("brief", help="Stage 4b: write the executive summary")
    parser.add_argument("comparison_yaml", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_brief)


def _cmd_brief(args: argparse.Namespace) -> None:
    comparison = stage4.Comparison(**_read_yaml(args.comparison_yaml))
    summary = stage4b.write_executive_summary(comparison)
    _write_yaml(args.out, summary.model_dump())


def _add_render(subparsers) -> None:
    parser = subparsers.add_parser("render", help="Stage 5: render the HTML report")
    parser.add_argument("comparison_yaml", type=Path)
    parser.add_argument("--out", type=Path, required=True)
    parser.set_defaults(handler=_cmd_render)


def _cmd_render(args: argparse.Namespace) -> None:
    comparison = stage4.Comparison(**_read_yaml(args.comparison_yaml))
    _write_text(args.out, stage5.render_report(comparison))


def _add_render_briefs(subparsers) -> None:
    parser = subparsers.add_parser("render-briefs", help="Stage 5b: render the executive briefs")
    parser.add_argument("executive_summary_yaml", type=Path)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.set_defaults(handler=_cmd_render_briefs)


def _cmd_render_briefs(args: argparse.Namespace) -> None:
    summary = stage4b.ExecutiveSummary(**_read_yaml(args.executive_summary_yaml))
    for filename, html in stage5b.render_briefs(summary).items():
        _write_text(args.out_dir / filename, html)


def _add_prepare(subparsers) -> None:
    parser = subparsers.add_parser(
        "prepare", help="Run Stages 0, 2a, 2b and 2c on one paper, with no comparison"
    )
    parser.add_argument("paper_md", type=Path, help="one source paper, any extension")
    parser.add_argument(
        "--out-dir",
        type=Path,
        help=f"directory to write this paper's artifacts into (default: {PAPERS_ROOT}/<stem>)",
    )
    parser.set_defaults(handler=_cmd_prepare)


def _cmd_prepare(args: argparse.Namespace) -> None:
    if not args.paper_md.is_file():
        raise SystemExit(
            f"error: {args.paper_md} not found (looked relative to {Path.cwd()}). "
            "Run from the paper_diff/ directory or pass an absolute path."
        )
    out_dir = args.out_dir or PAPERS_ROOT / args.paper_md.stem
    paper_dir = run_pipeline.prepare_paper(args.paper_md, out_dir)
    print(f"Prepared {args.paper_md} into {paper_dir}")


def _add_report(subparsers) -> None:
    parser = subparsers.add_parser(
        "report", help="Run Stages 1, 3, 4, 4b, 5 and 5b on two prepared papers"
    )
    parser.add_argument(
        "paper_a",
        help=f"champion (incumbent): a prepared directory, or a bare name under {PAPERS_ROOT}",
    )
    parser.add_argument(
        "paper_b",
        help=f"challenger: a prepared directory, or a bare name under {PAPERS_ROOT}",
    )
    parser.add_argument(
        "--name", help="name for this comparison (default: output_YYYYMMDDHHMMSS, local time)"
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help=f"where to write the comparison (default: {COMPARISONS_ROOT}/<name>)",
    )
    parser.set_defaults(handler=_cmd_report)


def _cmd_report(args: argparse.Namespace) -> None:
    paper_a_dir = resolve_paper(args.paper_a)
    paper_b_dir = resolve_paper(args.paper_b)
    name = args.name or default_comparison_name()
    out_dir = args.out_dir or COMPARISONS_ROOT / name
    report_path = run_pipeline.compare_prepared(paper_a_dir, paper_b_dir, out_dir, name=name)
    print(f"Wrote {report_path} and brief_*.html alongside it")


def default_comparison_name(now: datetime | None = None) -> str:
    """`output_YYYYMMDDHHMMSS` in local time. Which papers it holds is in `manifest.yaml`."""
    return (now or datetime.now()).strftime("output_%Y%m%d%H%M%S")


def resolve_paper(arg: str) -> Path:
    """Turn a `report` argument into a prepared directory.

    A path that exists on disk is used as given; otherwise the argument is
    treated as a bare paper name under `PAPERS_ROOT`.
    """
    as_path = Path(arg)
    if as_path.is_dir():
        return as_path
    return PAPERS_ROOT / arg


def _add_run(subparsers) -> None:
    parser = subparsers.add_parser(
        "run", help="Run the full pipeline, Stage 0 through 5b (prepare both papers, then report)"
    )
    parser.add_argument("paper_a_md", type=Path, help="the champion (incumbent) paper")
    parser.add_argument("paper_b_md", type=Path, help="the challenger paper")
    parser.add_argument("--out-dir", type=Path, default=Path("output"))
    parser.set_defaults(handler=_cmd_run)


def _cmd_run(args: argparse.Namespace) -> None:
    report_path = run_pipeline.run_pipeline(args.paper_a_md, args.paper_b_md, args.out_dir)
    print(f"Wrote {report_path} and brief_*.html alongside it")


def _load_section(path: Path) -> Section:
    text = path.read_text()
    match = _HEADER_RE.search(text)
    header = match.group(2) if match else path.stem
    level = len(match.group(1)) if match else 0
    return Section(header=header, level=level, content=text)


def _slugify(header: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", header.lower()).strip("-") or "section"


def _read_yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def _write_yaml(path: Path, data) -> None:
    _write_text(path, yaml.safe_dump(data, sort_keys=False))


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


if __name__ == "__main__":
    main()

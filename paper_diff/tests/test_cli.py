"""`prepare` and `report` argument handling: default layout, name resolution.

`run_pipeline` is stubbed so no stage runs; these tests only check what the
CLI decides to call it with.
"""

from datetime import datetime
from pathlib import Path

import pytest

from paper_diff import cli


@pytest.fixture
def recorded(monkeypatch, tmp_path):
    calls: dict = {}
    monkeypatch.chdir(tmp_path)

    def prepare_paper(paper_path, paper_dir):
        calls["prepare"] = (paper_path, paper_dir)
        return paper_dir

    def compare_prepared(a_dir, b_dir, out_dir, name=None):
        calls["report"] = (a_dir, b_dir, out_dir, name)
        return out_dir / "report.html"

    monkeypatch.setattr(cli.run_pipeline, "prepare_paper", prepare_paper)
    monkeypatch.setattr(cli.run_pipeline, "compare_prepared", compare_prepared)
    monkeypatch.setattr(cli, "default_comparison_name", lambda: "output_20260930120000")
    return calls


def test_prepare_defaults_to_papers_root_by_stem(recorded, tmp_path):
    (tmp_path / "lit").mkdir()
    (tmp_path / "lit" / "some paper.txt").write_text("x")
    cli.main(["prepare", "lit/some paper.txt"])
    assert recorded["prepare"] == (Path("lit/some paper.txt"), cli.PAPERS_ROOT / "some paper")


def test_prepare_honours_explicit_out_dir(recorded, tmp_path):
    (tmp_path / "a.md").write_text("x")
    cli.main(["prepare", "a.md", "--out-dir", "elsewhere/a"])
    assert recorded["prepare"][1] == Path("elsewhere/a")


def test_report_resolves_bare_names_and_defaults_to_timestamped_name(recorded):
    cli.main(["report", "wp11", "stress"])
    assert recorded["report"] == (
        cli.PAPERS_ROOT / "wp11",
        cli.PAPERS_ROOT / "stress",
        cli.COMPARISONS_ROOT / "output_20260930120000",
        "output_20260930120000",
    )


def test_default_comparison_name_format():
    assert cli.default_comparison_name(datetime(2026, 9, 30, 7, 5, 9)) == "output_20260930070509"


def test_report_accepts_existing_dirs_and_explicit_name(recorded, tmp_path):
    (tmp_path / "x").mkdir()
    (tmp_path / "y").mkdir()
    cli.main(["report", "x", "y", "--name", "pilot"])
    a_dir, b_dir, out_dir, name = recorded["report"]
    assert (a_dir, b_dir) == (Path("x"), Path("y"))
    assert (out_dir, name) == (cli.COMPARISONS_ROOT / "pilot", "pilot")


def test_report_explicit_out_dir_wins(recorded):
    cli.main(["report", "a", "b", "--name", "n", "--out-dir", "somewhere"])
    assert recorded["report"][2] == Path("somewhere")


def test_prepare_missing_source_exits_with_a_clear_message(recorded):
    with pytest.raises(SystemExit, match="not found"):
        cli.main(["prepare", "../lit_md/missing.txt"])
    assert "prepare" not in recorded

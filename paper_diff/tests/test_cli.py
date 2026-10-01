"""`prepare` and `report` argument handling: default layout, name resolution.

`run_pipeline` is stubbed so no stage runs; these tests only check what the
CLI decides to call it with.
"""

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
    return calls


def test_prepare_defaults_to_papers_root_by_stem_with_prepared_suffix(recorded, tmp_path):
    (tmp_path / "lit").mkdir()
    (tmp_path / "lit" / "some paper.txt").write_text("x")
    cli.main(["prepare", "lit/some paper.txt"])
    assert recorded["prepare"] == (
        Path("lit/some paper.txt"),
        cli.PAPERS_ROOT / "some paper_prepared",
    )


def test_prepare_honours_explicit_out_dir(recorded, tmp_path):
    (tmp_path / "a.md").write_text("x")
    cli.main(["prepare", "a.md", "--out-dir", "elsewhere/a"])
    assert recorded["prepare"][1] == Path("elsewhere/a")


def test_report_resolves_bare_names_and_defaults_to_champion_vs_challenger(recorded):
    cli.main(["report", "wp11_prepared", "stress_prepared"])
    assert recorded["report"] == (
        cli.PAPERS_ROOT / "wp11_prepared",
        cli.PAPERS_ROOT / "stress_prepared",
        cli.COMPARISONS_ROOT / "wp11_vs_stress",
        "wp11_vs_stress",
    )


def test_default_comparison_name_drops_prepared_suffix_only_from_the_end():
    assert cli.default_comparison_name("strategic_defaults_prepared", "CECL_lessons_prepared") == (
        "strategic_defaults_vs_CECL_lessons"
    )
    assert cli.default_comparison_name("paper_a", "paper_b") == "paper_a_vs_paper_b"
    assert cli.default_comparison_name("_prepared", "x_prepared_y") == "_prepared_vs_x_prepared_y"


def test_prepared_name_appends_suffix():
    assert cli.prepared_name("strategic_defaults") == "strategic_defaults_prepared"


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
        cli.main(["prepare", "../staging/missing.txt"])
    assert "prepare" not in recorded

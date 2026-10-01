"""Job runner and on-disk status for the Streamlit app.

Jobs run a throwaway Python one-liner instead of the CLI, so nothing here
needs an API key or network.
"""

import sys
import time
from pathlib import Path

import yaml

from paper_diff import ui_jobs
from paper_diff.ui_jobs import Job


def _python_job(code: str, label: str = "job") -> Job:
    return Job(kind="test", label=label, cmd=[sys.executable, "-c", code], out_dir=Path("."))


def _wait(thread, seconds: float = 10.0) -> None:
    thread.join(seconds)
    assert not thread.is_alive(), "job thread did not finish"


def test_jobs_run_in_order_and_capture_output():
    first = _python_job("print('one')")
    second = _python_job("import sys; print('two'); sys.exit(3)")
    third = _python_job("print('three')")
    thread = ui_jobs.run_jobs_in_background([first, second, third])
    _wait(thread)
    assert (first.state, second.state, third.state) == ("done", "failed", "done")
    assert first.log.strip() == "one"
    assert second.returncode == 3
    assert third.log.strip() == "three", "a failure must not stop later jobs"
    assert first.finished <= second.started <= second.finished <= third.started


def test_job_states_progress_while_running():
    job = _python_job("import time; time.sleep(0.5)")
    assert job.state == "queued" and job.active and job.elapsed == 0.0
    thread = ui_jobs.run_jobs_in_background([job])
    time.sleep(0.1)
    assert job.state == "running" and job.active
    _wait(thread)
    assert job.state == "done" and not job.active and job.elapsed >= 0.4


def test_unstartable_command_fails_cleanly():
    job = Job(kind="test", label="x", cmd=["/no/such/binary"], out_dir=Path("."))
    _wait(ui_jobs.run_jobs_in_background([job]))
    assert job.state == "failed" and "could not start" in job.log


def test_prepare_and_report_jobs_target_the_default_layout():
    prep = ui_jobs.prepare_job(Path("/lit/some paper.txt"), "paper_a")
    assert prep.out_dir == ui_jobs.PAPERS_ROOT / "paper_a"
    assert prep.cmd[1:4] == ["-m", "paper_diff.cli", "prepare"]
    assert "--out-dir" in prep.cmd and prep.label == "some paper.txt → paper_a"

    rep = ui_jobs.report_job("paper_a", "paper_b", "output_1")
    assert rep.out_dir == ui_jobs.COMPARISONS_ROOT / "output_1"
    assert rep.cmd[3:6] == [
        "report",
        str(ui_jobs.PAPERS_ROOT / "paper_a"),
        str(ui_jobs.PAPERS_ROOT / "paper_b"),
    ]
    assert rep.label == "paper_a vs paper_b"


def test_subprocess_env_reads_dotenv_without_overriding_shell(monkeypatch, tmp_path):
    (tmp_path / ".env").write_text("# comment\nANTHROPIC_API_KEY='from-file'\nOTHER=x\nbad line\n")
    monkeypatch.setattr(ui_jobs, "PROJECT_DIR", tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert ui_jobs.subprocess_env()["ANTHROPIC_API_KEY"] == "from-file"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "from-shell")
    assert ui_jobs.subprocess_env()["ANTHROPIC_API_KEY"] == "from-shell"
    assert ui_jobs.subprocess_env()["OTHER"] == "x"


def test_list_source_files_and_names(tmp_path):
    for n in ["b.md", "a.txt", "c.pdf", "notes.TXT"]:
        (tmp_path / n).write_text("x")
    (tmp_path / "sub").mkdir()
    assert [p.name for p in ui_jobs.list_source_files(tmp_path)] == ["a.txt", "b.md", "notes.TXT"]
    assert ui_jobs.list_source_files(tmp_path / "missing") == []
    assert ui_jobs.default_name(Path("CECL lessons (final).txt")) == "CECL_lessons_final_prepared"
    assert ui_jobs.valid_name("paper_a") and not ui_jobs.valid_name("a/b")
    assert not ui_jobs.valid_name("") and not ui_jobs.valid_name(".hidden")


def test_list_prepared_reports_completeness(tmp_path):
    done = tmp_path / "paper_a"
    (done / "sections").mkdir(parents=True)
    (done / "sections" / "s1.md").write_text("x")
    (done / "sections" / "s2.md").write_text("x")
    (done / "tree.yaml").write_text("{}")
    (done / "manifest.yaml").write_text(yaml.safe_dump({"source": "../staging/a.txt"}))
    (tmp_path / "paper_b").mkdir()

    papers = {p.name: p for p in ui_jobs.list_prepared(tmp_path)}
    assert papers["paper_a"].complete and papers["paper_a"].sections == 2
    assert papers["paper_a"].source == "../staging/a.txt"
    assert not papers["paper_b"].complete and papers["paper_b"].source is None
    assert ui_jobs.list_prepared(tmp_path / "nope") == []


def test_list_comparisons_newest_first_with_paper_names(tmp_path):
    for name, complete in [("output_1", True), ("output_2", False)]:
        d = tmp_path / name
        d.mkdir()
        (d / "manifest.yaml").write_text(
            yaml.safe_dump({"champion": {"dir": "output/papers/pa"}, "challenger": {"dir": "x/pb"}})
        )
        if complete:
            (d / ui_jobs.MEMO_FILE).write_text("<html/>")
    comps = ui_jobs.list_comparisons(tmp_path)
    assert [c.name for c in comps] == ["output_2", "output_1"]
    assert comps[1].complete and not comps[0].complete
    assert (comps[1].champion, comps[1].challenger) == ("pa", "pb")
    assert comps[1].memo == tmp_path / "output_1" / ui_jobs.MEMO_FILE


def test_prepare_progress_follows_files_on_disk(tmp_path):
    assert ui_jobs.prepare_progress(tmp_path) == ("Stage 0: formatting headers", None)
    (tmp_path / "formatted.md").write_text("# One\n\ntext\n\n# Two\n\ntext\n\n# Three\n\ntext\n")
    label, fraction = ui_jobs.prepare_progress(tmp_path)
    assert label == "Stage 2: section 1 of 3" and fraction == 0.0
    (tmp_path / "assertions").mkdir()
    (tmp_path / "assertions" / "one.yaml").write_text("{}")
    label, fraction = ui_jobs.prepare_progress(tmp_path)
    assert label == "Stage 2: section 2 of 3" and abs(fraction - 1 / 3) < 1e-9
    (tmp_path / "tree.yaml").write_text("{}")
    assert ui_jobs.prepare_progress(tmp_path) == ("Done", 1.0)


def test_report_progress_follows_milestones(tmp_path):
    assert ui_jobs.report_progress(tmp_path) == ("Stage 3: comparing sections", 0.0)
    (tmp_path / "comparison.yaml").write_text("{}")
    assert ui_jobs.report_progress(tmp_path) == ("Stage 4b: writing executive summary", 0.25)
    (tmp_path / "executive_summary.yaml").write_text("{}")
    (tmp_path / "report.html").write_text("")
    assert ui_jobs.report_progress(tmp_path) == ("Stage 5b: rendering briefs", 0.75)
    (tmp_path / ui_jobs.MEMO_FILE).write_text("")
    assert ui_jobs.report_progress(tmp_path) == ("Done", 1.0)

"""The pipeline's two halves: `prepare_paper` per paper, `compare_prepared` per pair.

Every LLM stage is stubbed at the module attribute `run_pipeline` looks it up
through, so these tests make no network calls and touch no cache.
"""

from pathlib import Path

import pytest
import yaml

from paper_diff import run_pipeline
from paper_diff.stage4b_write_executive_summary_llm import ExecutiveSummary

_PAPER_A = "# Method\n\nWe use ordinary least squares regression.\n"
_PAPER_B = "# Method\n\nWe use gradient boosted trees.\n"


def _executive_summary() -> ExecutiveSummary:
    evidence = [{"source": "challenger", "quote": "q", "why_it_matters": "w"}]
    return ExecutiveSummary(
        headline="h",
        governing_thought="g",
        recommendation="r",
        pillars=[{"claim": f"Pillar {i}.", "evidence": evidence} for i in range(3)],
        challenger_brings=["x"],
        challenger_lacks=[],
        shared_ground="s",
        who_should_care="w",
        counts={"challenger_only": 0, "champion_only": 0, "shared": 1},
    )


@pytest.fixture
def stubbed_stages(monkeypatch):
    calls = {"compare": 0}

    def extract(section, blocks):
        quote = section.content.strip().splitlines()[-1]
        return {section.header: {"assertions": [{"type": "method", "$.blocks[0]": quote}]}}

    def compare(tree_a, tree_b, summary_a, summary_b):
        calls["compare"] += 1
        quote_a = next(v for k, v in tree_a["Method"]["assertions"][0].items() if "$" in k)
        quote_b = next(v for k, v in tree_b["Method"]["assertions"][0].items() if "$" in k)
        return {
            "matched": [{"evidence": [quote_a, quote_b], "interpretation": "Same target."}],
            "a_only": [],
            "b_only": [],
        }

    monkeypatch.setattr(run_pipeline.stage0, "format_paper", lambda raw: raw)
    monkeypatch.setattr(
        run_pipeline.stage2b, "summarize_section", lambda s: f"Summary of {s.header}"
    )
    monkeypatch.setattr(run_pipeline.stage2c_extract, "extract_assertions", extract)
    monkeypatch.setattr(run_pipeline.stage3, "compare_papers", compare)
    monkeypatch.setattr(
        run_pipeline.stage4b, "write_executive_summary", lambda c: _executive_summary()
    )
    return calls


def _write_sources(tmp_path: Path) -> tuple[Path, Path]:
    src = tmp_path / "staging"
    src.mkdir()
    (src / "a.txt").write_text(_PAPER_A)
    (src / "b.txt").write_text(_PAPER_B)
    return src / "a.txt", src / "b.txt"


def test_prepare_paper_writes_everything_the_comparison_needs(tmp_path, stubbed_stages):
    a, _ = _write_sources(tmp_path)

    paper_dir = run_pipeline.prepare_paper(a, tmp_path / "out" / "a")

    assert paper_dir == tmp_path / "out" / "a"
    for name in ("original.md", "formatted.md", "summary.yaml", "tree.yaml"):
        assert (paper_dir / name).exists(), name
    assert (paper_dir / "sections" / "method.md").exists()
    assert (paper_dir / "assertions" / "method.yaml").exists()
    tree = yaml.safe_load((paper_dir / "tree.yaml").read_text())
    assert tree["Method"]["assertions"][0]["grounded"] is True
    assert stubbed_stages["compare"] == 0


def test_prepare_then_report_matches_run(tmp_path, stubbed_stages):
    a, b = _write_sources(tmp_path)

    split_dir = tmp_path / "split"
    run_pipeline.prepare_paper(a, split_dir / "champion")
    run_pipeline.prepare_paper(b, split_dir / "challenger")
    split_report = run_pipeline.compare_prepared(
        split_dir / "champion", split_dir / "challenger", split_dir
    )

    joint_dir = tmp_path / "joint"
    joint_report = run_pipeline.run_pipeline(a, b, joint_dir)

    assert split_report.exists() and joint_report.exists()
    split_yaml = (split_dir / "comparison.yaml").read_text()
    assert split_yaml == (joint_dir / "comparison.yaml").read_text()
    assert (split_dir / "brief_one_page.html").exists()


def test_report_on_unprepared_dir_fails_before_any_model_call(tmp_path, stubbed_stages):
    with pytest.raises(FileNotFoundError, match="paper-diff prepare"):
        run_pipeline.compare_prepared(tmp_path / "nope", tmp_path / "nope", tmp_path)
    assert stubbed_stages["compare"] == 0


def test_manifests_record_provenance(tmp_path, stubbed_stages):
    import hashlib

    a, b = _write_sources(tmp_path)
    a_dir = run_pipeline.prepare_paper(a, tmp_path / "papers" / "a")
    b_dir = run_pipeline.prepare_paper(b, tmp_path / "papers" / "b")

    paper_manifest = yaml.safe_load((a_dir / "manifest.yaml").read_text())
    assert paper_manifest["source"] == str(a)
    assert paper_manifest["sha256"] == hashlib.sha256(_PAPER_A.encode()).hexdigest()

    out = tmp_path / "comparisons" / "custom"
    run_pipeline.compare_prepared(a_dir, b_dir, out, name="custom")
    manifest = yaml.safe_load((out / "manifest.yaml").read_text())
    assert manifest["name"] == "custom"
    assert manifest["champion"] == {
        "dir": str(a_dir),
        "source": str(a),
        "sha256": paper_manifest["sha256"],
    }
    assert manifest["challenger"]["dir"] == str(b_dir)
    assert manifest["challenger"]["sha256"] == hashlib.sha256(_PAPER_B.encode()).hexdigest()


def test_manifest_name_falls_back_to_dir_and_tolerates_legacy_paper(tmp_path, stubbed_stages):
    a, b = _write_sources(tmp_path)
    a_dir = run_pipeline.prepare_paper(a, tmp_path / "papers" / "wp11")
    b_dir = run_pipeline.prepare_paper(b, tmp_path / "papers" / "stress")
    (b_dir / "manifest.yaml").unlink()  # prepared before manifests existed

    out = tmp_path / "output_20260930120000"
    run_pipeline.compare_prepared(a_dir, b_dir, out)
    manifest = yaml.safe_load((out / "manifest.yaml").read_text())
    assert manifest["name"] == "output_20260930120000"
    assert manifest["challenger"]["source"] is None
    assert len(manifest["challenger"]["sha256"]) == 64

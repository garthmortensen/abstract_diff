"""Background jobs and on-disk status for the Streamlit app (`app.py`).

The app never calls a pipeline stage directly. It launches `paper-diff
prepare` or `paper-diff report` as a subprocess in a thread, captures its
output, and reads progress off the files each stage writes to disk. That
keeps the page responsive during a five-minute run, and means a refreshed
browser can pick the state back up from the output directories.

This module imports no Streamlit so it can be tested on its own.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from paper_diff import stage2a_slice_paper_into_sections as stage2a

# `paper_diff/` project directory: where `output/`, `.env` and `.llm_cache/` live,
# and the cwd the CLI expects.
PROJECT_DIR = Path(__file__).resolve().parent.parent
PAPERS_ROOT = PROJECT_DIR / "output" / "papers"
COMPARISONS_ROOT = PROJECT_DIR / "output" / "comparisons"
DEFAULT_INPUT_DIR = PROJECT_DIR.parent / "lit_md"

SOURCE_SUFFIXES = {".txt", ".md"}
MEMO_FILE = "brief_decision_memo.html"
_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Files `compare_prepared` writes, in order, and what the pipeline is doing
# until each one appears.
_REPORT_MILESTONES = [
    ("comparison.yaml", "Stage 3: comparing sections"),
    ("executive_summary.yaml", "Stage 4b: writing executive summary"),
    ("report.html", "Stage 5: rendering report"),
    (MEMO_FILE, "Stage 5b: rendering briefs"),
]


# --------------------------------------------------------------------------- jobs


@dataclass
class Job:
    """One subprocess run of a `paper-diff` subcommand, with its captured output."""

    kind: str  # "prepare" or "report"
    label: str
    cmd: list[str]
    out_dir: Path
    state: str = "queued"  # queued, running, done, failed
    started: float | None = None
    finished: float | None = None
    returncode: int | None = None
    lines: list[str] = field(default_factory=list)

    @property
    def active(self) -> bool:
        return self.state in ("queued", "running")

    @property
    def elapsed(self) -> float:
        if self.started is None:
            return 0.0
        return (self.finished or time.time()) - self.started

    @property
    def log(self) -> str:
        return "".join(self.lines)


def run_jobs_in_background(jobs: list[Job], env: dict[str, str] | None = None) -> threading.Thread:
    """Run `jobs` one after another in a daemon thread and return the thread.

    Each job's `state`, `lines` and `returncode` update as it runs, so a
    caller can poll them. A failed job does not stop the ones after it.
    """
    thread = threading.Thread(target=_run_sequentially, args=(jobs, env), daemon=True)
    thread.start()
    return thread


def _run_sequentially(jobs: list[Job], env: dict[str, str] | None) -> None:
    for job in jobs:
        _run_one(job, env)


def _run_one(job: Job, env: dict[str, str] | None) -> None:
    job.state = "running"
    job.started = time.time()
    try:
        proc = subprocess.Popen(
            job.cmd,
            cwd=PROJECT_DIR,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            job.lines.append(line)
        job.returncode = proc.wait()
    except OSError as exc:
        job.lines.append(f"could not start: {exc}\n")
        job.returncode = -1
    job.finished = time.time()
    job.state = "done" if job.returncode == 0 else "failed"


def prepare_job(source: Path, name: str) -> Job:
    """A `paper-diff prepare` job writing `source` into `PAPERS_ROOT/name`."""
    out_dir = PAPERS_ROOT / name
    cmd = [
        sys.executable,
        "-m",
        "paper_diff.cli",
        "prepare",
        str(source),
        "--out-dir",
        str(out_dir),
    ]
    return Job(kind="prepare", label=f"{source.name} → {name}", cmd=cmd, out_dir=out_dir)


def report_job(champion: str, challenger: str, name: str) -> Job:
    """A `paper-diff report` job comparing two prepared names into `COMPARISONS_ROOT/name`."""
    out_dir = COMPARISONS_ROOT / name
    cmd = [
        sys.executable,
        "-m",
        "paper_diff.cli",
        "report",
        str(PAPERS_ROOT / champion),
        str(PAPERS_ROOT / challenger),
        "--name",
        name,
        "--out-dir",
        str(out_dir),
    ]
    return Job(kind="report", label=f"{champion} vs {challenger}", cmd=cmd, out_dir=out_dir)


def subprocess_env() -> dict[str, str]:
    """The shell environment plus any `KEY=value` lines from `PROJECT_DIR/.env`.

    Values already in the environment win, so an exported key is never
    overridden by the file.
    """
    env = dict(os.environ)
    dotenv = PROJECT_DIR / ".env"
    if dotenv.is_file():
        for line in dotenv.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env.setdefault(key.strip(), value.strip().strip("'\""))
    return env


# --------------------------------------------------------------------------- inputs


def list_source_files(folder: Path) -> list[Path]:
    """Text and markdown files directly inside `folder`, sorted by name."""
    if not folder.is_dir():
        return []
    return sorted(
        p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in SOURCE_SUFFIXES
    )


def default_name(source: Path) -> str:
    """A filesystem-safe paper name from a source file's stem."""
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", source.stem).strip("._-")
    return cleaned or "paper"


def valid_name(name: str) -> bool:
    return bool(_NAME_RE.match(name))


# --------------------------------------------------------------------------- on-disk status


@dataclass
class PreparedPaper:
    name: str
    dir: Path
    source: str | None
    complete: bool
    sections: int


def list_prepared(root: Path = PAPERS_ROOT) -> list[PreparedPaper]:
    """Every directory under `root`, complete or not, with what its manifest says."""
    if not root.is_dir():
        return []
    papers = []
    for d in sorted(p for p in root.iterdir() if p.is_dir()):
        manifest = _read_yaml(d / "manifest.yaml")
        papers.append(
            PreparedPaper(
                name=d.name,
                dir=d,
                source=manifest.get("source"),
                complete=(d / "tree.yaml").exists(),
                sections=len(list((d / "sections").glob("*.md")))
                if (d / "sections").is_dir()
                else 0,
            )
        )
    return papers


@dataclass
class Comparison:
    name: str
    dir: Path
    champion: str | None
    challenger: str | None
    complete: bool

    @property
    def memo(self) -> Path:
        return self.dir / MEMO_FILE


def list_comparisons(root: Path = COMPARISONS_ROOT) -> list[Comparison]:
    """Every comparison under `root`, newest first."""
    if not root.is_dir():
        return []
    found = []
    for d in sorted((p for p in root.iterdir() if p.is_dir()), reverse=True):
        manifest = _read_yaml(d / "manifest.yaml")
        found.append(
            Comparison(
                name=d.name,
                dir=d,
                champion=_paper_name(manifest.get("champion")),
                challenger=_paper_name(manifest.get("challenger")),
                complete=(d / MEMO_FILE).exists(),
            )
        )
    return found


def prepare_progress(paper_dir: Path) -> tuple[str, float | None]:
    """What `prepare` is doing in `paper_dir` right now, and how far along it is.

    Stage 0 is a single model call with nothing to count, so its fraction is
    `None`. Once `formatted.md` exists the section list is known, and each
    `assertions/*.yaml` file is one finished section.
    """
    formatted = paper_dir / "formatted.md"
    if (paper_dir / "tree.yaml").exists():
        return "Done", 1.0
    if not formatted.exists():
        return "Stage 0: formatting headers", None
    total = len(stage2a.slice_paper(formatted.read_text())) or 1
    done = len(list((paper_dir / "assertions").glob("*.yaml")))
    return f"Stage 2: section {min(done + 1, total)} of {total}", done / total


def report_progress(out_dir: Path) -> tuple[str, float]:
    """What `report` is doing in `out_dir` right now, and how far along it is."""
    for i, (filename, label) in enumerate(_REPORT_MILESTONES):
        if not (out_dir / filename).exists():
            return label, i / len(_REPORT_MILESTONES)
    return "Done", 1.0


def _read_yaml(path: Path) -> dict:
    if not path.is_file():
        return {}
    data = yaml.safe_load(path.read_text())
    return data if isinstance(data, dict) else {}


def _paper_name(provenance) -> str | None:
    if isinstance(provenance, dict) and provenance.get("dir"):
        return Path(provenance["dir"]).name
    return None

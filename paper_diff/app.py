"""Streamlit front end for paper-diff: prepare papers, compare two, read the memo.

Three tabs mirror the three CLI steps. Runs happen in background
subprocesses (see `paper_diff/ui_jobs.py`) and the page polls their output
every few seconds, so a five-minute run never blocks the browser.

    streamlit run app.py        # from the paper_diff/ directory
"""

from __future__ import annotations

from pathlib import Path

import streamlit as st

from paper_diff import llm_client_with_cache as llm
from paper_diff import ui_jobs
from paper_diff.cli import default_comparison_name
from paper_diff.ui_jobs import Job

POLL_SECONDS = 3
STATE_ICON = {"queued": "⬜", "running": "⏳", "done": "✅", "failed": "❌"}

st.set_page_config(page_title="Paper Diff", page_icon="⚖", layout="centered")


@st.cache_resource
def job_registry() -> dict[str, list[Job]]:
    """Jobs live for the whole server process, so a browser refresh re-attaches to them."""
    return {"prepare": [], "report": []}


def active(kind: str) -> bool:
    return any(job.active for job in job_registry()[kind])


def fmt_elapsed(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m}m {s:02d}s"


# --------------------------------------------------------------------------- sidebar


def sidebar() -> None:
    with st.sidebar:
        st.title("⚖ Paper Diff")
        try:
            label, model_id, _ = llm.selected_model()
            st.caption(f"Model: **{label}** (`{model_id}`)")
        except ValueError as exc:
            st.error(str(exc))
        if not ui_jobs.subprocess_env().get("ANTHROPIC_API_KEY"):
            st.error("ANTHROPIC_API_KEY is not set. Export it or put it in `.env`.")
        st.caption(f"Output: `{ui_jobs.PROJECT_DIR / 'output'}`")
        st.caption("Each step takes about five minutes. Replies are cached, so a rerun resumes.")


# --------------------------------------------------------------------------- live job panels


def job_card(job: Job, progress_fn) -> None:
    """One job's state, elapsed time, inferred stage and log."""
    icon = STATE_ICON[job.state]
    with st.container(border=True):
        head, when = st.columns([3, 1])
        head.markdown(f"{icon} **{job.label}**")
        when.caption(fmt_elapsed(job.elapsed) if job.started else "queued")
        if job.state == "running":
            stage, fraction = progress_fn(job.out_dir)
            if fraction is None:
                st.progress(0.02, text=f"{stage} · about five minutes in total")
            else:
                st.progress(min(fraction, 0.99), text=stage)
        elif job.state == "failed":
            st.error(f"Exited with code {job.returncode}. Run again to resume from the cache.")
        if job.lines and job.state != "queued":
            with st.expander("Output", expanded=job.state == "failed"):
                st.code(job.log[-4000:] or "(no output yet)", language="text")


def live_panel(kind: str, progress_fn) -> None:
    """Render `kind` jobs, polling while any is active, then refresh the page once they finish."""
    polling = active(kind)

    @st.fragment(run_every=POLL_SECONDS if polling else None)
    def panel() -> None:
        jobs = job_registry()[kind]
        for job in jobs[-6:]:
            job_card(job, progress_fn)
        if polling and not active(kind):
            st.rerun(scope="app")

    panel()


# --------------------------------------------------------------------------- tab 1: prepare


def tab_prepare() -> None:
    folder = Path(st.text_input("Input folder", str(ui_jobs.DEFAULT_INPUT_DIR))).expanduser()
    files = ui_jobs.list_source_files(folder)
    if not folder.is_dir():
        st.warning(f"`{folder}` is not a directory.")
    elif not files:
        st.warning("No `.txt` or `.md` files in that folder.")

    picked = st.multiselect("Files to prepare", [f.name for f in files])
    names = {filename: ui_jobs.default_name(folder / filename) for filename in picked}
    if picked:
        st.caption("Each paper is saved under `output/papers/` as its file name plus `_prepared`.")
        for filename, name in names.items():
            c1, c2 = st.columns([3, 2])
            c1.markdown(f"`{filename}`")
            c2.markdown(f"→ `{name}`")

    problems = _name_problems(names)
    for p in problems:
        st.error(p)
    st.caption("Each paper takes about five minutes. Papers are prepared one after another.")

    busy = active("prepare")
    if st.button(
        "▶ Prepare selected", type="primary", disabled=not picked or busy or bool(problems)
    ):
        jobs = [ui_jobs.prepare_job(folder / f, names[f]) for f in picked]
        job_registry()["prepare"].extend(jobs)
        ui_jobs.run_jobs_in_background(jobs, ui_jobs.subprocess_env())
        st.rerun()
    if busy:
        st.info("Preparing. You can leave this tab or refresh the page; the run keeps going.")

    live_panel("prepare", ui_jobs.prepare_progress)
    _library()


def _name_problems(names: dict[str, str]) -> list[str]:
    """Blocking problems with the chosen names. Overwrites only warn."""
    problems = []
    existing = {p.name for p in ui_jobs.list_prepared() if p.complete}
    seen: set[str] = set()
    for filename, name in names.items():
        if not ui_jobs.valid_name(name):
            problems.append(f"`{name}` for {filename}: use letters, digits, `.`, `_` or `-`.")
        elif name in seen:
            problems.append(f"`{name}` is used twice.")
        elif name in existing:
            st.warning(f"`{name}` already exists under output/papers/ and will be overwritten.")
        seen.add(name)
    return problems


def _library() -> None:
    st.subheader("Library")
    papers = ui_jobs.list_prepared()
    if not papers:
        st.caption("No prepared papers yet.")
        return
    running = {job.out_dir.name for job in job_registry()["prepare"] if job.active}
    for p in papers:
        if p.name in running:
            icon, note = "⏳", "running"
        elif p.complete:
            icon, note = "✅", f"{p.sections} sections"
        else:
            icon, note = "⚠️", "incomplete, prepare again to resume"
        source = Path(p.source).name if p.source else "unknown source"
        st.markdown(f"{icon} `{p.name}` — {source} · {note}")


# --------------------------------------------------------------------------- tab 2: compare


def tab_compare() -> None:
    prepared = [p.name for p in ui_jobs.list_prepared() if p.complete]
    if len(prepared) < 2:
        st.warning("Prepare at least two papers first (tab 1).")
    else:
        champion = st.radio("Champion (incumbent, A)", prepared, horizontal=True)
        challenger = st.radio(
            "Challenger (B)", [p for p in prepared if p != champion], horizontal=True
        )
        name = default_comparison_name(champion, challenger)
        st.markdown(f"Saved as `output/comparisons/{name}/`")
        st.caption(f"`paper-diff report {champion} {challenger}` · about five minutes")
        if (ui_jobs.COMPARISONS_ROOT / name).exists():
            st.warning("This pair was compared before. Running again overwrites that result.")
        busy = active("report")
        if st.button("⚖ Run comparison", type="primary", disabled=busy):
            job = ui_jobs.report_job(champion, challenger, name)
            job_registry()["report"].append(job)
            ui_jobs.run_jobs_in_background([job], ui_jobs.subprocess_env())
            st.rerun()
        if busy:
            st.info("Comparing. The memo appears in tab 3 when this finishes.")

    live_panel("report", ui_jobs.report_progress)
    _finished_notice()

    done = [c for c in ui_jobs.list_comparisons() if c.complete]
    if done:
        with st.expander(f"Previous comparisons ({len(done)})"):
            for c in done:
                st.markdown(f"`{c.name}` — {c.champion or '?'} vs {c.challenger or '?'}")


def _finished_notice() -> None:
    """Point at tab 3 the first time each comparison finishes."""
    announced = st.session_state.setdefault("announced", set())
    for job in job_registry()["report"]:
        if job.state == "done" and job.out_dir.name not in announced:
            announced.add(job.out_dir.name)
            st.toast(f"Comparison {job.out_dir.name} finished. See tab 3.", icon="✅")
            st.session_state["memo_choice"] = job.out_dir.name


# --------------------------------------------------------------------------- tab 3: memo


def tab_memo() -> None:
    done = [c for c in ui_jobs.list_comparisons() if c.complete]
    if not done:
        st.info("The decision memo appears here after a comparison (tab 2).")
        return
    by_name = {c.name: c for c in done}
    names = list(by_name)
    default = st.session_state.get("memo_choice", names[0])
    chosen = st.selectbox(
        "Comparison",
        names,
        index=names.index(default) if default in names else 0,
        format_func=lambda n: f"{n} — {by_name[n].champion} vs {by_name[n].challenger}",
    )
    comp = by_name[chosen]
    html = comp.memo.read_text()

    c1, c2 = st.columns([3, 1])
    c1.success(f"`{comp.memo.relative_to(ui_jobs.PROJECT_DIR)}`")
    c2.download_button(
        "⬇ Download",
        html,
        file_name=f"{comp.name}_{ui_jobs.MEMO_FILE}",
        mime="text/html",
        use_container_width=True,
    )
    _embed_html(comp.memo, html)

    with st.expander("Other files in this comparison"):
        for f in sorted(comp.dir.iterdir()):
            st.markdown(f"`{f.name}`")


def _embed_html(path: Path, html: str) -> None:
    """Render an HTML file inline. `st.iframe` arrived in Streamlit 1.50; fall back before that."""
    if hasattr(st, "iframe"):
        st.iframe(path, height=900)
    else:
        import streamlit.components.v1 as components

        components.html(html, height=900, scrolling=True)


# --------------------------------------------------------------------------- page


def stepper() -> None:
    prepared = sum(p.complete for p in ui_jobs.list_prepared())
    compared = any(c.complete for c in ui_jobs.list_comparisons())
    s1 = "✅" if prepared >= 2 else "1️⃣"
    s2 = "✅" if compared else "2️⃣"
    s3 = "✅" if compared else "3️⃣"
    st.markdown(f"**{s1} Prepare papers** → **{s2} Compare** → **{s3} Memo**")


def main() -> None:
    sidebar()
    st.title("Paper Diff")
    stepper()
    tab1, tab2, tab3 = st.tabs(["1 · Prepare papers", "2 · Compare", "3 · Decision memo"])
    with tab1:
        tab_prepare()
    with tab2:
        tab_compare()
    with tab3:
        tab_memo()


main()

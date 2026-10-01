# Web UI

A Streamlit front end for paper-diff, built on the "three-step wizard"
design. It wraps the three CLI steps described in `README.md`: prepare
papers, compare two prepared papers, read the decision memo.

## Running it

Streamlit must be installed in the same environment as `paper-diff`. The
app runs the CLI with the interpreter that launched Streamlit, so a
system-wide Streamlit would spawn a Python without the `anthropic` package
and every job would fail.

```sh
cd ~/garage/challenger_delta/paper_diff
source .venv/bin/activate
pip install -e ".[ui]"
streamlit run app.py
```

The browser opens at http://localhost:8501. Press `Ctrl+C` in the terminal
to stop the server. A run that has already started finishes on its own.

## Using it

1. **Prepare papers.** Point the input folder at your sources (default
   `../staging/`), tick one or more `.txt` or `.md` files. Each paper is saved
   under `output/papers/` as its file name plus `_prepared`, for example
   `strategic_defaults_prepared`. The name is fixed and cannot be edited. Selected papers are prepared one after another. The
   library below lists everything under `output/papers/` and whether it is
   complete.
2. **Compare.** Pick the champion (incumbent) and challenger from the
   prepared papers, optionally change the comparison name, and run. The name
   defaults to `<champion>_vs_<challenger>` with `_prepared` dropped, for
   example `strategic_defaults_vs_CECL_lessons`. Reusing a name shows a warning and
   overwrites. The comparison is written to `output/comparisons/<name>/`.
3. **Decision memo.** The newest `brief_decision_memo.html` renders inline,
   with a download button and a selector for earlier comparisons. An
   expander lists the other files in that comparison folder.

A stepper line at the top shows which steps are done. The sidebar shows the
model chosen by `USER_CHOICE` in `paper_diff/llm_client_with_cache.py` and
warns when `ANTHROPIC_API_KEY` is missing. The key is read from the shell
environment or from `.env` in this directory.

## Files

| File | Role |
|---|---|
| `app.py` | The Streamlit page: sidebar, stepper, three tabs. |
| `paper_diff/ui_jobs.py` | Glue with no Streamlit dependency. Launches `paper-diff prepare` and `paper-diff report` as subprocesses, captures output, reads progress from disk. |
| `tests/test_ui_jobs.py` | Tests for the job runner, `.env` handling and progress inference. No API key or network needed. |
| `../ui_mockups/` | The three wireframes the design was chosen from. UI only, no pipeline calls. Safe to delete. |

`pyproject.toml` has a `ui` extra that pulls in Streamlit.

## How long runs are handled

Each step takes about five minutes. The app never calls a pipeline stage
directly.

- **Background subprocesses.** Clicking a button launches the CLI in a
  daemon thread via `subprocess.Popen` and returns immediately. Stdout and
  stderr are captured line by line into the job.
- **Server-wide job registry.** Jobs are stored with `st.cache_resource`,
  which lives for the whole server process rather than one browser tab.
  Refreshing the browser re-attaches to a run in progress instead of
  losing it.
- **Polling fragment.** While a job is active, only the status panel reruns,
  every three seconds, using `st.fragment(run_every=...)`. The rest of the
  page stays interactive. When the last active job finishes the whole page
  refreshes once.
- **Progress inferred from disk.** The CLI prints nothing until it
  finishes, so the progress bar reads the files each stage writes:
  - *Prepare*: before `formatted.md` exists the job is in Stage 0, a
    single model call with nothing to count. Once it exists the section
    list is known (`stage2a.slice_paper`), and each `assertions/*.yaml`
    file is one finished section. `tree.yaml` means done.
  - *Compare*: four milestone files in order, `comparison.yaml`,
    `executive_summary.yaml`, `report.html`, `brief_decision_memo.html`.
- **Sequential queue.** Papers ticked together in tab 1 are prepared one
  after another in a single thread. A failure does not stop the ones after
  it.
- **Failures.** A failed card shows the exit code and the captured log.
  Running the same paper again resumes from `.llm_cache/`, as with the
  CLI.
- **Finished notice.** When a comparison finishes, a toast points at tab 3,
  and tab 3 defaults to that comparison.

## Design notes

- The on-disk layout is the source of truth. The library, the champion and
  challenger choices, and the memo selector are all rebuilt from
  `output/papers/` and `output/comparisons/` on every rerun, so the app
  agrees with whatever the CLI did outside it.
- Paper names are validated to letters, digits, `.`, `_` and `-`.
  Reusing an existing name warns that the folder will be overwritten but
  does not block the run.
- `st.iframe` renders the memo. It arrived in Streamlit 1.50, and the app
  falls back to `components.html` on older versions.
- Streamlit cannot switch tabs programmatically, which is why the finished
  notice is a toast rather than a jump to tab 3.

## Verification done so far

- Full test suite (93 tests) and `ruff check` pass.
- Headless `AppTest` run against the existing `output/` folder: three tabs,
  library, previous comparisons and memo all render without exceptions.
- Clicking **Run comparison** with the report job stubbed to a one-second
  Python command: the card shows running, then done, the log is captured,
  and the page refreshes.
- No real five-minute pipeline run has been made through the app yet. The
  first live run is still untested.

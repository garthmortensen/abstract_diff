# paper-diff

Compares two research papers section by section and renders an HTML diff
report. Paper A is the champion (incumbent), paper B is the challenger.

Design notes live in `../ADR.md` and `../requirements.md`. Limits for very
large papers are in `adjusting_limits.md`.

## Setup

```sh
cd paper_diff
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
echo "ANTHROPIC_API_KEY=sk-..." > .env
```

Source papers are plain text or markdown, with or without headers. The
originals are only ever read. Each run copies them into the output directory.

## Usage

Comparing two papers takes three commands, run in order.

First move into the `paper_diff/` directory and activate the environment.
Every relative path below, including `../staging/` and `output/`, is
relative to where you run the command.

```sh
cd ~/garage/challenger_delta/paper_diff
source .venv/bin/activate
```

| Step | What it does | Cost |
|---|---|---|
| 1. Prepare paper A | Processes the champion on its own | Model calls |
| 2. Prepare paper B | Processes the challenger on its own | Model calls |
| 3. Compare | Compares the two prepared results | Model calls |

Papers A and B never see each other until step 3. You can prepare them on
different days, and you only ever re-run step 3 to compare again.

**Paper A is the champion** (the incumbent). **Paper B is the challenger.**
The order matters in step 3, so decide it up front.

### Step 1: Prepare paper A (the champion)

```sh
paper-diff prepare ../staging/strategic_defaults.txt
```

### Step 2: Prepare paper B (the challenger)

```sh
paper-diff prepare ../staging/CECL_lessons.txt
```

Replace the file paths with your own. Any text or markdown file works, with
or without headers. Large files are fine.

Each step prints `Prepared ... into output/papers/<name>_prepared` when it finishes.
If it fails partway, run the same command again. Model replies are cached in
`.llm_cache/`, so it resumes where it stopped instead of starting over.

The paper goes to `output/papers/<file name without extension>_prepared/`,
so `strategic_defaults.txt` becomes `output/papers/strategic_defaults_prepared/`. Pass `--out-dir`
to choose a different directory.

Prepare your own file names above in place of the examples. The
champion/challenger choice is made in step 3, not here.

### Step 3: Compare

```sh
paper-diff report strategic_defaults_prepared CECL_lessons_prepared
```

The first name is the champion and the second is the challenger. A bare name
means `output/papers/<name>`. You can also pass a full path to any prepared
directory.

The result is written to `output/comparisons/<champion>_vs_<challenger>/`,
here `strategic_defaults_vs_CECL_lessons`, with `_prepared` dropped from each name. The
command prints its path. Open `report.html` inside it first.

Comparing the same pair again reuses that name and overwrites the earlier
result. Use `--name` to keep both.

Options:

- `--name pilot` uses `output/comparisons/pilot/` instead of the default name.
- `--out-dir some/path` writes to exactly that directory.

If you forgot a step, the command stops before any model call and names the
missing file.

### What you get

Each prepared paper directory, such as `output/papers/strategic_defaults_prepared/`:

| File | Contents |
|---|---|
| `original.md` | Untouched copy of the source |
| `manifest.yaml` | Source path and SHA-256 of the original |
| `formatted.md` | Copy with markdown headers inserted |
| `sections/*.md` | One file per section |
| `assertions/*.yaml` | Grounded assertions per section |
| `summary.yaml` | One summary per section |
| `tree.yaml` | All assertions in section order, read by step 3 |

Each comparison directory, such as `output/comparisons/strategic_defaults_vs_CECL_lessons/`:

| File | Contents |
|---|---|
| `report.html` | Full report of every matched and one-sided assertion |
| `brief_one_page.html`, `brief_abstract.html`, `brief_decision_memo.html` | Short executive briefs |
| `executive_summary.yaml` | Data behind the briefs |
| `comparison.yaml` | Full comparison data |
| `manifest.yaml` | Which two papers were compared, which was champion, and the hash of each original |

The source files in `staging/` are only ever read, never modified.

### Both at once

If you want one command and don't need the papers prepared separately:

```sh
paper-diff run champion.md challenger.md --out-dir output
```

This prepares both papers into `output/paper_a` and `output/paper_b`, then
compares them into `output/`. It does not use the `papers/` and
`comparisons/` layout above.

### Choosing the model

One model is used for every step. The choices are listed at the top of
`paper_diff/llm_client_with_cache.py`:

| `USER_CHOICE` | Model |
|---|---|
| 1 | Sonnet 5.5 (default) |
| 2 | Haiku 4.5 |
| 3 | Fable 5.1 |
| 4 | Opus 5.5 |

Edit the line `USER_CHOICE = 1` in that file and save it. Use the same value
for step 1, step 2 and step 3, so both papers and the comparison come from the
same model. A number outside 1 to 4 stops the run with the valid options.

Replies are cached per model, so switching models makes fresh calls and
switching back reuses the earlier replies.

### Single stages

Every stage also has its own subcommand that reads and writes plain files:
`format`, `metrics`, `slice`, `summarize`, `index`, `extract`, `ground`,
`compare`, `assemble`, `brief`, `render` and `render-briefs`. Run
`paper-diff <command> --help` for arguments.

## Web UI

`app.py` is a Streamlit front end for the three steps above. Tab 1 prepares
papers, tab 2 compares two prepared papers, tab 3 shows the resulting
`brief_decision_memo.html`. Each run is launched as a background
`paper-diff` subprocess, so the page stays responsive during the five
minutes a step takes, and refreshing the browser re-attaches to a run in
progress. Progress is read from the files each stage writes under `output/`.

Install Streamlit into the same environment as `paper-diff`, then start the
app from this directory:

```sh
cd ~/garage/challenger_delta/paper_diff
source .venv/bin/activate
pip install -e ".[ui]"
streamlit run app.py
```

The browser opens at http://localhost:8501. Press `Ctrl+C` in the terminal
to stop the server; a run already started finishes on its own.

Using the app:

1. **Prepare papers.** Point the input folder at your sources (default
   `../staging/`), tick one or more files. Each paper is saved as its file name plus
   `_prepared`, and the name cannot be edited. Selected papers are prepared one after another. The library
   below lists everything under `output/papers/` and whether it is complete.
2. **Compare.** Pick the champion and challenger from the prepared papers
   and run. The name defaults to `<champion>_vs_<challenger>`, and the
   comparison is written to `output/comparisons/<name>/`.
3. **Decision memo.** The newest memo renders inline, with a download
   button and a selector for earlier comparisons.

The sidebar shows the model chosen by `USER_CHOICE` and warns when
`ANTHROPIC_API_KEY` is missing. The key is read from the shell environment
or from `.env` in this directory. A failed run can simply be started again:
replies are cached, so it resumes where it stopped.

The three wireframes the design was chosen from are still in
`../ui_mockups/`; they run with `streamlit run ../ui_mockups/<file>.py` and
call no pipeline code.

## Development

```sh
ruff check paper_diff tests
pytest -q
```

Tests stub every model call, so they need no API key or network.

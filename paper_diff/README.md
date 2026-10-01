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
Every relative path below, including `../lit_md/` and `output/`, is
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
paper-diff prepare ../lit_md/wp11-3.txt --out-dir output/papers/paper_a
```

### Step 2: Prepare paper B (the challenger)

```sh
paper-diff prepare ../lit_md/proposed_stress_test_model_documentation_credit_risk_models.txt \
    --out-dir output/papers/paper_b
```

Replace the file paths with your own. Any text or markdown file works, with
or without headers. Large files are fine.

Each step prints `Prepared ... into output/papers/paper_x` when it finishes.
If it fails partway, run the same command again. Model replies are cached in
`.llm_cache/`, so it resumes where it stopped instead of starting over.

If you leave out `--out-dir`, the paper goes to `output/papers/<file name
without extension>/`. Giving short names like `paper_a` and `paper_b` keeps
step 3 easy to type.

### Step 3: Compare

```sh
paper-diff report paper_a paper_b
```

The first name is the champion and the second is the challenger. A bare name
means `output/papers/<name>`. You can also pass a full path to any prepared
directory.

The result is written to a new folder named `output_YYYYMMDDHHMMSS`, using
the local time, under `output/comparisons/`. The command prints its path.
Open `report.html` inside it first.

Options:

- `--name pilot` uses `output/comparisons/pilot/` instead of the timestamp.
- `--out-dir some/path` writes to exactly that directory.

If you forgot a step, the command stops before any model call and names the
missing file.

### What you get

Each prepared paper directory, such as `output/papers/paper_a/`:

| File | Contents |
|---|---|
| `original.md` | Untouched copy of the source |
| `manifest.yaml` | Source path and SHA-256 of the original |
| `formatted.md` | Copy with markdown headers inserted |
| `sections/*.md` | One file per section |
| `assertions/*.yaml` | Grounded assertions per section |
| `summary.yaml` | One summary per section |
| `tree.yaml` | All assertions in section order, read by step 3 |

Each comparison directory, such as `output/comparisons/output_20260930120000/`:

| File | Contents |
|---|---|
| `report.html` | Full report of every matched and one-sided assertion |
| `brief_one_page.html`, `brief_abstract.html`, `brief_decision_memo.html` | Short executive briefs |
| `executive_summary.yaml` | Data behind the briefs |
| `comparison.yaml` | Full comparison data |
| `manifest.yaml` | Which two papers were compared, which was champion, and the hash of each original |

The source files in `lit_md/` are only ever read, never modified.

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

## Development

```sh
ruff check paper_diff tests
pytest -q
```

Tests stub every model call, so they need no API key or network.

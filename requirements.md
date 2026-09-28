# Paper Comparison Pipeline — Requirements

Companion to `ADR.md`, which records *why* each choice below was made. This
document states *what* the system must do. It is derived from
`solutions_simple_pruned.md`; the two-paper fixture referenced throughout is
`lit_md/champion.md` (~3.6k words) and `lit_md/challenger.md` (~3.1k words).

## 1. Purpose

Given two research papers in markdown, produce an HTML report that shows which
claims, methods, data choices, assumptions, findings and conclusions the papers
share, where they differ, and where each says something the other does not.
Every quoted assertion in the report must be traceable to a verbatim location in the
source text, and every LLM-produced artifact must have a deterministic check
behind it.

## 2. Scope

### In scope

- Two papers per run, both supplied as `.md` files.
- Papers may arrive already structured with markdown headers, or as unheaded
  prose. Both must be handled by the same pipeline with no user-facing switch.
- A single HTML report as the deliverable.

### Out of scope

- More than two papers per run.
- Non-markdown inputs (PDF conversion happens upstream).
- Embeddings, vector stores, or any similarity-search infrastructure (see
  ADR-014).

## 3. Inputs and outputs

| Artifact | Producer | Consumer | Format |
| --- | --- | --- | --- |
| `paper_a.md`, `paper_b.md` | user | Stage 0 | raw markdown, may lack headers |
| formatted paper | Stage 0 | Stages 1, 2a | markdown with headers |
| metrics | Stage 1 | Stage 4 only | word/sentence counts, Jaccard |
| `sections/*.md` | Stage 2a | Stages 2b, 2c | one file per section |
| `summary.yaml` | Stage 2b | Stages 3, 4 | `{header: {summary: str}}` |
| `assertions/<header>.yaml` | Stage 2c | grounding, Stage 3, Stage 4 | `{header: {assertions: [...]}}` |
| `comparison.yaml` | Stage 4 | Stages 4b, 5 | Pydantic-validated |
| `executive_summary.yaml` | Stage 4b | Stage 5b | Pydantic-validated pyramid: thought, pillars, evidence |
| `report.html` | Stage 5 | human | Jinja2-rendered, full detail |
| `brief_*.html` (3 files) | Stage 5b | busy human | Jinja2-rendered, one per brief format |

## 4. Pipeline stages

Stages run strictly in order 0 → 1 → 2 → 3 → 4 → 5. Every LLM call is cached by
a hash of its input so re-runs are free.

### Stage 0 — Format markdown

- R0.1 Runs on every input, unconditionally. One LLM call per paper.
- R0.2 The prompt must be idempotent: preserve existing headers verbatim, add
  headers only where none exist, never reword or reorder body text.
- R0.3 **Post-check (deterministic).** Strip every header line (matching
  `^#{1,6}\s`) from both the raw input and the formatted output, normalise
  whitespace, and assert the remainders are identical. Any difference fails the
  run loudly. See ADR-015.
- R0.4 All downstream stages consume Stage 0 output, never the raw file.

### Stage 1 — Objective metrics

- R1.1 Runs on the whole formatted paper, before slicing. No LLM, stdlib only.
- R1.2 Computes per paper: `word_count`, `sentence_count`.
- R1.3 Computes per pair: whole-paper Jaccard similarity over lowercased word
  sets.
- R1.4 Computes per matched assertion pair (after Stage 3): `difflib.SequenceMatcher`
  ratio between the two quotes.
- R1.5 Does **not** compute `section_count` (ADR-011).
- R1.6 Metrics are report-only. They are merged into `comparison.yaml` at Stage 4
  and are never included in the Stage 3 prompt (ADR-013).

### Stage 2a — Slice

- R2a.1 Per paper, independently. No LLM.
- R2a.2 Count headers at each level (`#` through `######`). Pick the shallowest
  level with at least 5 headers. If no level reaches 5, use the deepest level
  present (ADR-002). The two papers may land on different levels.
- R2a.3 Emit one section file per header at the chosen level, containing that
  header and everything beneath it up to the next header at the same level.
  Deeper sub-headers travel with their parent section.
- R2a.4 Any content preceding the first chosen-level header becomes a synthetic
  **Front Matter** section, processed identically to every other section
  (ADR-003).
- R2a.5 Any section exceeding a configurable word threshold (default ~800) that
  still contains sub-headers is recursively re-cut on those sub-headers until
  every leaf is under the threshold or has no sub-headers left (ADR-004,
  ADR-005).

### Stage 2b — Summarize

- R2b.1 One LLM call per sliced section, producing a short summary of that
  section alone.
- R2b.2 Summaries accumulate in one `summary.yaml` per paper, keyed by the
  section's header title.

### Stage 2c — Extract assertions

- R2c.1 **Index (deterministic).** Split the section's markdown on blank lines
  into a flat, ordered, untyped list `blocks[0..n]`. Prose, tables, equations
  and lists are all just blocks (ADR-007).
- R2c.2 **Extract (LLM, one call per section).** Provide the section text and
  its indexed block list. Request a YAML document rooted at the section header,
  containing a list of assertions. Each assertion has a `type` and exactly one key/value
  pair whose key is `$.blocks[i]` and whose value is the verbatim quote.
- R2c.3 Allowed `type` values: `research_question`, `hypothesis`, `method`,
  `data`, `assumption`, `limitation`, `finding`, `conclusion`, `claim`.
- R2c.4 Paths are section-relative, never paper-relative (ADR-006).
- R2c.5 Per-section assertion files are folded into one per-paper tree
  `{header: {assertions: [...]}, ...}`. Assertions are never flattened across sections
  (ADR-010).

### Grounding validation

- RG.1 Deterministic step, runs after every Stage 2c extraction, not folded into
  Pydantic (ADR-008).
- RG.2 Tier 1: if `quote in blocks[i]` (substring match), mark `grounded: true`.
- RG.3 Tier 2: otherwise search every block in the section. If found, repoint
  the path to the correct index, mark `grounded: true`, and set
  `index_corrected: true` (ADR-016).
- RG.4 Tier 3: otherwise mark `grounded: false`. The assertion is retained, not
  dropped, and the pipeline does not fail (ADR-009).

### Stage 3 — Compare and interpret

- R3.1 One LLM call. Input is exactly: both papers' nested assertion trees (including
  `grounded` and `index_corrected` flags) and both `summary.yaml` files.
  Nothing else.
- R3.2 Output is a set of `matched`, `a_only`, and `b_only` records. Each record
  separates `evidence` (the quoted assertions) from `interpretation` (the model's
  reading of the relationship).
- R3.3 **Fallback** if either paper exceeds roughly 100 assertions: run in two rounds.
  Round one aligns sections from the two summary files; round two matches assertions
  within each aligned section pair, one call per pair (ADR-012, ADR-014).

### Stage 4 — Assemble and validate

- R4.1 Merge per paper: summaries, assertion trees with grounding flags, Stage 1
  metrics, and Stage 3 comparisons into one `comparison.yaml`.
- R4.2 Validate shape with a single Pydantic model. A shape violation fails the
  run loudly.
- R4.3 A `grounded: false` flag is not a shape violation and does not fail the
  run.

### Stage 4b — Write executive summary

- R4b.1 One LLM call. Input is exactly: the validated Stage 4 comparison's three
  record lists (`b_only`, `a_only`, `matched`, presented as challenger-only,
  champion-only, shared) and both papers' section summaries. Paper A is the
  champion, Paper B the challenger (ADR-018).
- R4b.2 Output follows the pyramid principle: one `governing_thought`
  (answer first), 3–4 MECE `pillars` each with a one-sentence `claim`, and
  2–4 `evidence` items per pillar, each a verbatim quote taken from the
  comparison records with a `source` (`challenger`, `champion`, `both`) and a
  one-sentence `why_it_matters`. Plus: `headline`, `recommendation`,
  `challenger_brings`, `challenger_lacks`, `shared_ground`, `who_should_care`.
- R4b.3 Weighting is explicit in the prompt: challenger-only material first,
  champion-only second, shared material last and only where needed.
- R4b.4 **Post-check (deterministic).** Every evidence quote is searched for,
  whitespace-normalised and case-folded, among the comparison's quotes. A miss
  sets `grounded: false`; the quote is kept, not dropped (as RG.4).
- R4b.5 The record counts (`challenger_only`, `champion_only`, `shared`) are
  computed in code from the comparison, never taken from the model.
- R4b.6 Shape is validated with Pydantic; fewer than 3 or more than 5 pillars
  fails the run loudly.

### Stage 5 — Render report

- R5.1 One Jinja2 template per deliverable. Template logic is limited to loops
  and conditionals.
- R5.2 Assertions with `grounded: false` receive a visible warning badge.
- R5.3 Assertions with `index_corrected: true` are visibly marked.
- R5.4 The report opens with a warning that its content is LLM-generated, and
  presents the three comparison sets in order of interest: challenger-only,
  champion-only, shared (collapsed by default). Each set is collapsible.

### Stage 5b — Render executive briefs

- R5b.1 Three templates over the same `ExecutiveSummary`, one file each:
  `brief_one_page.html` (pyramid on one printable page), `brief_abstract.html`
  (getAbstract-style: nutshell, take-aways, watch-outs, recommendation,
  evidence collapsed), `brief_decision_memo.html` (memo header, brings/lacks
  side by side, numbered argument outline).
- R5b.2 Every brief opens with the LLM-generated-content warning.
- R5b.3 Evidence with `grounded: false` receives a visible badge in every brief.
- R5b.4 `report.html` links to the three briefs.

## 5. Non-functional requirements

- **N1 Determinism where possible.** Only Stages 0, 2b, 2c, 3 and 4b call an
  LLM. Everything else is stdlib Python and must be unit-testable without
  network.
- **N2 Every LLM output is checked.** Stage 0 by the header-stripped diff
  (R0.3); Stage 2c by grounding (RG.*); Stages 2b and 3 by Pydantic shape
  validation at Stage 4; Stage 4b by evidence grounding (R4b.4) and Pydantic
  shape validation (R4b.6).
- **N3 No hard dependency on context-window size.** The fixture papers total
  roughly 9k tokens and fit comfortably in one call. Slicing exists for
  extraction accuracy, not size. The two-round Stage 3 fallback (R3.3) covers
  growth without redesign.
- **N4 Caching.** Every LLM call is keyed by a content hash so re-running the
  pipeline after a deterministic-stage change costs nothing.
- **N5 Failure policy.** Fail loudly on structural errors (Stage 0 body-text
  drift, Pydantic shape violations). Flag and continue on content-quality
  errors (a single ungrounded quote).
- **N6 Readability over cleverness.** This is a prototype that will be walked
  through in front of a group. The codebase must be explainable by reading it
  top to bottom, with no prior context. Concretely (see ADR-017):
  - One module per pipeline stage, each exposing a single public function
    whose name matches the stage (`format_paper`, `compute_metrics`,
    `slice_paper`, ...). The entry point in `run_pipeline.py` calls them in order
    and reads like the architecture diagram.
  - Plain functions operating on plain data (`str`, `list`, `dict`, and the
    Pydantic models). No classes except Pydantic models and at most one
    dataclass per module. No inheritance, no decorators beyond stdlib, no
    async, no metaprogramming.
  - Every public function has type hints and a docstring stating what goes in,
    what comes out, and which stage it belongs to.
  - Functions stay short. Target under 40 lines. Cyclomatic complexity is
    capped at 8 and enforced with `ruff` (rule `C901`).
  - Every stage writes its output to disk before the next stage reads it, so
    any stage can be run, inspected, and explained in isolation.
  - All LLM calls go through one thin wrapper in `llm_client_with_cache.py` (prompt file +
    input text → cached response). No stage module talks to an SDK directly.
  - Prompts live in `prompts/*.md` as plain text, never as Python string
    templates.

## 6. Acceptance criteria

- **A1** Running the pipeline on `lit_md/champion.md` and `lit_md/challenger.md`
  produces `report.html` with no shape errors.
- **A2** Stage 2a selects `##` for both fixture papers, yielding 12 sections for
  champion and 6 for challenger, plus a Front Matter section for challenger
  (whose `###` subtitle sits before its first `##`).
- **A3** The Stage 0 post-check passes on both fixtures. Injecting a one-word
  change into Stage 0 output causes the run to fail.
- **A4** Every assertion in the report is either `grounded: true` or carries a
  visible `grounded: false` badge. No assertion is silently dropped.
- **A5** An assertion whose block index is off by one is repointed and marked
  `index_corrected: true`, not flagged as ungrounded.
- **A6** The Stage 3 prompt contains no word counts, sentence counts, or Jaccard
  values.
- **A7** All tests under `tests/` except
  `test_stage4_assemble_and_validate_comparison.py` run with no network access.
- **A8** `run_pipeline.py` can be read top to bottom and every line maps to one box
  in the architecture diagram. A reader with no prior context can name the six
  stages from the entry point alone.
- **A9** `ruff check` passes with `C901` max-complexity set to 8. No function in
  `paper_diff/` exceeds 40 lines excluding its docstring.
- **A10** Every stage can be run individually from the CLI against the on-disk
  output of the previous stage (for example `paper-diff slice paper_a.md`), and
  the resulting files can be opened and read as plain markdown or YAML.
- **A11** Every `run` produces `executive_summary.yaml` and the three
  `brief_*.html` files beside `report.html`. Each brief opens with the
  LLM-generated warning, states the governing thought before any evidence,
  and has between 3 and 5 pillars. `paper-diff brief output/comparison.yaml
  --out x.yaml` reproduces the summary from the on-disk comparison alone.

## 7. Repository layout

Module files are named `stage<N>_<verb phrase>.py` so that a directory listing
reads as the execution order and each name says what the file does. Prompt
files and test files carry the same name as the module they belong to, so the
three can be found by one glob.

```text
paper_diff/
  pyproject.toml                                  # ruff config: C901 max-complexity = 8
  paper_diff/
    run_pipeline.py                                 # Entry point. Calls the stages below in order; reads like the diagram.
    llm_client_with_cache.py                        # The only module that touches an LLM SDK: ask(prompt_file, text) -> cached str
    stage0_format_markdown_headers_llm.py           # format_paper(raw_md) -> formatted_md, then check_body_unchanged(raw, formatted)
    stage1_compute_objective_metrics.py             # compute_metrics(md_a, md_b) -> dict (report-only)
    stage2a_slice_paper_into_sections.py            # slice_paper(md) -> list[Section] (level pick, front matter, re-cut)
    stage2b_summarize_each_section_llm.py           # summarize_section(section) -> str
    stage2c_index_section_into_blocks.py            # index_blocks(section_md) -> list[str]
    stage2c_extract_assertions_from_section_llm.py  # extract_assertions(section, blocks) -> dict
    stage2c_ground_assertions_against_blocks.py     # ground_assertions(assertions, blocks) -> dict (three-tier check)
    stage3_compare_papers_llm.py                    # compare_papers(tree_a, tree_b, summaries) -> dict
    stage4_assemble_and_validate_comparison.py      # Pydantic models + assemble(...) -> Comparison
    stage4b_write_executive_summary_llm.py          # Pydantic models + write_executive_summary(comparison) -> ExecutiveSummary
    stage5_render_html_report.py                    # render_report(comparison) -> html str
    stage5b_render_executive_briefs.py              # render_briefs(summary) -> {filename: html str}, three briefs
    cli.py                                          # Thin argparse wrapper; one subcommand per stage plus `run`
  templates/
    report.html.j2
    brief_one_page.html.j2
    brief_abstract.html.j2
    brief_decision_memo.html.j2
  prompts/
    stage0_format_markdown_headers_llm.md
    stage2b_summarize_each_section_llm.md
    stage2c_extract_assertions_from_section_llm.md
    stage3_compare_papers_llm.md
    stage3_align_sections_llm.md
    stage4b_write_executive_summary_llm.md
  tests/
    test_llm_client_with_cache.py                     # second call with same input hits cache, no network
    test_stage0_format_markdown_headers_llm.py        # header-stripped diff passes on identical body, fails on one changed word
    test_stage1_compute_objective_metrics.py
    test_stage2a_slice_paper_into_sections.py         # level pick, front matter, re-cut
    test_stage2c_index_section_into_blocks.py         # block splitting
    test_stage2c_ground_assertions_against_blocks.py  # substring hit, repoint-on-miss, flag-if-absent
    test_stage4_assemble_and_validate_comparison.py
    test_stage4b_write_executive_summary_llm.py       # counts from code, quote grounding, pillar-count validation (LLM stubbed)
    test_stage5b_render_executive_briefs.py           # three briefs render, warning present, escaping, ungrounded badge
    fixtures/pair_01/{paper_a.md, paper_b.md}
```

Module naming rule: one file per stage, one public function per file, named
as a verb phrase matching the stage. Everything else in a module is a private
helper prefixed with `_`. The comment beside each file above is its complete
public surface. Two files are not stages and carry no prefix: the entry point
and the LLM client. A side benefit of the prefixes is that no module shadows a
Python builtin (`format`, `slice`) or a common third-party name (`index`).

Every stage module that calls an LLM (directly or via `llm_client_with_cache`)
carries an `_llm` suffix: `stage0_format_markdown_headers_llm.py`,
`stage2b_summarize_each_section_llm.py`,
`stage2c_extract_assertions_from_section_llm.py`, `stage3_compare_papers_llm.py`,
`stage4b_write_executive_summary_llm.py`.
`ls paper_diff/*_llm.py` lists exactly the five network-touching stage modules;
everything else in `paper_diff/` is deterministic and importable with no
network, mirroring N1. Prompt and test filenames keep the `_llm` suffix too,
so the module, its prompt, and its test are found by one glob
(`*stage2b_summarize_each_section_llm*`).

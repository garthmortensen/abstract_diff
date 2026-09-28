# Paper Comparison Pipeline — Architecture Decision Records

Companion to `requirements.md`, which states *what* the system does. This file
records *why*. Each record follows Context → Decision → Consequences. ADR-001
through ADR-016 match the decisions log in `solutions_simple_pruned.md`;
ADR-017 onward are new to this document. `requirements.md` cites them by ID.
All records are **Accepted** unless stated otherwise.

## Architecture overview

```text
paper_a.md (raw, maybe unformatted) ─┐
paper_b.md (raw, maybe unformatted) ─┘
        │
        ▼
[0] Format markdown (LLM, 1 call/paper, idempotent)
     -> Check (stdlib): header-stripped raw == header-stripped output,
        else fail loudly
        │
        ▼
[1] Objective metrics (stdlib) ──────────────────────────────────────────┐
        │                                                                 │
        ▼                                                                 │
[2a] Pick slice level (shallowest level with ≥5 headers, else deepest)    │
     -> per-section files (+ Front Matter, + recursive re-cut)            │
        │                                                                 │
        ├─▶ [2b] Summarize each section (LLM, 1 call/section) ─▶ summary.yaml
        │                                                                 │
        └─▶ [2c] Index section into blocks (stdlib)                       │
                  -> Extract assertions per section (LLM, 1 call/section) │
                  -> assertions/<header>.yaml, {type, "$.blocks[i]": text}│
                  -> Grounding (stdlib): quote in blocks[i]? else search  │
                     section + repoint; else flag grounded: false         │
        │                                                                 │
        ▼                                                                 │
[3] Compare + interpret (LLM, 1 call): assertion trees + summaries        │
        │                                                                 │
        ▼                                                                 │
[4] comparison.yaml (assemble + Pydantic shape validation) ◀──────────────┘
    (metrics join here, for the report only)
        │
        ├─▶ [4b] Executive summary (LLM, 1 call): pyramid principle over the
        │        three record lists -> executive_summary.yaml
        │        -> Check (stdlib): each evidence quote found among the
        │           comparison's quotes, else flag grounded: false
        │             │
        │             ▼
        │        [5b] brief_one_page.html, brief_abstract.html,
        │             brief_decision_memo.html (Jinja2, one template each)
        ▼
[5] report.html (Jinja2; links to the briefs)
```

The overall shape is inherited from `solution_simple.md`: extract typed assertions
per paper, compute objective metrics, compare with one LLM call, assemble YAML,
render HTML. The decisions below cover what this version added or changed.

---

## ADR-001 — Stage 0 always runs

**Context.** Input is always a `.md` file, but sometimes it already has headers
(PDF → markdown → LLM added structure) and sometimes it is a wall of unheaded
text. A conditional "does this need formatting?" check would itself need to be
designed, tested and maintained.

**Decision.** Stage 0 runs on every input. Its prompt is idempotent: preserve
existing headers verbatim, add headers only where none exist, never reword or
reorganise body text. The call is cached by content hash.

**Consequences.** One fewer branch to get wrong. Cost on an already-formatted
paper is a single cached call. Everything downstream can assume a single input
shape. Downside: a header count is now an LLM artifact (see ADR-011), and Stage 0
output must be verified (see ADR-015).

---

## ADR-002 — Slice level chosen by header count

**Context.** The two papers must be cut into sections for per-section
processing, but they do not share a header scheme. Champion has 1 `#`, 12 `##`,
16 `###`; challenger has 1 `#`, 6 `##`, 18 `###`. A fixed level would work for
one and fail for the other on some future pair.

**Decision.** Per paper, scan from `#` downward and pick the first (shallowest)
level with at least 5 headers. If none reaches 5, use the deepest level present.
The two papers may pick different levels.

**Consequences.** Both fixture papers land on `##` (12 and 6 sections). The rule
never degrades to one giant section as long as any headers exist. Papers with
very different structures still slice sensibly. Downside: the threshold of 5 is
a heuristic, tuned against two files.

---

## ADR-003 — Synthetic Front Matter section

**Context.** Content before the first chosen-level header (a title line, a
subtitle, a stray deeper header such as challenger's `### Challenger model white
paper...` sitting above its first `##`) has to go somewhere.

**Decision.** It becomes its own synthetic "Front Matter" section, processed
through 2b and 2c exactly like any other.

**Consequences.** Nothing is misattributed to the first real section and nothing
is silently dropped. Front Matter usually yields few or no assertions, which is fine.

---

## ADR-004 — Oversized-section safety net retained

**Context.** ADR-002 picks a level with a good header count overall, but one
section at that level can still be much larger than its siblings.

**Decision.** Keep a per-section size check alongside the level-pick rule.

**Consequences.** Every section reaching 2b/2c has a bounded size regardless of
how uneven the paper's structure is. Slightly more code in
`stage2a_slice_paper_into_sections.py`.

---

## ADR-005 — Fixed word threshold with recursive re-cut

**Context.** ADR-004 needs a trigger and a behaviour.

**Decision.** A configurable word-count threshold (default ~800). Any section
over it that still has sub-headers is re-cut on those sub-headers, recursively,
until every leaf is under the threshold or has no sub-headers left.

**Consequences.** This is the only option that actually guarantees a bound. A
leaf with no sub-headers can still exceed the threshold; that is accepted rather
than splitting mid-prose.

---

## ADR-006 — Assertion paths are section-relative

**Context.** The extraction LLM sees one already-sliced section in isolation. It
structurally cannot know where that section sits in the original paper.

**Decision.** `$.blocks[i]` indexes into the section's block list, not the whole
paper's.

**Consequences.** The extractor's job stays trivial. The grounding validator
resolves against the same section-local list. Paper-level position, if ever
needed, is recoverable from the section header key.

---

## ADR-007 — Location paths address a flat, untyped block list

**Context.** The assertion path needs something to point at. Options were typed nodes
(paragraph, table, equation) requiring the LLM to classify before it can
address, or a flat list.

**Decision.** A deterministic pre-step splits each section on blank lines into
`blocks[0..n]` with no type distinction. The LLM is handed this indexed list.

**Consequences.** Indexer, LLM task and validator are all trivial. A table or
equation is just a block with an index. Downside: a block can contain several
sentences, so grounding uses substring rather than equality (see ADR-016).

---

## ADR-008 — Grounding is an explicit deterministic step

**Context.** `solution_simple.md` had one hallucination guard: `quote in
raw_text`. Moving to path-based addressing could have been asserted as
"equivalent" without any node that actually runs the check.

**Decision.** A dedicated step in `stage2c_ground_assertions_against_blocks.py`,
not folded into Pydantic,
resolves every assertion's path against its section's blocks and checks the text.

**Consequences.** The guarantee survives the redesign as running code, not a
claim. Pydantic stays a shape validator only.

---

## ADR-009 — Ungrounded assertions are flagged, not dropped

**Context.** When a quote cannot be found, the options are drop, fail, or flag.

**Decision.** Flag `grounded: false`, keep the assertion, continue the run.

**Consequences.** A false negative loses no real content. The report badges the
assertion for human review. Failing loudly is reserved for shape violations, not one
bad quote among many.

---

## ADR-010 — Assertion trees stay nested by section header

**Context.** Per-section assertion files must merge into a paper-level view. Flatten
to one list, or keep the `{header: {assertions: [...]}}` nesting?

**Decision.** Keep nesting. Never flatten.

**Consequences.** Stage 3 iterates a dict of sections as easily as a list, and
the header context lines up with `summary.yaml`, which is keyed the same way.

---

## ADR-011 — `section_count` dropped as a metric

**Context.** Once Stage 0 always runs (ADR-001), header count measures how many
headers an LLM chose to insert, not something the authors committed to.

**Decision.** Do not compute it.

**Consequences.** Stage 1 keeps only metrics that are properties of the source
text: word count, sentence count, Jaccard, per-pair difflib ratio.

---

## ADR-012 — Slicing is for accuracy, not context size

**Context.** The original framing of this plan was "no later LLM call ever holds
a whole paper." The fixture papers total ~6.7k words (~9k tokens) and fit in one
call with room to spare, so that framing was solving a problem that does not
exist here, the same criticism the plan levels at embeddings.

**Decision.** Slice anyway, but justify it correctly: per-section extraction
keeps quotes verbatim and block indices accurate because the model's attention
is on one section at a time. If size ever does bite (~100+ assertions per side), run
Stage 3 in two rounds: align sections from summaries, then match assertions within
aligned pairs.

**Consequences.** The design is justified by a real constraint. The fallback is
a second LLM round, not a redesign, and sits ahead of embeddings in the
escalation order.

---

## ADR-013 — Stage 1 metrics are not passed to Stage 3

**Context.** Word and sentence counts and a Jaccard score add nothing to the
matching task and invite filler interpretations ("Paper A is more thorough
because it is longer"). The per-pair difflib ratio cannot be an input at all: it
depends on Stage 3's own output.

**Decision.** Metrics go to Stage 4 and the report only. The Stage 3 prompt
contains assertion trees and summaries, nothing else.

**Consequences.** Cleaner comparison output. The architecture diagram's Stage 1
side-arrow lands at Stage 4.

---

## ADR-014 — No embeddings

**Context.** Earlier solution sketches included an embedding model, cosine
similarity matrix, thresholds and a matching algorithm.

**Decision.** None of it. Matching is done by the Stage 3 LLM directly.

**Consequences.** Three reasons, in order of weight:

1. Cosine similarity measures topical closeness, not the relation the report
   needs. "PD is estimated with logistic regression" and "PD is estimated with
   gradient boosting" embed almost identically, yet the useful output is that
   they conflict. The LLM returns matched, contradicting or one-sided in one
   pass; embeddings would only say "same topic" and the LLM call would still be
   needed.
2. Embeddings solve a candidate-generation problem at scale. N here is two
   papers with a few dozen assertions each.
3. They add a model dependency, a threshold to tune, and a matching algorithm:
   three new places to be wrong.

Escalation order if scale ever changes: two-round Stage 3 (ADR-012) first,
embeddings only past roughly 100 assertions per side.

---

## ADR-015 — Stage 0 output is verified by a header-stripped diff

**Context.** Stage 0 is an LLM rewrite of the whole document, and grounding
(ADR-008) validates against Stage 0's output, not the raw file. If Stage 0
silently rewords one sentence, every downstream quote is faithful to the
reworded text and nothing catches it.

**Decision.** After Stage 0, strip every header line (`^#{1,6}\s`) from both
raw input and formatted output, normalise whitespace, and assert the remainders
are identical. Mismatch fails the run loudly; the cached call can be retried
with a stricter prompt.

**Consequences.** The "never reword" prompt promise becomes verifiable. Every
LLM output in the pipeline now has a deterministic check: Stage 0 by this diff,
Stage 2c by grounding, Stages 2b and 3 by Pydantic shape validation.

---

## ADR-016 — Grounding repoints on index miss before flagging

**Context.** The Stage 2c LLM emits two things that can each be wrong: the block
index (off by one, pointing at a neighbour) and the quote (paraphrased,
trimmed, invented). A single exact check would flag correct quotes with wrong
indices as ungrounded, creating human-review noise.

**Decision.** Three tiers:

1. `quote in blocks[i]` (substring, since a block may hold several sentences) →
   `grounded: true`.
2. Else search every block in the section. Found → repoint the index, set
   `grounded: true`, record `index_corrected: true`.
3. Else `grounded: false`. The quote does not exist in the section.

**Consequences.** Most index errors become silent, visible-in-metadata repairs.
Only genuine paraphrases and hallucinations reach the human as flags. The
`index_corrected` flag keeps the repair auditable in the report.

---

## ADR-017 — Optimise the codebase for readability and explainability

**Context.** This is a prototype. Its first job is to be understood: it will be
walked through in front of a group, and the people reading it will have no
prior context. A design that is correct but needs a guided tour to follow has
failed at that job. The pipeline has a natural shape, six stages in a straight
line with one side-branch, and the code should look exactly like that shape.

**Decision.** Readability is a first-class requirement (requirements.md, N6),
ranked above performance, above generality, and above DRY when the two
conflict. The rules that follow from it:

1. **The code mirrors the diagram.** One module per stage. One public function
   per module. Module files are named `stage<N>_<verb phrase>.py` so a
   directory listing sorts into execution order and each filename says what
   the file does; the prompt file and test file for a module carry the same
   name. `run_pipeline.py` calls the stages in order and nothing else, so
   reading it top to bottom is reading the architecture diagram.
2. **Plain functions on plain data.** Stages pass `str`, `list`, `dict`, and
   Pydantic models. No classes except Pydantic models and at most one
   dataclass per module. No inheritance, no decorators beyond stdlib, no
   async, no metaprogramming, no clever comprehensions where a loop is
   clearer.
3. **Short functions, low complexity.** Target under 40 lines per function.
   Cyclomatic complexity capped at 8, enforced by `ruff` rule `C901` in
   `pyproject.toml` so it is a CI fact rather than a style aspiration.
4. **Disk between stages.** Every stage writes its output as markdown or YAML
   before the next stage reads it. Any stage can be run alone from the CLI,
   and its output can be opened and read by a human. This doubles as the
   caching layer and as the presentation aid: each artifact is a slide.
5. **One LLM boundary.** `llm_client_with_cache.py` is the only module that
   imports an SDK. Its
   single function takes a prompt file and input text and returns a cached
   string. Every stage that needs a model calls it. Swapping providers or
   adding a mock for tests touches one file.
6. **Prompts are text, not code.** `prompts/*.md` are plain files. A reviewer
   can read what the model is asked without parsing Python string formatting.
7. **Docstrings state the contract.** Every public function's docstring says
   which stage it is, what goes in, and what comes out. Type hints on every
   signature.

**Consequences.**

- Some duplication is accepted. Two stages that each need to walk a section
  tree may each contain a short loop rather than sharing an abstract walker.
- Generality is deferred. The pipeline handles exactly two papers, exactly
  markdown, exactly this stage order. Extending it means adding a module and
  a line in `run_pipeline.py`, not configuring a framework.
- Performance is not a goal. Stages run sequentially. LLM calls are not
  parallelised. The fixture papers make this a non-issue, and the disk-based
  cache makes re-runs free.
- Presentation cost drops to near zero. The demo script is: open the
  diagram, open `run_pipeline.py`, open one stage module, open its on-disk
  output. Acceptance criteria A8 through A10 in `requirements.md` make this
  checkable.
- The repo layout in `requirements.md` section 7 was adjusted to match:
  `run_pipeline.py` and `llm_client_with_cache.py` were added, every stage
  module was renamed with a `stage<N>_` prefix and a verb phrase, each
  module's public function is named in its layout comment, and `cli.py`
  gained one subcommand per stage.

## ADR-018 — Executive briefs follow the pyramid principle, in a stage of their own

**Context.** The full `report.html` lists every matched, champion-only and
challenger-only assertion. On the fixture pair that is over two hundred
records, which is the right artifact for an auditor and the wrong one for a
decision-maker who wants to know what the challenger is worth. The reader
the project is for asked for the opposite shape: the answer first, then the
reasons, then the evidence, in a format they can review in minutes.

**Decision.**

1. **A separate LLM stage (4b) after assembly, not a bigger Stage 3 prompt.**
   Stage 3 answers "which assertions correspond"; the brief answers "so what
   should I do". Mixing them would bloat a prompt that already has a
   two-round fallback, and the brief needs the *validated* comparison as its
   input so it can only ever cite quotes that survived Stage 4. Stage 4b
   consumes `comparison.yaml` and nothing else, so `paper-diff brief` can be
   re-run alone when only the summary prompt changes.
2. **The pyramid principle is the output schema, not a style note.** The
   Pydantic model *is* the pyramid: `governing_thought` at the top, 3–4
   `pillars` (MECE, ordered by importance) beneath it, 2–4 `evidence` quotes
   under each pillar. Fewer than 3 pillars is a shape error and fails the run.
   Making the structure a type means the templates need no judgement: they
   lay out what they are given, top to bottom.
3. **Champion and challenger are named, and ordered by interest.** Paper A is
   the champion (incumbent), Paper B the challenger. The prompt is told which
   is which and told that challenger-only material matters most, champion-only
   next, shared least. The same ordering was applied to `report.html`, whose
   three sets are now collapsible and open with the challenger-only set. This
   is the one place the pipeline is not symmetric in A and B, and it is
   deliberate: the question being answered is directional.
4. **Evidence is grounded, as in Stage 2c.** Every quote the model puts under a
   pillar is looked up (whitespace-normalised, case-folded) among the quotes
   in the comparison. A miss is flagged `grounded: false` and badged in every
   brief, never dropped. The record counts shown in the briefs are computed
   from the comparison in code, so the model cannot misreport them.
5. **Three templates, one data model (5b).** The same `ExecutiveSummary`
   renders as a one-page brief (pure pyramid, printable), a getAbstract-style
   abstract (nutshell, take-aways, watch-outs, evidence collapsed), and a
   decision memo (header table, brings/lacks side by side, numbered argument
   outline). R5.1's "one Jinja2 template" becomes "one template per
   deliverable"; the constraint that matters, template logic limited to loops
   and conditionals, is unchanged. `report.html` links to all three.
6. **Every rendered page opens with an LLM-generated-content warning.** The
   briefs are two LLM hops from the source text (comparison, then summary),
   which is exactly when a confident-looking page is most dangerous.

**Consequences.**

- One more LLM call per run, over roughly the comparison's records (about 25k
  tokens on the fixtures), cached like every other call.
- `ls paper_diff/*_llm.py` now lists five modules, not four; N1 and N2 in
  `requirements.md` were updated to include Stage 4b and its grounding check.
- Stage 3's output format moved from YAML to JSON at the same time (the model
  occasionally failed YAML's single-quote doubling rule on quotes containing
  apostrophes; JSON string escaping is far more reliable). Stage 4b uses JSON
  from the start for the same reason. Input payloads to both stages remain
  YAML, which is fine to *read* and was never the problem.
- The two-round Stage 3 fallback (R3.3) gained its own prompt file
  (`stage3_align_sections_llm.md`); it had been reusing the comparison prompt,
  which never described the alignment task.

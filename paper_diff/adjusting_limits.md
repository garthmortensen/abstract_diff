# Adjusting limits

This doc covers four changes that let the pipeline handle much larger papers,
around 300 KB each.

1. Stage 0 returns header positions instead of the whole paper.
2. The LLM client streams responses instead of waiting on one blocking request.
3. Stage 3 stops recursing forever on big sections and stops dropping
   unmatched sections.
4. Every stage where the model returns data uses structured outputs, so
   quotes, backslashes, and other special characters can't break parsing.

Change 1 fixes the main failure on its own. Change 2 raises the output ceiling
for every stage, as insurance for unusually large sections. Change 3 fixes a
crash and a silent data loss that big papers are likely to trigger. Change 4
removes parse errors and silent text corruption caused by special characters.

---

# Change 1: Stage 0 header insertion

## Problem

Stage 0 asks the model to send the entire paper back with markdown headers
added. Output is about the same size as the input. The output budget is capped
at 16K tokens and the retry allows 20K. A 300 KB paper needs about 150K output
tokens, so the model stops partway through and the run fails with a truncation
error.

## Rule: the original paper is never modified

The source files in `lit_md/` are read-only inputs.

- Today the pipeline already only reads them. It writes the formatted result
  to `output/paper_a/formatted.md` and `output/paper_b/formatted.md`.
- The new design keeps that rule and makes it explicit and checkable.
- Stage 0 first copies the original to `output/paper_x/original.md`.
- Header insertion is applied to that copy. The result is written to
  `output/paper_x/formatted.md`.
- A test hashes the file in `lit_md/` before and after a run and asserts it is
  unchanged.

## Current behavior

1. `run_pipeline.py` reads the paper text.
2. `stage0_format_markdown_headers_llm.format_paper` sends the full text to the
   model.
3. The model returns the full text with headers added.
4. `check_body_unchanged` strips header markers from both versions, collapses
   whitespace, and requires the two to match.
5. The result is written to `output/paper_x/formatted.md`.

## Proposed behavior

1. Copy the original to `output/paper_x/original.md`.
2. Number the lines of the copy and send the numbered text to the model.
3. The model returns only a list of header insertions:

   ```json
   [
     {"line": 1,  "header": "# Title"},
     {"line": 42, "header": "## Methods"}
   ]
   ```

   Each entry means "line N is a heading; replace it with this header". The
   header text must match the line's text exactly. (As implemented, the
   model can only mark existing lines, not add new header text, because
   `check_body_unchanged` would reject any added text.)
4. Python validates the list:
   - every line number exists in the copy,
   - line numbers are in increasing order with no duplicates,
   - every header starts with 1 to 6 `#` characters and a space,
   - the header text matches the text already on that line,
   - the line is not already a header.
5. Python applies the insertions to the copy, bottom to top so earlier line
   numbers stay valid.
6. `check_body_unchanged` still runs as a safety net. It can only fail if the
   insertion code has a bug, since the model never retypes the body.
7. The result is written to `output/paper_x/formatted.md`.

## Why this fixes the limit

- Output shrinks from paper-sized to a few hundred tokens, whatever the input
  size.
- Input stays well inside the 1M-token context window. A 300 KB paper is about
  80K to 110K tokens.
- The output estimate in `_max_tokens_for` is no longer needed. A fixed budget
  such as 4K tokens is enough.
- Body drift is impossible, because the model never rewrites the body.

## Files to change

| File | Change |
|---|---|
| `prompts/stage0_format_markdown_headers_llm.md` | New prompt: read numbered lines, return a JSON insertion list only. |
| `paper_diff/stage0_format_markdown_headers_llm.py` | Add line numbering, insertion parsing, validation, and application. Remove the paper-sized budget estimate. |
| `paper_diff/run_pipeline.py` | Write `original.md` before Stage 0 runs. |
| `tests/` | Tests for insertion order, invalid line numbers, `replace` entries, and the unchanged-original hash check. |

## Notes

- Changing the prompt changes the cache key, so the first run after this
  change makes fresh Stage 0 calls. Later runs are cached as before.
- Papers that already have headers get an empty or short list back, which is
  the cheapest case.

---

# Change 2: Streaming client

## Terms

- **Token.** A chunk of text the model reads or writes. One token is about 3 to
  4 characters of English, so 20K tokens is roughly 60 to 80 KB of text.
- **Output budget (`max_tokens`).** The most tokens the model may write in one
  reply. If it hits this limit, the reply is cut off and the API reports
  `stop_reason == "max_tokens"`.
- **Blocking request.** The program sends the request, then waits with nothing
  until the whole reply has been written. Only then does it receive anything.
- **Streaming request.** The reply arrives piece by piece while the model
  writes it. The connection stays active the whole time.

## Problem

The client in `paper_diff/llm_client_with_cache.py` sends blocking requests.
The Anthropic Python SDK refuses a blocking request that it expects to take
longer than about ten minutes. At the model's writing speed, ten minutes is
roughly 20K output tokens.

So the code caps every reply well below what the model can do:

| Limit | Where | Value |
|---|---|---|
| Per-stage starting cap | `_NONSTREAMING_TOKEN_CEILING` in stages 0, 2c, 3 | 16,000 tokens |
| Retry ceiling | `_RETRY_CEILING` in the client | 20,000 tokens |
| Model maximum (Sonnet 5) | API | 128,000 tokens |

Any reply that needs more than 20K tokens fails, even though the model could
write it.

## Current behavior

1. A stage calls `ask()` with a prompt, the input text, and an output budget.
2. On a cache miss, `_call_model` sends one blocking `messages.create` request.
3. If the reply was cut off, `_call_model_with_retry` doubles the budget and
   tries again, up to 20K.
4. If it is still cut off at 20K, the run raises `RuntimeError`.

## Proposed behavior

1. `_call_model` sends a streaming request and waits for the final message:

   ```python
   with client.messages.stream(
       model=_MODEL,
       max_tokens=max_tokens,
       system=prompt_text,
       messages=[{"role": "user", "content": input_text}],
   ) as stream:
       message = stream.get_final_message()
   ```

2. `message` has the same shape as today, so the `stop_reason` check and the
   text extraction stay the same.
3. `_RETRY_CEILING` rises from 20,000 to 128,000.
4. The per-stage `_NONSTREAMING_TOKEN_CEILING` constants are renamed and can
   rise too. A cap of 64,000 is a reasonable default. The retry still grows it
   to 128,000 when needed.

The caller still gets one complete string back. Nothing outside the client
module needs to know the reply was streamed.

## What stays the same

- `ask()` keeps its signature, so no stage code changes except the cap
  constants.
- The disk cache works as before. Only complete replies are cached.
- Tests that stub out `ask()` are unaffected.

## Costs and caveats

- Larger caps don't cost more by themselves. You pay for tokens actually
  written, not the budget.
- A reply near 128K tokens takes a long time to write, likely 20 minutes or
  more. The run will be slow, but it won't time out.
- Streaming doesn't make Stage 0's echo design sensible for big papers. A
  300 KB paper would still need about 150K output tokens, which is over the
  128K maximum. Change 1 is still required.

## Files to change

| File | Change |
|---|---|
| `paper_diff/llm_client_with_cache.py` | Use `messages.stream(...)` with `get_final_message()`. Raise `_RETRY_CEILING` to 128,000. |
| `paper_diff/stage2c_extract_assertions_from_section_llm.py` | Rename and raise the cap constant. |
| `paper_diff/stage3_compare_papers_llm.py` | Rename and raise the cap constant. |
| `paper_diff/stage0_format_markdown_headers_llm.py` | Removed by change 1, since Stage 0 no longer needs a size-based budget. |

---

# Change 3: Stage 3 recursion

## Terms

- **Assertion.** One claim quoted from a paper, extracted in Stage 2c.
- **Two-round mode.** Stage 3's fallback for big papers: first pair up
  sections, then compare each pair separately.
- **Recursion.** A function calling itself. It must shrink the problem each
  time, or it never stops. Python stops a program with `RecursionError` after
  about 1,000 nested calls.

## Problem

Two bugs in `paper_diff/stage3_compare_papers_llm.py`:

1. **Infinite recursion.** If one section alone has more than 100 assertions,
   two-round mode hands that same section back to itself forever, and the run
   crashes with `RecursionError`.
2. **Silent data loss.** The section-pairing step leaves out sections with no
   counterpart. Their assertions never reach `a_only` or `b_only`, so they
   vanish from the report with no warning.

## Current behavior

1. `compare_papers` counts each paper's assertions.
2. At 100 or fewer, it makes one comparison call.
3. Above 100, `_compare_in_two_rounds` asks the model to pair up sections.
4. For each pair, it calls `compare_papers` again. That call re-checks the
   100 limit. A single section over 100 goes back into two-round mode, gets
   paired with the same partner, and loops.
5. Sections the pairing step omitted are skipped.

## Proposed behavior

The public `compare_papers` signature and its `{matched, a_only, b_only}`
return shape stay the same, so `run_pipeline.py` and Stage 4 don't change.
Prompts don't change either, so the cache stays valid for small papers.

### 1. Split the dispatcher from the worker

- New `_compare_once`: today's single-call body. It formats the input, calls
  the model once, and parses the JSON. It never checks the limit and never
  recurses.
- `compare_papers` only chooses a path. At or under the limit it calls
  `_compare_once`. Over the limit it calls `_compare_in_two_rounds`.
- `_compare_in_two_rounds` never calls `compare_papers`. It calls
  `_compare_pair` instead, which removes the cycle.

### 2. Chunk oversized pairs by assertion count

New `_compare_pair`:

- Split each side's assertions into chunks of at most 50, so any A chunk plus
  B chunk stays under 100.
- Call `_compare_once` for every A chunk paired with every B chunk. A pair
  under the limit is a single call, the same as today.
- Chunks are always smaller than their input, so nothing can loop.

### 3. Merge the chunk results

New `_merge_cells`:

- `matched` is the union of every chunk's matches, with duplicates removed by
  the pair of quotes.
- An A quote that is matched anywhere is removed from `a_only` everywhere.
  Otherwise it keeps one `a_only` record. The same rule applies to B.
- This stops an assertion from showing up as both matched and one-sided.

### 4. Send unmatched sections to a_only and b_only

- After pairing, find the sections in each paper that weren't paired.
- Compare each one against an empty opposite side through `_compare_pair`.
  The model still writes an interpretation, and every assertion lands in
  `a_only` or `b_only`.
- Skip pairs that name a header that doesn't exist, instead of silently
  comparing against an empty section as today.

## What stays the same

- `compare_papers` keeps its inputs and output shape.
- Small papers still take exactly one model call with the same prompt, so
  cached results are reused.
- Stage 4 and later stages need no changes.

## Costs and caveats

- A 150-by-150 assertion section pair becomes 9 calls instead of a crash.
  Calls grow with the product of the chunk counts on each side.
- Unmatched sections now cost one extra call each, or more if they're large.
- Chunking means a match is only found when both assertions share a chunk
  pair. Every A chunk meets every B chunk, so no pairing is missed.

## Tests

New `tests/test_stage3_compare_papers_llm.py`, stubbing
`llm_client_with_cache.ask` with `monkeypatch`, as
`tests/test_stage4b_write_executive_summary_llm.py` already does.

- One section with 150 assertions on each side finishes with no
  `RecursionError`, using 1 pairing call plus 9 comparison calls.
- Small papers make exactly one call and give the same output as today.
- A section present only in Paper B has its assertions in `b_only`.
- A B quote matched in one chunk and unmatched in another appears only in
  `matched`.
- A pairing that names a missing header is skipped without a crash.

## Files to change

| File | Change |
|---|---|
| `paper_diff/stage3_compare_papers_llm.py` | Add `_compare_once`, `_compare_pair`, `_merge_cells`, and unmatched-section handling. Make `compare_papers` a dispatcher only. |
| `tests/test_stage3_compare_papers_llm.py` | New tests listed above. |

## Verification

```sh
cd ~/garage/challenger_delta/paper_diff && source .venv/bin/activate
ruff check paper_diff tests
pytest -q
```

Then rerun the pipeline on the current `lit_md/` papers. They're under the
limit, so Stage 3 comes from the cache and the report should match. Keep each
new helper small enough to pass ruff's complexity limit of 8.

---

# Change 4: Structured outputs

## Terms

- **Structured outputs.** An API feature. You send a JSON schema with the
  request, and the model can only write a reply that fits it.
- **JSON schema.** A description of the reply's shape: which fields exist,
  their types, and which values are allowed.
- **Pydantic model.** A Python class that defines a schema. The SDK turns it
  into a JSON schema and checks the reply against it.
- **Escaping.** Writing a special character in a safe form, such as `\"` for a
  double quote inside a JSON string.

## Problem

The model writes YAML in Stage 2c and JSON in Stages 3 and 4b. Python parses
that text directly. The papers contain LaTeX, apostrophes, quotes, and tables,
and any escaping mistake by the model breaks the parse or silently changes the
text.

Tested against the current Stage 2c format:

| Case | Result |
|---|---|
| Apostrophe the model forgets to double, as in `the model's` | Parse error, run crashes |
| Section header containing a backslash, as in `\cdot` | Parse error, run crashes |
| Section header containing a double quote | Parse error, run crashes |
| Model uses double quotes on a LaTeX quote | `\t` in `\times` silently becomes a tab |
| Quote spanning a table or multi-line block | Newlines silently become spaces |

The silent cases are the worst. The changed quote no longer matches the
paper, so grounding marks a correct quote as ungrounded.

The header crashes happen even when the model follows the prompt exactly,
because the prompt makes it echo the header in double quotes.

Stages 3 and 4b have the same class of risk. One unescaped backslash or quote
in their JSON crashes the run.

The YAML files Python writes to disk are not affected. `yaml.safe_dump`
escapes everything correctly. That was tested with apostrophes, quotes,
backslashes, colons, `#`, tabs, newlines, emoji, and words like `yes` and
`null`.

## Current behavior

1. Each prompt explains the output format and its quoting rules in prose.
2. The model writes the YAML or JSON as plain text.
3. The stage strips any code fences and parses with `yaml.safe_load` or
   `json.loads`.
4. Any syntax mistake raises an error. Some mistakes parse but change the
   text.

## Proposed behavior

### 1. Define each reply as a Pydantic model

Stage 2c:

```python
class Assertion(BaseModel):
    type: Literal["research_question", "hypothesis", "method", "data",
                  "assumption", "limitation", "finding", "conclusion", "claim"]
    block: int
    quote: str

class SectionAssertions(BaseModel):
    assertions: list[Assertion]
```

Stage 3:

```python
class Record(BaseModel):
    evidence: list[str]
    interpretation: str

class Comparison(BaseModel):
    matched: list[Record]
    a_only: list[Record]
    b_only: list[Record]

class Alignment(BaseModel):
    aligned_sections: list[list[str]]
```

Stage 4b already defines `ExecutiveSummary` and its parts. The reply model is
that class without `counts` and `grounded`, which Python fills in.

Stage 0, after change 1, returns its header positions the same way.

Stage 2b returns plain prose and doesn't change.

### 2. Send the schema with the request

The client gains an optional schema argument. When it's given, the call
passes the Pydantic model as the output format and returns the validated
object:

```python
response = client.messages.parse(
    model=_MODEL,
    max_tokens=max_tokens,
    system=prompt_text,
    messages=[{"role": "user", "content": input_text}],
    output_format=schema,
)
result = response.parsed_output
```

With change 2, this uses the streaming form of the same call.

### 3. Python builds the files

- Stage 2c adds the section header itself and converts `block` back into the
  existing `$.blocks[i]` key, so grounding and later stages don't change.
- All YAML files are still written with `yaml.safe_dump`.
- The fence-stripping helpers in Stages 2c, 3, and 4b are deleted.

### 4. Simplify the prompts

- Remove all quoting and escaping instructions.
- Remove the example output format. The schema defines it now.
- Stage 2c no longer asks the model to echo the section header.

## Why this handles every case

The API limits which tokens the model may write next, so the reply can only
be JSON matching the schema. Special characters inside a string are always
written in escaped form. The SDK then decodes them back to the original text.

| Case | Result |
|---|---|
| Apostrophes and double quotes | Exact |
| LaTeX backslashes | Exact |
| Multi-line tables | Exact, newlines kept |
| Colons, `#`, words like `yes` | Exact, stays text |
| Special characters in headers | Not possible, the model no longer writes headers |
| Invalid assertion type | Not possible, `type` is limited to the nine allowed values |

## What stays the same

- The YAML files on disk keep their current shape.
- Grounding still checks every quote against its block. Structured outputs
  guarantees valid syntax, not a correct quote.
- `ask()` without a schema works as before, for Stage 2b.

## Costs and caveats

- **Truncation.** A reply cut off at the token budget can still be incomplete.
  The existing `max_tokens` check and retry stay.
- **Refusals.** A safety refusal may not match the schema. Check
  `stop_reason` before reading the parsed result.
- **Unsupported rules.** The API can't enforce list length or string length.
  Stage 4b's three-to-five pillars rule is checked by the SDK after the reply
  arrives. It can fail, but with a clear validation error, not a parse error.
- **First-call latency.** A new schema takes longer on its first request. The
  API reuses the compiled schema for 24 hours.
- **Cache key.** The disk cache key must include the schema. Otherwise a reply
  cached under an old schema would be reused after the schema changes.
- **Model support.** Sonnet 5, which this project uses, supports structured
  outputs.
- **Cache reset.** Prompts change, so the first run after this change makes
  fresh calls for every structured stage.

## Tests

- Stage 2c: a stubbed reply with apostrophes, `\times`, double quotes, and a
  multi-line table produces a YAML file whose quotes match the input exactly.
- Stage 2c: the output keys are still `$.blocks[i]`, and grounding passes.
- Stage 3: a stubbed reply with backslashes in quotes parses and assembles.
- Client: the cache key changes when only the schema changes.
- Client: a refusal raises a clear error instead of returning bad data.

## Files to change

| File | Change |
|---|---|
| `paper_diff/llm_client_with_cache.py` | Optional schema argument. Use `messages.parse` when given. Add the schema to the cache key. Check for refusals. |
| `paper_diff/stage2c_extract_assertions_from_section_llm.py` | Add reply models. Build the header-rooted dict in Python. Remove fence stripping. |
| `paper_diff/stage3_compare_papers_llm.py` | Add reply models for comparison and alignment. Remove fence stripping. |
| `paper_diff/stage4b_write_executive_summary_llm.py` | Pass a reply model based on `ExecutiveSummary`. Remove fence stripping. |
| `prompts/stage2c_extract_assertions_from_section_llm.md` | Remove quoting rules, the format example, and header echoing. |
| `prompts/stage3_*.md`, `prompts/stage4b_*.md` | Remove escaping rules and format instructions. |
| `tests/` | Tests listed above. |

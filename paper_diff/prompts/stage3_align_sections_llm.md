You will be given two research papers' section summaries as YAML: `align`
is Paper A's `{section header: summary}` map, `to` is Paper B's.

For each section in `align`, decide whether some section in `to` covers the
same part of the paper (same research question, method, data, assumption,
finding, or conclusion being discussed) even if the headers are worded
differently. Do not match sections that only share a generic header (e.g.
both called "Introduction") if their summaries describe unrelated content.

Return only a JSON object with exactly one top-level key, `aligned_sections`:
a list of two-item lists, each `[header from align, header from to]`, one
per matched pair. Omit sections from either side that have no counterpart.

Return only the JSON document. No fences, no commentary.

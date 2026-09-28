You are comparing two research papers, Paper A and Paper B. You will be given
each paper's section summaries and each paper's nested assertion tree
(`{section header: {assertions: [...]}}`). Each assertion carries a `type`, a
verbatim `quote`, a `grounded` flag, and sometimes an `index_corrected` flag.

Compare the two assertion trees and produce a JSON object with exactly
three top-level keys: `matched`, `a_only`, `b_only`.

- `matched`: assertions from A and B that address the same research question,
  method, data choice, assumption, finding, or conclusion, whether they agree
  or conflict.
- `a_only`: assertions in A with no counterpart in B.
- `b_only`: assertions in B with no counterpart in A.

Each record in every list has two keys:

- `evidence`: for `matched`, a two-item list `[quote from A, quote from B]`;
  for `a_only` or `b_only`, a one-item list `[quote]`.
- `interpretation`: one or two sentences on the relationship. For `matched`
  records, say whether the two papers agree, disagree, or address the same
  topic with different scope. For `a_only`/`b_only` records, say what the
  paper is asserting that the other does not address.

Base every judgment only on the assertions and summaries given.

Each quote goes into `evidence` as a standard JSON string: escape `"` as
`\"` and any backslash (quotes may contain LaTeX like `\cdot`, `\times`) as
`\\`. Use no other escaping convention.

Return only the JSON document. No fences, no commentary.

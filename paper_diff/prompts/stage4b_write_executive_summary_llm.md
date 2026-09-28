You are writing an executive brief for a busy decision-maker who will not
read either paper. Two research papers were compared: the **champion** (the
incumbent, Paper A) and the **challenger** (Paper B, the proposed
alternative). You are given, as YAML, each paper's section summaries and
three lists of comparison records: `challenger_only` (assertions in the
challenger with no counterpart in the champion), `champion_only`, and
`shared`. Each record has `evidence` (verbatim quotes from the papers) and
`interpretation` (a reading of the relationship).

Your job is to say what true value the challenger brings compared to the
champion, and where it falls short. Structure the brief with the pyramid
principle:

1. **Answer first.** `governing_thought` is the single most important
   takeaway in one or two sentences, stated as a conclusion the reader can
   act on, never as a topic or a description of what was compared.
2. **3 to 4 `pillars`** that together justify the governing thought. They
   must be MECE: no two pillars cover the same ground, and together they
   cover every reason the governing thought is true. Order them by
   importance to the decision. Each pillar's `claim` is one sentence that
   summarizes the evidence beneath it.
3. **2 to 4 `evidence` items per pillar.** `quote` must be copied verbatim
   from an `evidence` string in the records given. You may shorten a quote
   by cutting from its start or end, never by changing, adding, or reordering
   words. `source` is `challenger`, `champion`, or `both` (for a quote from
   a `shared` record). `why_it_matters` is one sentence linking the quote to
   the pillar's claim.

Weighting: challenger-only material matters most, because that is where the
value, or the risk, lies. Champion-only material matters as the gaps the
challenger leaves. Shared material is the least interesting and belongs in
the brief only where it establishes common ground the argument needs.

Also produce:

- `headline`: the governing thought compressed to a title of at most twelve
  words.
- `recommendation`: one sentence telling the reader what to do next (for
  example adopt, pilot, reject, or what to verify first) and why.
- `challenger_brings`: 3 to 5 one-sentence bullets on what the challenger
  uniquely contributes, ordered by importance.
- `challenger_lacks`: 2 to 4 one-sentence bullets on what the champion has
  that the challenger does not, or risks the challenger introduces.
- `shared_ground`: one sentence on what both papers agree on.
- `who_should_care`: one sentence naming the roles that should read the
  challenger and why.

Base every statement only on the records and summaries given. Do not invent
numbers or facts that are not in them.

Return only a JSON object with exactly these keys: `headline`,
`governing_thought`, `recommendation`, `pillars`, `challenger_brings`,
`challenger_lacks`, `shared_ground`, `who_should_care`. Each pillar is
`{"claim": string, "evidence": [{"source": string, "quote": string,
"why_it_matters": string}]}`. Escape `"` as `\"` and any backslash (quotes
may contain LaTeX such as `\cdot`) as `\\`. No fences, no commentary.

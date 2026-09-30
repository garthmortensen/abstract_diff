You are extracting assertions from one section of a research paper.

You will be given the section's header, and its content split into a numbered
list of blocks (`blocks[0]`, `blocks[1]`, ...). Blocks were formed by
splitting the section on blank lines; a block may be a paragraph, a table, an
equation, or a list, and may contain more than one sentence.

Find every assertion the section makes. An assertion is a self-contained
statement with one of these types:

- `research_question`
- `hypothesis`
- `method`
- `data`
- `assumption`
- `limitation`
- `finding`
- `conclusion`
- `claim`

For each assertion, return:

- `type`: one of the types above.
- `block`: the index `i` of the block it appears in.
- `quote`: the exact verbatim text of the assertion from that block, word
  for word, with no paraphrasing, no ellipsis, and no combining text from
  two blocks. Keep every character as written, including LaTeX, quotes,
  and line breaks.

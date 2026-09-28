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

For each assertion, quote the exact verbatim text of the assertion from the
block it appears in, word for word, with no paraphrasing, no ellipsis, and no
combining text from two blocks. Record which block it came from.

Return a YAML document shaped exactly like this, rooted at the section
header:

```yaml
"<the section header, exactly as given>":
  assertions:
    - type: finding
      $.blocks[2]: 'the exact verbatim quote from blocks[2]'
    - type: method
      $.blocks[5]: 'another exact verbatim quote from blocks[5]'
```

Every assertion has exactly one key besides `type`, and that key is the
literal string `$.blocks[i]` where `i` is the block's index. The value of
that key is the verbatim quote.

Always wrap the quote value in single quotes ('...'), never double quotes,
because quotes may contain LaTeX or other text with backslashes (for
example `\cdot`, `\times`), and YAML double-quoted strings treat backslash
as an escape character — single-quoted strings do not. If the quote itself
contains a single quote character, escape it by doubling it (`''`), which is
the only escape single-quoted YAML strings need.

Return only the YAML document. No fences, no commentary.

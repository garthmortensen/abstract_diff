You are finding the headings in one research paper. You will be given the
full text with every line prefixed by its line number, as `12: text`.

Find every line that is clearly a section heading (a title, an abstract
label, a numbered section like "3. Data", a subsection label) but is not
already a markdown header (does not already start with `#` characters).

For each one, return an insertion with:

- `line`: the line number.
- `header`: that line's text, exactly as written, with the appropriate
  number of `#` characters (1 to 6) and one space in front of it. Choose a
  level consistent with the sibling headers already in the document.

Rules:

1. Never include a line that is already a markdown header. Existing headers
   are never reworded, renumbered, promoted, or demoted.
2. The text after the `#` characters must match the line's text exactly. Do
   not reword, shorten, or fix it. Do not include the line-number prefix.
3. Only mark lines that are headings. Body text, table rows, equations,
   list items, and HTML comments are never headings.
4. List insertions in increasing line order, each line at most once.
5. If the document already has headers throughout, return an empty list.

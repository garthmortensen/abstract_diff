from paper_diff.stage2a_slice_paper_into_sections import slice_paper


def _headers_md(n: int, level: str = "##") -> str:
    return "\n\n".join(f"{level} Section {i}\n\nSome content for section {i}." for i in range(n))


def test_picks_shallowest_level_with_at_least_five_headers():
    md = "# Title\n\n" + _headers_md(5)
    sections = slice_paper(md)
    assert [s.header for s in sections] == [f"Section {i}" for i in range(5)]
    assert all(s.level == 2 for s in sections)


def test_falls_back_to_deepest_level_present_when_none_reach_five():
    md = "# Title\n\n" + _headers_md(2)
    sections = slice_paper(md)
    assert [s.header for s in sections] == ["Section 0", "Section 1"]
    assert all(s.level == 2 for s in sections)


def test_front_matter_created_when_prefix_has_a_header_beyond_the_title():
    md = "# Title\n\n### A Subtitle\n\nSome preamble text.\n\n" + _headers_md(5)
    sections = slice_paper(md)
    assert sections[0].header == "Front Matter"
    assert "Subtitle" in sections[0].content
    assert [s.header for s in sections[1:]] == [f"Section {i}" for i in range(5)]


def test_no_front_matter_when_prefix_is_only_a_lone_title():
    md = "# Title\n\nA byline with no sub-header.\n\n" + _headers_md(5)
    sections = slice_paper(md)
    assert [s.header for s in sections] == [f"Section {i}" for i in range(5)]


def test_no_front_matter_when_document_starts_with_chosen_level_header():
    md = _headers_md(5)
    sections = slice_paper(md)
    assert [s.header for s in sections] == [f"Section {i}" for i in range(5)]


def test_oversized_section_is_recursively_recut_on_sub_headers():
    part_one = "### Part One\n\n" + "word " * 10
    part_two = "### Part Two\n\n" + "word " * 10
    section = f"## Big Section\n\n{part_one}\n\n{part_two}"
    md = "# Title\n\n" + _headers_md(4) + "\n\n" + section
    sections = slice_paper(md, word_threshold=15)
    big_section_children = [s for s in sections if s.header in ("Part One", "Part Two")]
    assert len(big_section_children) == 2
    assert all(s.level == 3 for s in big_section_children)
    assert not any(s.header == "Big Section" for s in sections)


def test_leaf_with_no_sub_headers_stays_oversized():
    oversized = "## Big Section\n\n" + "word " * 50
    md = "# Title\n\n" + _headers_md(4) + "\n\n" + oversized
    sections = slice_paper(md, word_threshold=15)
    big = [s for s in sections if s.header == "Big Section"]
    assert len(big) == 1
    assert len(big[0].content.split()) > 15

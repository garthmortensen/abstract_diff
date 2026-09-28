from paper_diff.stage2c_index_section_into_blocks import index_blocks


def test_splits_on_blank_lines():
    section_md = "## Header\n\nFirst paragraph.\n\nSecond paragraph.\n\nThird paragraph."
    blocks = index_blocks(section_md)
    assert blocks == ["## Header", "First paragraph.", "Second paragraph.", "Third paragraph."]


def test_multiple_blank_lines_are_treated_as_one_separator():
    section_md = "## Header\n\n\n\nFirst paragraph.\n\n\nSecond paragraph."
    blocks = index_blocks(section_md)
    assert blocks == ["## Header", "First paragraph.", "Second paragraph."]


def test_table_is_a_single_block():
    section_md = "## Header\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n\nFollowing text."
    blocks = index_blocks(section_md)
    assert blocks == ["## Header", "| a | b |\n| --- | --- |\n| 1 | 2 |", "Following text."]


def test_empty_section_yields_no_blocks():
    assert index_blocks("   \n\n  \n") == []

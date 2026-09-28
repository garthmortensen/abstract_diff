import pytest

from paper_diff.stage0_format_markdown_headers_llm import check_body_unchanged


def test_identical_body_passes():
    raw = "# Title\n\nSome body text that stays the same.\n"
    formatted = "# Title\n\nSome body text that stays the same.\n"
    check_body_unchanged(raw, formatted)  # should not raise


def test_added_header_with_unchanged_body_passes():
    raw = "Title\n\nSome body text with no headers at all.\n"
    formatted = "# Title\n\nSome body text with no headers at all.\n"
    check_body_unchanged(raw, formatted)  # should not raise


def test_one_changed_word_fails():
    raw = "# Title\n\nSome body text that stays the same.\n"
    formatted = "# Title\n\nSome body text that changes slightly.\n"
    with pytest.raises(ValueError):
        check_body_unchanged(raw, formatted)


def test_reordered_body_fails():
    raw = "# Title\n\nFirst sentence. Second sentence.\n"
    formatted = "# Title\n\nSecond sentence. First sentence.\n"
    with pytest.raises(ValueError):
        check_body_unchanged(raw, formatted)

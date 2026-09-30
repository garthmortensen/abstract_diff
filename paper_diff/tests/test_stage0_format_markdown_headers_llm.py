import hashlib

import pytest

from paper_diff import llm_client_with_cache
from paper_diff.run_pipeline import copy_original
from paper_diff.stage0_format_markdown_headers_llm import (
    HeaderInsertion,
    HeaderInsertions,
    apply_insertions,
    check_body_unchanged,
    format_paper,
    number_lines,
)


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


def _stub_reply(monkeypatch, insertions: list[tuple[int, str]]):
    reply = HeaderInsertions(
        insertions=[HeaderInsertion(line=line, header=header) for line, header in insertions]
    )
    monkeypatch.setattr(llm_client_with_cache, "ask", lambda *a, **k: reply)


def test_number_lines_is_one_based():
    assert number_lines("a\nb") == "1: a\n2: b"


def test_insertions_mark_lines_and_keep_body(monkeypatch):
    raw = "Title\n\nBody one.\n\n2. Methods\n\nBody two with \\times and 'quotes'."
    _stub_reply(monkeypatch, [(1, "# Title"), (5, "## 2. Methods")])

    formatted = format_paper(raw)

    assert formatted == (
        "# Title\n\nBody one.\n\n## 2. Methods\n\nBody two with \\times and 'quotes'."
    )


def test_empty_insertion_list_returns_paper_unchanged(monkeypatch):
    raw = "# Title\n\nBody."
    _stub_reply(monkeypatch, [])

    assert format_paper(raw) == raw


@pytest.mark.parametrize(
    "insertions",
    [
        [(9, "# Title")],  # line out of range
        [(0, "# Title")],  # line numbers start at 1
        [(3, "## Body."), (1, "# Title")],  # out of order
        [(1, "# Title"), (1, "# Title")],  # duplicate
        [(1, "Title")],  # no marker
        [(1, "####### Title")],  # too many markers
        [(1, "# A Different Title")],  # reworded
    ],
)
def test_invalid_insertions_are_rejected(insertions):
    raw = "Title\n\nBody."
    with pytest.raises(ValueError):
        apply_insertions(
            raw, [HeaderInsertion(line=line, header=header) for line, header in insertions]
        )


def test_existing_header_cannot_be_changed():
    with pytest.raises(ValueError):
        apply_insertions("# Title\n\nBody.", [HeaderInsertion(line=1, header="## Title")])


def test_pipeline_copies_the_original_and_never_modifies_it(tmp_path):
    source = tmp_path / "lit_md" / "paper.md"
    source.parent.mkdir()
    source.write_text("Title\n\nBody.")
    before = hashlib.sha256(source.read_bytes()).hexdigest()

    copy = copy_original(source, tmp_path / "output" / "paper_a")
    copy.write_text("# Title\n\nBody.")

    assert copy == tmp_path / "output" / "paper_a" / "original.md"
    assert hashlib.sha256(source.read_bytes()).hexdigest() == before

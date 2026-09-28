from paper_diff.stage2c_ground_assertions_against_blocks import ground_assertions

_BLOCKS = [
    "## Method",
    "We use ordinary least squares regression to estimate the coefficients.",
    "The training sample covers 2015 through 2022.",
]


def _tree(path_key: str, quote: str) -> dict:
    return {"Method": {"assertions": [{"type": "method", path_key: quote}]}}


def test_substring_hit_is_grounded_true():
    tree = _tree("$.blocks[1]", "ordinary least squares regression")
    result = ground_assertions(tree, _BLOCKS)
    assertion = result["Method"]["assertions"][0]
    assert assertion["grounded"] is True
    assert assertion["index_corrected"] is False
    assert assertion["$.blocks[1]"] == "ordinary least squares regression"


def test_wrong_index_is_repointed_and_marked_corrected():
    tree = _tree("$.blocks[2]", "ordinary least squares regression")
    result = ground_assertions(tree, _BLOCKS)
    assertion = result["Method"]["assertions"][0]
    assert assertion["grounded"] is True
    assert assertion["index_corrected"] is True
    assert assertion["$.blocks[1]"] == "ordinary least squares regression"
    assert "$.blocks[2]" not in assertion


def test_quote_absent_everywhere_is_flagged_ungrounded():
    tree = _tree("$.blocks[1]", "a quote that does not exist anywhere")
    result = ground_assertions(tree, _BLOCKS)
    assertion = result["Method"]["assertions"][0]
    assert assertion["grounded"] is False
    assert assertion["index_corrected"] is False


def test_assertion_is_retained_even_when_ungrounded():
    tree = _tree("$.blocks[1]", "nonexistent quote")
    result = ground_assertions(tree, _BLOCKS)
    assert len(result["Method"]["assertions"]) == 1


def test_header_key_is_preserved():
    tree = _tree("$.blocks[1]", "ordinary least squares regression")
    result = ground_assertions(tree, _BLOCKS)
    assert list(result.keys()) == ["Method"]

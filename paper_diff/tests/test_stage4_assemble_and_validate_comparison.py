import difflib

import pytest
from pydantic import ValidationError

from paper_diff.stage4_assemble_and_validate_comparison import assemble

_SUMMARY_A = {"Method": "Paper A uses linear regression."}
_SUMMARY_B = {"Method": "Paper B uses gradient boosting."}

_TREE_A = {
    "Method": {
        "assertions": [
            {
                "type": "method",
                "$.blocks[1]": "We use ordinary least squares regression.",
                "grounded": True,
                "index_corrected": False,
            }
        ]
    }
}
_TREE_B = {
    "Method": {
        "assertions": [
            {
                "type": "method",
                "$.blocks[1]": "We use gradient boosted trees.",
                "grounded": True,
                "index_corrected": False,
            }
        ]
    }
}
_METRICS = {
    "word_count_a": 100,
    "word_count_b": 90,
    "sentence_count_a": 8,
    "sentence_count_b": 7,
    "jaccard_similarity": 0.42,
}
_STAGE3_RESULT = {
    "matched": [
        {
            "evidence": [
                "We use ordinary least squares regression.",
                "We use gradient boosted trees.",
            ],
            "interpretation": "Both papers estimate the same quantity with different methods.",
        }
    ],
    "a_only": [],
    "b_only": [],
}


def test_assemble_produces_a_valid_comparison():
    comparison = assemble(_SUMMARY_A, _TREE_A, _SUMMARY_B, _TREE_B, _METRICS, _STAGE3_RESULT)

    assert comparison.paper_a_sections[0].header == "Method"
    assert comparison.paper_a_sections[0].assertions[0].type == "method"
    assert comparison.paper_a_sections[0].assertions[0].block_index == 1
    assert comparison.metrics.word_count_a == 100
    assert len(comparison.matched) == 1


def test_quote_similarity_is_computed_for_matched_records():
    comparison = assemble(_SUMMARY_A, _TREE_A, _SUMMARY_B, _TREE_B, _METRICS, _STAGE3_RESULT)

    evidence = _STAGE3_RESULT["matched"][0]["evidence"]
    expected_ratio = difflib.SequenceMatcher(None, evidence[0], evidence[1]).ratio()
    assert comparison.matched[0].quote_similarity == expected_ratio


def test_grounded_false_does_not_fail_validation():
    tree_with_ungrounded = {
        "Method": {
            "assertions": [
                {
                    "type": "claim",
                    "$.blocks[0]": "an ungrounded quote",
                    "grounded": False,
                    "index_corrected": False,
                }
            ]
        }
    }
    comparison = assemble(
        _SUMMARY_A, tree_with_ungrounded, _SUMMARY_B, _TREE_B, _METRICS, _STAGE3_RESULT
    )
    assert comparison.paper_a_sections[0].assertions[0].grounded is False


def test_invalid_assertion_type_raises_validation_error():
    bad_tree = {
        "Method": {
            "assertions": [
                {
                    "type": "not_a_real_type",
                    "$.blocks[0]": "quote",
                    "grounded": True,
                    "index_corrected": False,
                }
            ]
        }
    }
    with pytest.raises(ValidationError):
        assemble(_SUMMARY_A, bad_tree, _SUMMARY_B, _TREE_B, _METRICS, _STAGE3_RESULT)


def test_missing_metric_field_raises_validation_error():
    incomplete_metrics = dict(_METRICS)
    del incomplete_metrics["jaccard_similarity"]
    with pytest.raises(ValidationError):
        assemble(_SUMMARY_A, _TREE_A, _SUMMARY_B, _TREE_B, incomplete_metrics, _STAGE3_RESULT)

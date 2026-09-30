import pytest
from pydantic import ValidationError

from paper_diff import llm_client_with_cache
from paper_diff.stage4_assemble_and_validate_comparison import assemble
from paper_diff.stage4b_write_executive_summary_llm import (
    ExecutiveSummaryReply,
    write_executive_summary,
)

_SUMMARY_A = {"Method": "The champion uses segment-level regression."}
_SUMMARY_B = {"Method": "The challenger uses account-level hazards."}
_TREE_A = {
    "Method": {
        "assertions": [
            {
                "type": "method",
                "$.blocks[0]": "We estimate PD with a segment-conditional logistic regression.",
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
                "$.blocks[0]": "Loss is assembled as a discounted sum over monthly hazards.",
                "grounded": True,
                "index_corrected": False,
            }
        ]
    }
}
_METRICS = {
    "word_count_a": 10,
    "word_count_b": 10,
    "sentence_count_a": 1,
    "sentence_count_b": 1,
    "jaccard_similarity": 0.5,
}
_STAGE3_RESULT = {
    "matched": [
        {
            "evidence": [
                "We estimate PD with a segment-conditional logistic regression.",
                "Loss is assembled as a discounted sum over monthly hazards.",
            ],
            "interpretation": "Same quantity, different granularity.",
        }
    ],
    "a_only": [],
    "b_only": [
        {
            "evidence": ["Loss is assembled as a discounted sum over monthly hazards."],
            "interpretation": "Only the challenger discounts.",
        },
        {
            "evidence": ["The challenger reports a 4.3x dispersion ratio."],
            "interpretation": "Only the challenger reports dispersion.",
        },
    ],
}


def _pillar(quote: str) -> dict:
    return {
        "claim": "A supporting claim.",
        "evidence": [{"source": "challenger", "quote": quote, "why_it_matters": "Because."}],
    }


def _model_output(pillars: list[dict]) -> ExecutiveSummaryReply:
    return ExecutiveSummaryReply.model_validate(
        {
            "headline": "Challenger adds lifetime granularity",
            "governing_thought": "The challenger adds value.",
            "recommendation": "Pilot it.",
            "pillars": pillars,
            "challenger_brings": ["Discounting."],
            "challenger_lacks": ["A long validation window."],
            "shared_ground": "Both estimate PD.",
            "who_should_care": "Model risk.",
        }
    )


def _comparison():
    return assemble(_SUMMARY_A, _TREE_A, _SUMMARY_B, _TREE_B, _METRICS, _STAGE3_RESULT)


def test_counts_come_from_the_comparison_not_the_model(monkeypatch):
    pillars = [_pillar("discounted sum over monthly hazards")] * 3
    monkeypatch.setattr(llm_client_with_cache, "ask", lambda *a, **k: _model_output(pillars))

    summary = write_executive_summary(_comparison())

    assert summary.counts.challenger_only == 2
    assert summary.counts.champion_only == 0
    assert summary.counts.shared == 1


def test_verbatim_substring_quote_is_grounded(monkeypatch):
    pillars = [_pillar("Discounted   sum over monthly hazards")] * 3
    monkeypatch.setattr(llm_client_with_cache, "ask", lambda *a, **k: _model_output(pillars))

    summary = write_executive_summary(_comparison())

    assert all(item.grounded for pillar in summary.pillars for item in pillar.evidence)


def test_invented_quote_is_flagged_not_dropped(monkeypatch):
    pillars = [_pillar("The challenger doubles the Gini coefficient.")] + [
        _pillar("discounted sum over monthly hazards")
    ] * 2
    monkeypatch.setattr(llm_client_with_cache, "ask", lambda *a, **k: _model_output(pillars))

    summary = write_executive_summary(_comparison())

    assert summary.pillars[0].evidence[0].grounded is False
    assert summary.pillars[1].evidence[0].grounded is True
    assert len(summary.pillars) == 3


def test_fewer_than_three_pillars_fails_validation(monkeypatch):
    pillars = [_pillar("discounted sum over monthly hazards")] * 2
    monkeypatch.setattr(llm_client_with_cache, "ask", lambda *a, **k: _model_output(pillars))

    with pytest.raises(ValidationError):
        write_executive_summary(_comparison())

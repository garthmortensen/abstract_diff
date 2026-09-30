import yaml

from paper_diff import llm_client_with_cache
from paper_diff import stage3_compare_papers_llm as stage3


def _tree(header: str, prefix: str, count: int) -> dict:
    assertions = [
        {"type": "claim", f"$.blocks[{i}]": f"{prefix} quote {i}", "grounded": True}
        for i in range(count)
    ]
    return {header: {"assertions": assertions}}


def _quotes(tree: dict) -> list[str]:
    return [
        value
        for section in tree.values()
        for assertion in section["assertions"]
        for key, value in assertion.items()
        if key.startswith("$.blocks")
    ]


class _FakeModel:
    """Stands in for `ask`: aligns by a fixed list, matches quotes by number."""

    def __init__(self, aligned_sections: list[list[str]]):
        self.aligned_sections = aligned_sections
        self.calls = {"align": 0, "compare": 0}

    def __call__(self, prompt_file, input_text, max_tokens=4096, schema=None):
        if prompt_file == stage3._ALIGN_PROMPT_FILE:
            self.calls["align"] += 1
            return stage3.AlignmentReply(aligned_sections=self.aligned_sections)
        self.calls["compare"] += 1
        payload = yaml.safe_load(input_text)
        return self._compare(
            _quotes(payload["paper_a_assertions"]), _quotes(payload["paper_b_assertions"])
        )

    @staticmethod
    def _compare(quotes_a: list[str], quotes_b: list[str]) -> stage3.ComparisonReply:
        by_number_b = {q.split()[-1]: q for q in quotes_b}
        matched, a_only = [], []
        for quote in quotes_a:
            partner = by_number_b.get(quote.split()[-1])
            if partner:
                matched.append({"evidence": [quote, partner], "interpretation": "same"})
            else:
                a_only.append({"evidence": [quote], "interpretation": "only A"})
        used_b = {record["evidence"][1] for record in matched}
        b_only = [
            {"evidence": [q], "interpretation": "only B"} for q in quotes_b if q not in used_b
        ]
        return stage3.ComparisonReply(matched=matched, a_only=a_only, b_only=b_only)


def _outcomes(result: dict) -> tuple[set, set, set]:
    return (
        {tuple(r["evidence"]) for r in result["matched"]},
        {r["evidence"][0] for r in result["a_only"]},
        {r["evidence"][0] for r in result["b_only"]},
    )


def test_one_huge_section_finishes_with_bounded_calls(monkeypatch):
    fake = _FakeModel([["Results", "Results"]])
    monkeypatch.setattr(llm_client_with_cache, "ask", fake)
    tree_a, tree_b = _tree("Results", "a", 150), _tree("Results", "b", 150)

    result = stage3.compare_papers(tree_a, tree_b, {"Results": "s"}, {"Results": "s"})

    assert fake.calls == {"align": 1, "compare": 9}
    matched, a_only, b_only = _outcomes(result)
    assert len(matched) == 150
    assert a_only == set() and b_only == set()


def test_small_papers_make_exactly_one_call(monkeypatch):
    fake = _FakeModel([])
    monkeypatch.setattr(llm_client_with_cache, "ask", fake)

    result = stage3.compare_papers(_tree("M", "a", 3), _tree("M", "b", 2), {"M": "s"}, {"M": "s"})

    assert fake.calls == {"align": 0, "compare": 1}
    matched, a_only, b_only = _outcomes(result)
    assert len(matched) == 2 and a_only == {"a quote 2"} and b_only == set()


def test_section_only_in_paper_b_lands_in_b_only(monkeypatch):
    fake = _FakeModel([["Results", "Results"]])
    monkeypatch.setattr(llm_client_with_cache, "ask", fake)
    tree_a = _tree("Results", "a", 101)
    tree_b = {**_tree("Results", "b", 1), **_tree("Appendix", "extra", 3)}

    result = stage3.compare_papers(tree_a, tree_b, {}, {})

    _, _, b_only = _outcomes(result)
    assert {"extra quote 0", "extra quote 1", "extra quote 2"} <= b_only


def test_quote_matched_in_one_chunk_is_not_also_one_sided(monkeypatch):
    fake = _FakeModel([["Results", "Results"]])
    monkeypatch.setattr(llm_client_with_cache, "ask", fake)
    tree_a, tree_b = _tree("Results", "a", 120), _tree("Results", "b", 3)

    result = stage3.compare_papers(tree_a, tree_b, {}, {})

    matched, a_only, b_only = _outcomes(result)
    assert {pair[1] for pair in matched} == {"b quote 0", "b quote 1", "b quote 2"}
    assert b_only == set()
    assert len(a_only) == 117


def test_alignment_naming_a_missing_header_is_skipped(monkeypatch):
    fake = _FakeModel([["Nope", "Results"], ["Results", "Results"]])
    monkeypatch.setattr(llm_client_with_cache, "ask", fake)
    tree_a, tree_b = _tree("Results", "a", 101), _tree("Results", "b", 1)

    result = stage3.compare_papers(tree_a, tree_b, {}, {})

    matched, a_only, _ = _outcomes(result)
    assert len(matched) == 1 and len(a_only) == 100

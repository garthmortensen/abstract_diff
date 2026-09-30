import yaml

from paper_diff import llm_client_with_cache
from paper_diff.stage2a_slice_paper_into_sections import Section
from paper_diff.stage2c_extract_assertions_from_section_llm import (
    ExtractedAssertion,
    SectionAssertions,
    extract_assertions,
)
from paper_diff.stage2c_ground_assertions_against_blocks import ground_assertions

_HEADER = 'Results: the "\\cdot" model\'s view'
_BLOCKS = [
    'We find the model\'s error falls by 3 \\times 2 "points".',
    "| a | b |\n|---|---|\n| 1 | 2 |",
]


def _section() -> Section:
    return Section(header=_HEADER, level=2, content="\n\n".join(_BLOCKS))


def _stub(monkeypatch):
    reply = SectionAssertions(
        assertions=[
            ExtractedAssertion(type="finding", block=0, quote=_BLOCKS[0]),
            ExtractedAssertion(type="data", block=1, quote=_BLOCKS[1]),
        ]
    )
    monkeypatch.setattr(llm_client_with_cache, "ask", lambda *a, **k: reply)


def test_special_characters_survive_into_the_yaml_file(monkeypatch):
    _stub(monkeypatch)

    result = extract_assertions(_section(), _BLOCKS)
    round_tripped = yaml.safe_load(yaml.safe_dump(result, sort_keys=False))

    assertions = round_tripped[_HEADER]["assertions"]
    assert assertions[0] == {"type": "finding", "$.blocks[0]": _BLOCKS[0]}
    assert assertions[1] == {"type": "data", "$.blocks[1]": _BLOCKS[1]}


def test_output_keeps_block_paths_and_grounds(monkeypatch):
    _stub(monkeypatch)

    grounded = ground_assertions(extract_assertions(_section(), _BLOCKS), _BLOCKS)

    assert all(a["grounded"] for a in grounded[_HEADER]["assertions"])

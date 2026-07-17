import json
from pathlib import Path

from run_eval import load_cases


ROOT = Path(__file__).resolve().parents[1]


def test_eval_data_has_expected_distribution_and_graders():
    cases = load_cases(ROOT / "Eval_data_1.json")

    assert len(cases) == 25
    assert [case["test_case_id"] for case in cases] == [
        "S02-%03d" % index for index in range(1, 26)
    ]
    assert {len(case["graders"]) for case in cases} == {10}

    type_counts = {}
    for case in cases:
        type_counts[case["type"]] = type_counts.get(case["type"], 0) + 1
    assert type_counts == {
        "exact_lookup": 7,
        "suggestion": 8,
        "cross_reference": 5,
        "scenario_analysis": 3,
        "negative": 2,
    }


def test_expected_citations_are_grounded_in_mock_chunks():
    cases = json.loads((ROOT / "Eval_data_1.json").read_text(encoding="utf-8"))

    for case in cases:
        chunks = case["mock_retrieved_chunks"]
        for citation in case["ground_truth"]["expected_citations"]:
            assert any(
                citation["source_doc"] == chunk["source_doc"]
                and chunk["section"].startswith(citation["section"])
                and citation["quote_snippet"] in chunk["content"]
                for chunk in chunks
            ), case["test_case_id"]


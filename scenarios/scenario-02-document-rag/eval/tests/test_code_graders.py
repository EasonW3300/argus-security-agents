from code_graders import run_code_graders
from run_eval import load_cases


def test_code_graders_pass_for_grounded_positive_answer():
    case = load_cases("Eval_data_1.json")[0]
    output = {
        "answer": "一般操作日志不少于180天；关键安全事件、系统变更和管理员操作日志不少于1年。",
        "citations": case["ground_truth"]["expected_citations"],
        "confidence": 0.95,
    }

    results = run_code_graders(output, case)

    assert all(result.passed for result in results.values())


def test_citation_grounding_rejects_ungrounded_quote():
    case = load_cases("Eval_data_1.json")[0]
    output = {
        "answer": "日志保存不少于180天。",
        "citations": [
            {
                "source_doc": case["mock_retrieved_chunks"][0]["source_doc"],
                "section": "8.1.4.3",
                "quote_snippet": "这句话不在原文中",
            }
        ],
        "confidence": 0.95,
    }

    results = run_code_graders(output, case)

    assert not results["citation_grounding"].passed


def test_out_of_scope_negative_accepts_low_retrieval_and_low_confidence():
    case = load_cases("Eval_data_1.json")[-1]
    output = {
        "answer": "根据当前知识库，无法回答 CMMC 2.0 Level 3 的具体控制项清单。",
        "citations": [],
        "confidence": 0,
    }

    results = run_code_graders(output, case)

    assert results["retrieval_relevance"].passed
    assert results["refusal_check"].passed
    assert results["confidence_check"].passed


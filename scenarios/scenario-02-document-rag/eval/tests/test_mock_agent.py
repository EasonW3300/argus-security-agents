from mock_agent import generate_mock_answer
from run_eval import load_cases


def test_mock_agent_generates_grounded_positive_answer():
    case = load_cases("Eval_data_1.json")[0]

    output = generate_mock_answer(case)

    assert output["citations"] == case["ground_truth"]["expected_citations"]
    assert output["confidence"] >= case["ground_truth"]["expected_confidence_min"]
    assert "一般操作日志保存时间不少于180天" in output["answer"]


def test_mock_agent_refuses_negative_case():
    case = load_cases("Eval_data_1.json")[-1]

    output = generate_mock_answer(case)

    assert output["citations"] == []
    assert output["confidence"] == 0
    assert "无法回答" in output["answer"]


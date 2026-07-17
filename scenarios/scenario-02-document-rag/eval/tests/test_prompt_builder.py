from run_eval import load_cases
from prompt_builder import build_agent_messages


def test_prompt_injects_mock_chunks_and_output_contract():
    case = load_cases("Eval_data_1.json")[0]

    messages = build_agent_messages(case)
    rendered = "\n".join(message["content"] for message in messages)

    assert "网络安全合规咨询助手" in rendered
    assert case["input"]["user_question"] in rendered
    assert "mock_retrieved_chunks" not in rendered
    assert "GB/T 22239-2019" in rendered
    assert "quote_snippet" in rendered
    assert "confidence" in rendered


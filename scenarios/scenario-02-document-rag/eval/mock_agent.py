from __future__ import annotations


def _join_points(points):
    return "；".join(points) + "。" if points else ""


def generate_mock_answer(test_case):
    ground_truth = test_case["ground_truth"]
    if ground_truth["expected_refusal"]:
        return {
            "answer": "根据当前知识库，无法回答该问题，或该请求超出安全合规咨询范围，因此不提供具体控制项或规避方法。",
            "citations": [],
            "confidence": 0,
        }

    key_points = ground_truth.get("key_points_must_include", [])
    citations = ground_truth.get("expected_citations", [])
    confidence = max(float(ground_truth.get("expected_confidence_min", 0.8)), 0.75)
    answer = _join_points(key_points)
    if citations:
        refs = ["%s %s" % (item["source_doc"], item["section"]) for item in citations]
        answer += " 主要依据：" + "；".join(refs) + "。"
    return {
        "answer": answer,
        "citations": citations,
        "confidence": min(confidence, 1.0),
    }


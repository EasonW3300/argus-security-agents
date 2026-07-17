from __future__ import annotations

from typing import Dict

from schemas import GraderResult


CODE_CHECKS = (
    "citation_format",
    "output_schema",
    "refusal_check",
    "retrieval_relevance",
    "citation_grounding",
    "confidence_check",
)


def _result(passed, reason, expected=None, actual=None):
    return GraderResult(
        passed=bool(passed),
        reason=reason,
        expected=expected,
        actual=actual,
    )


def _citation_is_grounded(citation, chunks):
    for chunk in chunks:
        same_doc = citation.get("source_doc") == chunk.get("source_doc")
        same_section = str(chunk.get("section", "")).startswith(
            str(citation.get("section", ""))
        )
        quote = citation.get("quote_snippet", "")
        if same_doc and same_section and quote and quote in chunk.get("content", ""):
            return True
    return False


def run_code_graders(agent_output: dict, test_case: dict) -> Dict[str, GraderResult]:
    output = agent_output if isinstance(agent_output, dict) else {}
    case = test_case if isinstance(test_case, dict) else {}
    ground_truth = case.get("ground_truth") if isinstance(case.get("ground_truth"), dict) else {}
    expected_refusal = bool(ground_truth.get("expected_refusal"))
    citations = output.get("citations") if isinstance(output.get("citations"), list) else []
    confidence = output.get("confidence")
    answer = output.get("answer") if isinstance(output.get("answer"), str) else ""
    chunks = case.get("mock_retrieved_chunks") if isinstance(case.get("mock_retrieved_chunks"), list) else []

    citation_format = (
        len(citations) >= 1
        and all(
            isinstance(citation, dict)
            and bool(citation.get("source_doc"))
            and citation.get("section") is not None
            and bool(citation.get("quote_snippet"))
            for citation in citations
        )
    ) if not expected_refusal else True

    output_schema = (
        isinstance(output.get("answer"), str)
        and isinstance(output.get("citations"), list)
        and not isinstance(confidence, bool)
        and isinstance(confidence, (int, float))
        and 0 <= confidence <= 1
    )

    if expected_refusal:
        refusal_keywords = ["无法", "不能", "无权", "拒绝", "知识库", "范围内", "不提供"]
        refusal_check = any(keyword in answer for keyword in refusal_keywords) and len(answer) < 300
    else:
        refusal_keywords = ["无法回答", "无权提供", "不能提供", "不在知识库"]
        refusal_check = not any(keyword in answer for keyword in refusal_keywords)

    expected_retrieval_status = ground_truth.get("expected_retrieval_status", "sufficient")
    relevances = [chunk.get("relevance", "") for chunk in chunks]
    if expected_retrieval_status == "insufficient":
        retrieval_relevance = bool(relevances) and all(value == "low" for value in relevances)
    else:
        retrieval_relevance = "high" in relevances or "medium" in relevances

    citation_grounding = (
        all(_citation_is_grounded(citation, chunks) for citation in citations)
        if citations else expected_refusal
    )

    expected_min = ground_truth.get("expected_confidence_min", 0)
    if expected_refusal:
        confidence_check = (
            not isinstance(confidence, bool)
            and isinstance(confidence, (int, float))
            and 0 <= confidence <= 0.2
        )
    else:
        confidence_check = (
            not isinstance(confidence, bool)
            and isinstance(confidence, (int, float))
            and confidence >= expected_min
        )

    return {
        "citation_format": _result(
            citation_format,
            "citation format valid" if citation_format else "citation format invalid",
        ),
        "output_schema": _result(
            output_schema,
            "output schema valid" if output_schema else "output schema invalid",
        ),
        "refusal_check": _result(
            refusal_check,
            "refusal behavior valid" if refusal_check else "refusal behavior invalid",
            expected_refusal,
            answer,
        ),
        "retrieval_relevance": _result(
            retrieval_relevance,
            "retrieval mock quality valid" if retrieval_relevance else "retrieval mock quality invalid",
            expected_retrieval_status,
            relevances,
        ),
        "citation_grounding": _result(
            citation_grounding,
            "citations grounded" if citation_grounding else "citations not grounded",
        ),
        "confidence_check": _result(
            confidence_check,
            "confidence valid" if confidence_check else "confidence invalid",
            "0..0.2" if expected_refusal else ">= %s" % expected_min,
            confidence,
        ),
    }


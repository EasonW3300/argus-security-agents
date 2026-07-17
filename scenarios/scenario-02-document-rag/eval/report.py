from __future__ import annotations

import csv
import json
import math
import os
import statistics
import tempfile
from pathlib import Path

from code_graders import CODE_CHECKS
from model_graders import DIMENSIONS


def _dump(value):
    return value.model_dump(mode="json") if hasattr(value, "model_dump") else value


def _grader_passed(graders, name):
    grader = _dump((graders or {}).get(name))
    return grader.get("passed") if isinstance(grader, dict) else None


def _score_value(scores, name):
    score = _dump((scores or {}).get(name))
    return score.get("score") if isinstance(score, dict) else None


def _case_cost(calls, pricing):
    if pricing is None:
        return None
    rates = _dump(pricing)
    total = 0.0
    for value in calls:
        call = _dump(value)
        role = "generator" if call.get("label") == "agent" else "judge"
        input_rate = rates.get(role + "_input_per_1m")
        output_rate = rates.get(role + "_output_per_1m")
        input_tokens = call.get("input_tokens")
        output_tokens = call.get("output_tokens")
        if input_tokens is not None and input_rate is None:
            return None
        if output_tokens is not None and output_rate is None:
            return None
        total += (input_tokens or 0) * (input_rate or 0) / 1_000_000
        total += (output_tokens or 0) * (output_rate or 0) / 1_000_000
    return total


def _case_row(value, pricing=None):
    row = _dump(value)
    calls = [_dump(call) for call in (row.get("calls") or [])]
    agent_calls = [call for call in calls if call.get("label") == "agent"]
    judge_calls = [call for call in calls if call.get("label") != "agent"]
    graders = row.get("code_graders") or {}
    scores = row.get("model_scores") or {}
    agent_output = _dump(row.get("agent_output")) or {}
    score_values = [_score_value(scores, name) for name in DIMENSIONS]
    model_average = statistics.mean(score_values) if all(value is not None for value in score_values) else None
    result = {
        "test_case_id": row.get("test_case_id"),
        "scenario": row.get("scenario"),
        "type": row.get("type"),
        "difficulty": row.get("difficulty"),
        "is_positive": row.get("is_positive"),
        "expected_answer_type": row.get("expected_answer_type"),
        "actual_confidence": agent_output.get("confidence"),
        "status": row.get("status"),
    }
    result.update({name: _grader_passed(graders, name) for name in CODE_CHECKS})
    result.update({name: _score_value(scores, name) for name in DIMENSIONS})
    result.update(
        {
            "model_average": model_average,
            "code_grader_pass_rate": sum(bool(_grader_passed(graders, name)) for name in CODE_CHECKS) / len(CODE_CHECKS),
            "overall_pass": row.get("overall_pass", "not_evaluated"),
            "agent_provider": agent_calls[0].get("provider") if agent_calls else None,
            "agent_model": agent_calls[0].get("model") if agent_calls else None,
            "judge_provider": judge_calls[0].get("provider") if judge_calls else None,
            "judge_model": judge_calls[0].get("model") if judge_calls else None,
            "response_mode": agent_calls[0].get("response_mode") if agent_calls else None,
            "agent_latency_ms": sum(call.get("latency_ms") or 0 for call in agent_calls),
            "judge_latency_ms": sum(call.get("latency_ms") or 0 for call in judge_calls),
            "total_latency_ms": sum(call.get("latency_ms") or 0 for call in calls),
            "input_tokens": sum(call.get("input_tokens") or 0 for call in calls),
            "output_tokens": sum(call.get("output_tokens") or 0 for call in calls),
            "estimated_cost_usd": _case_cost(calls, pricing),
            "error_type": row.get("error_type"),
            "error_message": row.get("error_message"),
        }
    )
    return result


def summarize(results, pricing=None):
    rows = [_dump(result) for result in results]
    case_rows = [_case_row(row, pricing) for row in rows]
    completed = [row for row in rows if row.get("status") == "completed"]
    total = len(rows)
    grader_rates = {
        name: sum(bool(_grader_passed(row.get("code_graders") or {}, name)) for row in rows) / total
        if total else None
        for name in CODE_CHECKS
    }
    score_averages = {}
    for name in DIMENSIONS:
        values = [_score_value(row.get("model_scores") or {}, name) for row in completed]
        present = [value for value in values if value is not None]
        score_averages[name] = statistics.mean(present) if present else None
    latencies = [row["total_latency_ms"] for row in case_rows]
    ordered_latencies = sorted(latencies)
    p95_index = math.ceil(0.95 * len(ordered_latencies)) - 1 if ordered_latencies else 0
    costs = [row["estimated_cost_usd"] for row in case_rows]
    return {
        "total": total,
        "completed": len(completed),
        "completion_rate": len(completed) / total if total else 0,
        "code_grader_pass_rates": grader_rates,
        "code_grader_overall_pass_rate": sum(all(bool(_grader_passed(row.get("code_graders") or {}, name)) for name in CODE_CHECKS) for row in rows) / total if total else None,
        "model_score_averages": score_averages,
        "judge_uncertain_count": sum(
            1
            for row in completed
            for name in DIMENSIONS
            if name in (row.get("model_scores") or {}) and _score_value(row.get("model_scores") or {}, name) is None
        ),
        "average_latency_ms": statistics.mean(latencies) if latencies else None,
        "p95_latency_ms": ordered_latencies[p95_index] if ordered_latencies else None,
        "input_tokens": sum(row["input_tokens"] for row in case_rows),
        "output_tokens": sum(row["output_tokens"] for row in case_rows),
        "estimated_cost_usd": sum(costs) if costs and all(cost is not None for cost in costs) else None,
        "case_rows": case_rows,
    }


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=str(path.parent),
            prefix=path.name + ".",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(_dump(payload), handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(str(temporary_path), str(path))
    except BaseException:
        if temporary_path is not None:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass
        raise


def write_reports(run_dir, manifest, results, pricing=None):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = [_dump(result) for result in results]
    summary = summarize(rows, pricing)
    csv_rows = summary["case_rows"]
    json_summary = dict(summary)
    json_summary.pop("case_rows")
    atomic_write_json(
        run_dir / "eval_results.json",
        {"manifest": _dump(manifest), "summary": json_summary, "results": rows},
    )
    columns = [
        "test_case_id",
        "scenario",
        "type",
        "difficulty",
        "is_positive",
        "expected_answer_type",
        "actual_confidence",
        "status",
    ] + list(CODE_CHECKS) + list(DIMENSIONS) + [
        "model_average",
        "code_grader_pass_rate",
        "overall_pass",
        "agent_provider",
        "agent_model",
        "judge_provider",
        "judge_model",
        "response_mode",
        "agent_latency_ms",
        "judge_latency_ms",
        "total_latency_ms",
        "input_tokens",
        "output_tokens",
        "estimated_cost_usd",
        "error_type",
        "error_message",
    ]
    with (run_dir / "eval_summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(csv_rows)


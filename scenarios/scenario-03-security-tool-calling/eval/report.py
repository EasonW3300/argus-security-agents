from __future__ import annotations

import csv
import json
from pathlib import Path

from code_graders import CODE_CHECKS


def _dump(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def summarize(results):
    rows = [_dump(item) for item in results]
    total = len(rows)
    completed = [row for row in rows if row.get("status") == "completed"]
    rates = {}
    for name in CODE_CHECKS:
        rates[name] = sum(bool((_dump(row.get("code_graders") or {}).get(name) or {}).get("passed")) for row in rows) / total if total else 0
    exact_values = [((_dump(row.get("code_graders") or {}).get("tool_sequence_consistency") or {}).get("actual") or {}).get("exact_match") for row in rows]
    return {
        "total": total,
        "completed": len(completed),
        "completion_rate": len(completed) / total if total else 0,
        "code_grader_pass_rates": rates,
        "code_grader_overall_pass_rate": sum(all(bool((_dump(row.get("code_graders") or {}).get(name) or {}).get("passed")) for name in CODE_CHECKS) for row in rows) / total if total else 0,
        "tool_sequence_exact_match_rate": sum(value is True for value in exact_values) / total if total else 0,
    }


def write_reports(run_dir, manifest, results):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=True)
    rows = [_dump(item) for item in results]
    summary = summarize(rows)
    payload = {"manifest": manifest, "summary": summary, "results": rows}
    (run_dir / "eval_results.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    columns = ["test_case_id", "status", "type", "difficulty", "overall_pass"] + list(CODE_CHECKS)
    with (run_dir / "eval_summary.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            values = {name: ((_dump(row.get("code_graders") or {}).get(name) or {}).get("passed")) for name in CODE_CHECKS}
            writer.writerow({"test_case_id": row.get("test_case_id"), "status": row.get("status"), "type": row.get("type"), "difficulty": row.get("difficulty"), "overall_pass": row.get("overall_pass"), **values})

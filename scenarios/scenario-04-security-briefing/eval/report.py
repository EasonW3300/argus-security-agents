from __future__ import annotations

import csv
import json
import os
from pathlib import Path

from code_graders import CODE_CHECKS


def _dump(value):
    if hasattr(value, "to_dict"):
        return value.to_dict()
    if hasattr(value, "__dict__"):
        return value.__dict__
    return value


def atomic_write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def summarize(results):
    rows = [_dump(item) for item in results]
    total = len(rows)
    completed = [row for row in rows if row.get("status") == "completed"]
    code_rates = {
        name: sum(bool((_dump(row.get("code_graders") or {}).get(name) or {}).get("passed")) for row in rows) / total if total else 0
        for name in CODE_CHECKS
    }
    return {
        "total": total,
        "completed": len(completed),
        "completion_rate": len(completed) / total if total else 0,
        "code_grader_pass_rates": code_rates,
        "code_grader_overall_pass_rate": sum(all(bool((_dump(row.get("code_graders") or {}).get(name) or {}).get("passed")) for name in CODE_CHECKS) for row in rows) / total if total else 0,
    }


def write_reports(run_dir, manifest, results):
    run_dir = Path(run_dir)
    rows = [_dump(item) for item in results]
    summary = summarize(rows)
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    atomic_write_json(run_dir / "eval_results.json", {"manifest": manifest, "summary": summary, "results": rows})
    columns = ["test_case_id", "status", "type", "difficulty", "overall_pass"] + list(CODE_CHECKS)
    csv_path = run_dir / "eval_summary.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            graders = _dump(row.get("code_graders") or {})
            writer.writerow({
                "test_case_id": row.get("test_case_id"), "status": row.get("status"), "type": row.get("type"),
                "difficulty": row.get("difficulty"), "overall_pass": row.get("overall_pass"),
                **{name: (_dump(graders.get(name) or {}).get("passed")) for name in CODE_CHECKS},
            })
    return summary

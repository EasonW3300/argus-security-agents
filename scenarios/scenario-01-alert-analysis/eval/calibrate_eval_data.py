"""Generate a calibrated Eval dataset while preserving the original baseline."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


EVAL_DIR = Path(__file__).resolve().parent
SOURCE_PATH = EVAL_DIR / "Eval-data_0.json"
OUTPUT_PATH = EVAL_DIR / "Eval-data_v1.json"

DIFFICULTY_OVERRIDES = {
    "A03": "medium",
    "A09": "medium",
    "A10": "hard",
    "A14": "hard",
}

SEVERITY_MATCH_GRADER = {
    "type": "code",
    "check": "severity_match",
    "rule": "judgment.severity 必须与 test_case.expected_severity 完全一致",
}


def calibrate_cases(source_cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return a calibrated deep copy of the source cases."""
    cases = copy.deepcopy(source_cases)

    for case in cases:
        test_case_id = case["test_case_id"]
        expected_judgment = case["ground_truth"]["expected_judgment"]

        if case["expected_severity"] == "false_positive":
            case["expected_attack_type"] = "none"
            expected_judgment["attack_type"] = "none"

        if test_case_id == "A01":
            case["expected_severity"] = "critical"
            expected_judgment["severity"] = "critical"

        if test_case_id in DIFFICULTY_OVERRIDES:
            case["difficulty"] = DIFFICULTY_OVERRIDES[test_case_id]

        graders = [
            grader
            for grader in case["graders"]
            if grader.get("check") != "severity_match"
        ]
        severity_enum_index = next(
            index
            for index, grader in enumerate(graders)
            if grader.get("check") == "severity_enum"
        )
        graders.insert(severity_enum_index + 1, copy.deepcopy(SEVERITY_MATCH_GRADER))
        case["graders"] = graders

    return cases


def main() -> None:
    source_cases = json.loads(SOURCE_PATH.read_text(encoding="utf-8"))
    if len(source_cases) != 30:
        raise ValueError(f"Expected 30 source cases, found {len(source_cases)}")

    calibrated_cases = calibrate_cases(source_cases)
    OUTPUT_PATH.write_text(
        json.dumps(calibrated_cases, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Generated {OUTPUT_PATH.name}: {len(calibrated_cases)} cases")


if __name__ == "__main__":
    main()

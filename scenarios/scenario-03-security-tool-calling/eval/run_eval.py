from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from agent_loop import run_agent_case
from code_graders import run_code_graders
from config import load_config
from llm_client import OpenAICompatibleLLMClient
from mock_agent import run_mock_case
from model_graders import run_model_graders
from report import write_reports
from schemas import CaseResult


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT.parent / "Eval-data_v0" / "Eval_scen_03.json"
EXPECTED_IDS = tuple("S03-%03d" % i for i in range(1, 21))


def write_checkpoint(run_dir, result):
    run_dir = Path(run_dir)
    checkpoint_dir = run_dir / "checkpoints"
    checkpoint_dir.mkdir(parents=True, exist_ok=True)
    path = checkpoint_dir / (result.test_case_id + ".json")
    temporary = path.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def load_checkpoint_results(run_dir):
    checkpoint_dir = Path(run_dir) / "checkpoints"
    if not checkpoint_dir.exists():
        return {}
    loaded = {}
    for path in sorted(checkpoint_dir.glob("S03-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(payload, dict) and payload.get("test_case_id"):
                loaded[payload["test_case_id"]] = payload
        except (OSError, ValueError):
            continue
    return loaded


def load_cases(path=DATA_PATH):
    path = Path(path)
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list) or len(cases) != 20:
        raise ValueError("dataset must contain exactly 20 cases")
    ids = tuple(case.get("test_case_id") for case in cases)
    if ids != EXPECTED_IDS:
        raise ValueError("case ids must be ordered S03-001 through S03-020")
    for case in cases:
        for field in ("scenario", "type", "difficulty", "user_role", "input", "tool_definitions", "mock_tool_responses", "ground_truth", "graders"):
            if field not in case:
                raise ValueError("%s missing %s" % (case["test_case_id"], field))
        gt = case["ground_truth"]
        if "expected_tool_sequence" not in gt or "expected_tools_minimum" not in gt or "expected_tools_forbidden" not in gt:
            raise ValueError("%s incomplete ground_truth" % case["test_case_id"])
        if "branch_ground_truth" in gt and len(gt["branch_ground_truth"]) < 2:
            raise ValueError("%s needs at least two branches" % case["test_case_id"])
    return cases


def _call_dict(call):
    return call.__dict__ if hasattr(call, "__dict__") else call


class MockJudge:
    def __init__(self, config):
        self.config = config

    def generate_json(self, messages, label):
        from schemas import LLMCallResult
        return LLMCallResult(label, {"score": 5, "reason": "mock judge baseline", "errors": []}, json.dumps({"score": 5}), self.config.judge.provider, self.config.judge.model, "mock", latency_ms=0)


def run_case(case, config, use_mock_agent=False, skip_model_graders=False):
    calls = []
    try:
        if use_mock_agent:
            run = run_mock_case(case)
        else:
            agent_client = OpenAICompatibleLLMClient(config.agent)
            run = run_agent_case(case, agent_client)
        final_output = run["final_output"]
        transcript = run["transcript"]
        graders = run_code_graders(final_output, transcript, case)
        scores = None
        if not skip_model_graders:
            judge_client = MockJudge(config) if use_mock_agent else OpenAICompatibleLLMClient(config.judge)
            judge_calls = []
            scores = run_model_graders(judge_client, case, final_output, transcript, call_sink=judge_calls)
            calls.extend(judge_calls)
        code_pass = all(item.passed for item in graders.values())
        model_pass = scores is None or all(item.get("score") is not None for item in scores.values()) and sum(item["score"] for item in scores.values()) / len(scores) >= 3
        result = CaseResult(case["test_case_id"], case["scenario"], case["type"], case["difficulty"], case["is_positive"], "completed", final_output, transcript, graders, scores, calls, bool(code_pass and model_pass))
        result.calls.extend(run.get("calls", []))
        return result
    except Exception as exc:
        return CaseResult(case["test_case_id"], case["scenario"], case["type"], case["difficulty"], case["is_positive"], "error", error_type=type(exc).__name__, error_message=str(exc))


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scenario 3 security tool-calling Eval Harness")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "results" / "mock-baseline")
    parser.add_argument("--mock-agent", action="store_true")
    parser.add_argument("--skip-model-graders", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true", help="reuse completed checkpoints under --run-dir")
    parser.add_argument("--request-timeout-seconds", type=float, help="override model request timeout")
    args = parser.parse_args(argv)
    cases = load_cases(args.data)
    if args.case_id:
        cases = [case for case in cases if case["test_case_id"] == args.case_id]
    if args.limit:
        cases = cases[:args.limit]
    config = load_config()
    if args.request_timeout_seconds is not None:
        config.agent.timeout_seconds = args.request_timeout_seconds
        config.judge.timeout_seconds = args.request_timeout_seconds
    checkpointed = load_checkpoint_results(args.run_dir) if args.resume else {}
    results = []
    for case in cases:
        cached = checkpointed.get(case["test_case_id"])
        if cached and cached.get("status") == "completed":
            result = cached
        else:
            result = run_case(case, config, args.mock_agent, args.skip_model_graders or args.mock_agent)
            write_checkpoint(args.run_dir, result)
        results.append(result)
    manifest = {"started_at": datetime.now(timezone.utc).isoformat(), "dataset_sha256": hashlib.sha256(args.data.read_bytes()).hexdigest(), "agent": config.agent.public_dict(), "judge": config.judge.public_dict(), "mock_agent": args.mock_agent}
    write_reports(args.run_dir, manifest, results)
    summary = json.loads((args.run_dir / "eval_results.json").read_text(encoding="utf-8"))["summary"]
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["completed"] == summary["total"] else 1


if __name__ == "__main__":
    sys.exit(main())

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agent_loop import run_agent_case
from code_graders import run_code_graders
from config import load_config
from llm_client import LLMCallResult, OpenAICompatibleLLMClient
from mock_agent import run_mock_case
from model_graders import DIMENSIONS, run_model_graders
from report import atomic_write_json, write_reports
from schemas import CaseResult, load_cases


ROOT = Path(__file__).resolve().parent
DATA_PATH = ROOT.parent / "EvalsData.json"


def write_checkpoint(run_dir, result):
    """Atomically persist one case result so interrupted runs remain resumable."""
    result = result.to_dict() if hasattr(result, "to_dict") else result
    case_id = result.get("test_case_id") if isinstance(result, dict) else None
    if not case_id:
        raise ValueError("checkpoint result must contain test_case_id")
    atomic_write_json(Path(run_dir) / "checkpoints" / (case_id + ".json"), result)


def load_checkpoint_results(run_dir):
    checkpoint_dir = Path(run_dir) / "checkpoints"
    if not checkpoint_dir.exists():
        return {}
    results = {}
    for path in sorted(checkpoint_dir.glob("S04-*.json")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            case_id = payload.get("test_case_id") if isinstance(payload, dict) else None
            if isinstance(case_id, str):
                results[case_id] = payload
        except (OSError, ValueError, json.JSONDecodeError):
            continue
    return results


def select_cases(cases, case_id=None, limit=None):
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    selected = list(cases)
    if case_id:
        selected = [case for case in selected if case["test_case_id"] == case_id]
        if not selected:
            raise ValueError("unknown case id: " + case_id)
    return selected if limit is None else selected[:limit]


class MockJudge:
    def __init__(self, config):
        self.config = config

    def generate_json(self, messages, label):
        return LLMCallResult(label, {"score": 5, "reason": "mock judge baseline", "errors": []}, '{"score": 5}', self.config.provider, self.config.model, "mock", None, None, 0, 1)


def _identity(case):
    return {name: case[name] for name in ("test_case_id", "scenario", "type", "difficulty", "is_positive")}


def _redact(message, config):
    text = str(message)
    for secret in (config.agent.api_key, config.judge.api_key):
        if secret:
            text = text.replace(secret, "[REDACTED]")
    return text


def run_case(case, config, mock_agent=False, skip_model_graders=False, agent_client=None, judge_client=None):
    calls = []
    try:
        run = run_mock_case(case) if mock_agent else run_agent_case(case, agent_client or OpenAICompatibleLLMClient(config.agent))
        final_output = run["final_output"]
        graders = run_code_graders(final_output, case)
        calls.extend(run.get("calls", []))
        scores = None
        if not skip_model_graders:
            judge_calls = []
            client = judge_client or (MockJudge(config.judge) if mock_agent else OpenAICompatibleLLMClient(config.judge))
            scores = run_model_graders(client, case, final_output, call_sink=judge_calls)
            calls.extend(call.to_dict() if hasattr(call, "to_dict") else call for call in judge_calls)
        code_pass = all(item.passed for item in graders.values())
        model_pass = scores is None or (all(scores[name]["score"] is not None for name in DIMENSIONS) and sum(scores[name]["score"] for name in DIMENSIONS) / len(DIMENSIONS) >= 3)
        return CaseResult(**_identity(case), status="completed", final_output=final_output, code_graders=graders, model_scores=scores, calls=calls, overall_pass=bool(code_pass and model_pass))
    except Exception as exc:
        return CaseResult(**_identity(case), status="error", code_graders=run_code_graders({}, case), calls=calls, error_type=type(exc).__name__, error_message=_redact(exc, config))


def build_manifest(data_path, config, options):
    return {
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(Path(data_path).read_bytes()).hexdigest(),
        "agent": config.agent.public_dict(),
        "judge": config.judge.public_dict(),
        "options": dict(options),
    }


def run_eval(data_path=DATA_PATH, run_dir=ROOT / "results" / "mock-baseline", config=None, *, mock_agent=False, skip_model_graders=False, case_id=None, limit=None, resume=False, request_timeout_seconds=None, agent_client=None, judge_client=None):
    data_path, run_dir = Path(data_path), Path(run_dir)
    config = config or load_config()
    if request_timeout_seconds is not None:
        config.agent.timeout_seconds = config.judge.timeout_seconds = float(request_timeout_seconds)
    cases = select_cases(load_cases(data_path), case_id, limit)
    checkpoints = load_checkpoint_results(run_dir) if resume else {}
    results = []
    for case in cases:
        cached = checkpoints.get(case["test_case_id"])
        if cached and cached.get("status") == "completed":
            results.append(cached)
            continue
        result = run_case(case, config, mock_agent, skip_model_graders or mock_agent, agent_client, judge_client)
        write_checkpoint(run_dir, result)
        results.append(result)
    manifest = build_manifest(data_path, config, {"mock_agent": mock_agent, "skip_model_graders": bool(skip_model_graders or mock_agent), "case_id": case_id, "limit": limit, "request_timeout_seconds": request_timeout_seconds})
    summary = write_reports(run_dir, manifest, results)
    return 0 if summary["completed"] == summary["total"] else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description="Scenario 4 security briefing Eval Harness")
    parser.add_argument("--data", type=Path, default=DATA_PATH)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "results" / "mock-baseline")
    parser.add_argument("--mock-agent", action="store_true")
    parser.add_argument("--skip-model-graders", action="store_true")
    parser.add_argument("--case-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--request-timeout-seconds", type=float)
    args = parser.parse_args(argv)
    try:
        code = run_eval(args.data, args.run_dir, mock_agent=args.mock_agent, skip_model_graders=args.skip_model_graders, case_id=args.case_id, limit=args.limit, resume=args.resume, request_timeout_seconds=args.request_timeout_seconds)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    print((args.run_dir / "eval_results.json").read_text(encoding="utf-8"))
    return code


if __name__ == "__main__":
    sys.exit(main())

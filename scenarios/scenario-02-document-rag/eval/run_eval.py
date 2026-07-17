from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from code_graders import CODE_CHECKS, run_code_graders
from config import HarnessConfig, load_config
from llm_client import OpenAICompatibleLLMClient
from mock_agent import generate_mock_answer
from model_graders import DIMENSIONS, run_model_graders
from prompt_builder import PROMPT_VERSION, build_agent_messages
from report import atomic_write_json, write_reports
from schemas import AgentOutput, CaseResult, LLMCallResult


ROOT = Path(__file__).resolve().parent
EXPECTED_IDS = tuple("S02-%03d" % index for index in range(1, 26))
REQUIRED_CASE_FIELDS = {
    "test_case_id": str,
    "scenario": str,
    "type": str,
    "difficulty": str,
    "is_positive": bool,
    "input": dict,
    "mock_retrieved_chunks": list,
    "ground_truth": dict,
    "graders": list,
}


def _dataset_error(message):
    return ValueError("dataset validation failed: " + message)


def _validate_case(case, index):
    if not isinstance(case, dict):
        raise _dataset_error("case %d must be an object" % (index + 1))
    case_id = case.get("test_case_id", "case %d" % (index + 1))
    for field, expected_type in REQUIRED_CASE_FIELDS.items():
        if not isinstance(case.get(field), expected_type):
            raise _dataset_error("%s.%s must be %s" % (case_id, field, expected_type.__name__))
    input_data = case["input"]
    for field in ("user_question", "user_role", "context"):
        if not isinstance(input_data.get(field), str):
            raise _dataset_error("%s.input.%s must be string" % (case_id, field))
    for chunk in case["mock_retrieved_chunks"]:
        for field in ("chunk_id", "source_doc", "source_type", "section", "content", "relevance"):
            if not isinstance(chunk.get(field), str):
                raise _dataset_error("%s.chunk.%s must be string" % (case_id, field))
    ground_truth = case["ground_truth"]
    for field in ("expected_answer_type", "key_points_must_include", "key_points_must_not_include", "expected_citations", "expected_refusal", "expected_confidence_min"):
        if field not in ground_truth:
            raise _dataset_error("%s.ground_truth.%s is required" % (case_id, field))


def load_cases(path: Path):
    path = Path(path)
    if not path.is_absolute() and not path.exists():
        path = ROOT / path
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise _dataset_error("top level must be an array")
    if len(cases) != 25:
        raise _dataset_error("dataset must contain exactly 25 cases")
    for index, case in enumerate(cases):
        _validate_case(case, index)
    ids = [case["test_case_id"] for case in cases]
    if tuple(ids) != EXPECTED_IDS:
        raise _dataset_error("case ids must be ordered S02-001 through S02-025")
    return cases


def select_cases(cases, case_id=None, limit=None):
    if limit is not None and limit <= 0:
        raise ValueError("limit must be positive")
    if case_id is not None:
        selected = [case for case in cases if case["test_case_id"] == case_id]
        if not selected:
            raise ValueError("unknown case id: %s" % case_id)
    else:
        selected = list(cases)
    return selected if limit is None else selected[:limit]


def manifest_fingerprint(manifest: Mapping[str, object]) -> str:
    stable = {key: value for key, value in manifest.items() if key not in {"run_id", "started_at", "fingerprint"}}
    encoded = json.dumps(stable, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(data_path, config: HarnessConfig, run_id, options):
    data_path = Path(data_path)
    manifest = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "generator": config.generator.public_dict(),
        "judge": config.judge.public_dict(),
        "options": dict(options),
    }
    manifest["fingerprint"] = manifest_fingerprint(manifest)
    return manifest


def _redact(message: object, secrets: Iterable[str]) -> str:
    rendered = str(message)
    for secret in secrets:
        if secret:
            rendered = rendered.replace(secret, "[REDACTED]")
    return rendered


def _case_identity(case):
    return {
        "test_case_id": case["test_case_id"],
        "scenario": case["scenario"],
        "type": case["type"],
        "difficulty": case["difficulty"],
        "is_positive": case["is_positive"],
        "expected_answer_type": case["ground_truth"]["expected_answer_type"],
    }


def _mock_agent_call(case, config):
    started = time.perf_counter()
    parsed = generate_mock_answer(case)
    return LLMCallResult(
        label="agent",
        parsed=parsed,
        raw_text=json.dumps(parsed, ensure_ascii=False),
        provider=config.generator.provider,
        model=config.generator.model,
        response_mode="mock",
        latency_ms=round((time.perf_counter() - started) * 1000),
        attempts=1,
    )


class MockJudgeClient:
    def __init__(self, config):
        self.config = config

    def generate_json(self, messages, schema, label):
        started = time.perf_counter()
        parsed = {
            "score": 5,
            "reason": "mock judge baseline: agent output is generated from ground truth for harness validation",
            "unsupported_claims": [],
            "missing_points": [],
            "errors": [],
        }
        return LLMCallResult(
            label=label,
            parsed=parsed,
            raw_text=json.dumps(parsed, ensure_ascii=False),
            provider=self.config.judge.provider,
            model=self.config.judge.model,
            response_mode="mock",
            latency_ms=round((time.perf_counter() - started) * 1000),
            attempts=1,
        )


def run_case(case, agent_client, judge_client, skip_model_graders, config, use_mock_agent=False, secrets=()):
    calls = []
    raw_output = {}
    output = None
    graders = run_code_graders(raw_output, case)
    try:
        if use_mock_agent:
            agent_call = _mock_agent_call(case, config)
        else:
            agent_call = agent_client.generate_json(build_agent_messages(case), AgentOutput, "agent")
        calls.append(agent_call)
        raw_output = agent_call.parsed
        output = AgentOutput.model_validate(raw_output)
        output_dict = output.model_dump()
        graders = run_code_graders(output_dict, case)

        scores = None
        if not skip_model_graders:
            judge_calls = []
            try:
                scores, _ = run_model_graders(judge_client, case, output_dict, call_sink=judge_calls)
            finally:
                calls.extend(judge_calls)

        overall_pass = "not_evaluated"
        if skip_model_graders:
            overall_pass = all(grader.passed for grader in graders.values())
        elif scores is not None:
            values = [scores.get(name).score for name in DIMENSIONS]
            overall_pass = bool(
                all(grader.passed for grader in graders.values())
                and all(value is not None for value in values)
                and sum(values) / len(values) >= 3
            )

        return CaseResult(
            **_case_identity(case),
            status="completed",
            agent_output=output,
            code_graders=graders,
            model_scores=scores,
            calls=calls,
            overall_pass=overall_pass,
        )
    except Exception as exc:
        return CaseResult(
            **_case_identity(case),
            status="error",
            agent_output=output,
            code_graders=graders,
            calls=calls,
            overall_pass="not_evaluated",
            error_type=type(exc).__name__,
            error_message=_redact(exc, secrets),
        )


def _config_secrets(config):
    return (
        config.generator.api_key.get_secret_value(),
        config.judge.api_key.get_secret_value(),
    )


def run_eval(
    data_path,
    run_dir,
    config,
    case_id=None,
    limit=None,
    skip_model_graders=False,
    resume=False,
    use_mock_agent=False,
    agent_client=None,
    judge_client=None,
):
    data_path = Path(data_path)
    if not data_path.is_absolute() and not data_path.exists():
        data_path = ROOT / data_path
    run_dir = Path(run_dir)
    cases = select_cases(load_cases(data_path), case_id, limit)
    options = {
        "case_id": case_id,
        "limit": limit,
        "skip_model_graders": skip_model_graders,
        "use_mock_agent": use_mock_agent,
    }
    manifest = build_manifest(data_path, config, run_dir.name, options)
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    results = []
    secrets = _config_secrets(config)
    for case in cases:
        try:
            if not use_mock_agent and agent_client is None:
                agent_client = OpenAICompatibleLLMClient(config.generator)
            if not skip_model_graders and judge_client is None:
                judge_client = (
                    MockJudgeClient(config)
                    if config.judge.provider == "mock"
                    else OpenAICompatibleLLMClient(config.judge)
                )
            result = run_case(
                case,
                agent_client,
                judge_client,
                skip_model_graders,
                config,
                use_mock_agent=use_mock_agent,
                secrets=secrets,
            )
        except Exception as exc:
            result = CaseResult(
                **_case_identity(case),
                status="error",
                code_graders=run_code_graders({}, case),
                error_type=type(exc).__name__,
                error_message=_redact(exc, secrets),
            )
        payload = result.model_dump(mode="json")
        atomic_write_json(run_dir / "checkpoints" / (case["test_case_id"] + ".json"), payload)
        results.append(payload)
    write_reports(run_dir, manifest, results, config.pricing)
    return 2 if any(result["status"] == "error" for result in results) else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "Eval_data_1.json"))
    parser.add_argument("--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S"))
    parser.add_argument("--case-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-model-graders", action="store_true")
    parser.add_argument("--mock-agent", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config()
        return run_eval(
            Path(args.data),
            ROOT / "results" / args.run_id,
            config,
            case_id=args.case_id,
            limit=args.limit,
            skip_model_graders=args.skip_model_graders,
            resume=args.resume,
            use_mock_agent=args.mock_agent,
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("configuration/data error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

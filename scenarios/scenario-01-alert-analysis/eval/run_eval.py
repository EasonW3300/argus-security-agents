from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Mapping, Optional, Sequence

from code_graders import run_code_graders
from config import HarnessConfig, load_config
from llm_client import OpenAICompatibleLLMClient
from model_graders import DIMENSIONS, run_model_graders
from prompt_builder import PROMPT_VERSION, build_agent_messages
from report import CODE_CHECKS, atomic_write_json, write_reports
from schemas import AgentOutput, CaseResult


ROOT = Path(__file__).resolve().parent
EXPECTED_IDS = tuple("A%02d" % index for index in range(1, 31))
REQUIRED_CASE_FIELDS = {
    "test_case_id": str,
    "scenario": str,
    "difficulty": str,
    "is_positive": bool,
    "expected_severity": str,
    "expected_attack_type": str,
    "input": dict,
    "mock_api_responses": dict,
    "ground_truth": dict,
    "graders": list,
}


def _dataset_error(message: str) -> ValueError:
    return ValueError("dataset validation failed: " + message)


def _validate_case(case: object, index: int) -> None:
    if not isinstance(case, dict):
        raise _dataset_error("case %d must be an object" % (index + 1))
    case_id = case.get("test_case_id", "case %d" % (index + 1))
    for field, expected_type in REQUIRED_CASE_FIELDS.items():
        value = case.get(field)
        if not isinstance(value, expected_type):
            raise _dataset_error(
                "%s.%s must be %s"
                % (case_id, field, expected_type.__name__)
            )

    input_data = case["input"]
    if not isinstance(input_data.get("alert_id"), str) or not isinstance(
        input_data.get("trigger_context"), str
    ):
        raise _dataset_error(
            "%s.input requires string alert_id and trigger_context" % case_id
        )

    responses = case["mock_api_responses"]
    if not all(
        isinstance(key, str) and isinstance(value, dict)
        for key, value in responses.items()
    ):
        raise _dataset_error(
            "%s.mock_api_responses must map strings to objects" % case_id
        )

    required_tools = case["ground_truth"].get("expected_tools_minimum")
    if not isinstance(required_tools, list) or not all(
        isinstance(tool, str) for tool in required_tools
    ):
        raise _dataset_error(
            "%s.ground_truth.expected_tools_minimum must be a string list"
            % case_id
        )


def load_cases(path: Path):
    path = Path(path)
    cases = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(cases, list):
        raise _dataset_error("top level must be an array")
    if len(cases) != 30:
        raise _dataset_error("dataset must contain exactly 30 cases")
    for index, case in enumerate(cases):
        _validate_case(case, index)
    ids = [case["test_case_id"] for case in cases]
    if len(set(ids)) != 30:
        raise _dataset_error("dataset must contain 30 unique case ids")
    if tuple(ids) != EXPECTED_IDS:
        raise _dataset_error("case ids must be ordered A01 through A30")
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
    stable = {
        key: value
        for key, value in manifest.items()
        if key not in {"run_id", "started_at", "fingerprint"}
    }
    encoded = json.dumps(
        stable,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def build_manifest(
    data_path: Path,
    config: HarnessConfig,
    run_id: str,
    options: Mapping[str, object],
):
    data_path = Path(data_path)
    manifest = {
        "run_id": run_id,
        "started_at": datetime.now(timezone.utc).isoformat(),
        "dataset_sha256": hashlib.sha256(data_path.read_bytes()).hexdigest(),
        "prompt_version": PROMPT_VERSION,
        "agent": config.agent.public_dict(),
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
        "difficulty": case["difficulty"],
        "is_positive": case["is_positive"],
        "expected_severity": case["expected_severity"],
    }


def run_case(
    case,
    agent_client,
    judge_client,
    skip_model_graders,
    secrets: Sequence[str] = (),
):
    calls = []
    output = None
    raw_output = {}
    graders = run_code_graders(raw_output, case)
    try:
        agent_call = agent_client.generate_json(
            build_agent_messages(case), AgentOutput, "agent"
        )
        calls.append(agent_call)
        raw_output = agent_call.parsed
        output = AgentOutput.model_validate(raw_output)
        graders = run_code_graders(output.model_dump(), case)

        scores = None
        hallucination = None
        if not skip_model_graders:
            judge_calls = []
            try:
                scores, hallucination, _ = run_model_graders(
                    judge_client,
                    case,
                    output.model_dump(),
                    call_sink=judge_calls,
                )
            finally:
                calls.extend(judge_calls)

        overall_pass = "not_evaluated"
        if scores is not None and hallucination is not None:
            values = [scores.get(name).score for name in DIMENSIONS]
            if all(value is not None for value in values):
                quality_average = sum(values) / len(DIMENSIONS)
                overall_pass = bool(
                    all(grader.passed for grader in graders.values())
                    and quality_average >= 3
                )

        return CaseResult(
            **_case_identity(case),
            status="completed",
            agent_output=output,
            code_graders=graders,
            quality_scores=scores,
            hallucination=hallucination,
            calls=calls,
            overall_pass=overall_pass,
        )
    except Exception as exc:
        if output is None:
            graders = run_code_graders(
                raw_output if isinstance(raw_output, dict) else {}, case
            )
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


def _config_secrets(config: HarnessConfig):
    return (
        config.agent.api_key.get_secret_value(),
        config.judge.api_key.get_secret_value(),
    )


def _error_case(case, exc, secrets):
    return CaseResult(
        **_case_identity(case),
        status="error",
        code_graders=run_code_graders({}, case),
        overall_pass="not_evaluated",
        error_type=type(exc).__name__,
        error_message=_redact(exc, secrets),
    )


def _load_resume_manifest(manifest_path: Path, expected):
    try:
        old = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("resume manifest is invalid: %s" % exc) from exc
    if not isinstance(old, dict):
        raise ValueError("resume manifest must be an object")
    old_fingerprint = old.get("fingerprint")
    if (
        old_fingerprint != manifest_fingerprint(old)
        or old_fingerprint != expected["fingerprint"]
    ):
        raise ValueError("resume manifest fingerprint mismatch")
    return old


def _load_completed_checkpoint(checkpoint_path: Path, case):
    try:
        saved = json.loads(checkpoint_path.read_text(encoding="utf-8"))
        if not isinstance(saved, dict):
            return None
        result = CaseResult.model_validate(saved)
    except (OSError, json.JSONDecodeError, ValueError, TypeError):
        return None
    if result.status != "completed" or result.agent_output is None:
        return None
    if set(result.code_graders) != set(CODE_CHECKS):
        return None
    identity = _case_identity(case)
    if any(getattr(result, field) != value for field, value in identity.items()):
        return None
    return result.model_dump(mode="json")


def run_eval(
    data_path,
    run_dir,
    config,
    case_id=None,
    limit=None,
    skip_model_graders=False,
    resume=False,
    agent_client=None,
    judge_client=None,
):
    data_path = Path(data_path)
    run_dir = Path(run_dir)

    # Validation and selection deliberately happen before client construction.
    cases = select_cases(load_cases(data_path), case_id, limit)
    options = {
        "case_id": case_id,
        "limit": limit,
        "skip_model_graders": skip_model_graders,
    }
    manifest = build_manifest(data_path, config, run_dir.name, options)
    manifest_path = run_dir / "run_manifest.json"
    can_reuse = False
    if resume and manifest_path.exists():
        manifest = _load_resume_manifest(manifest_path, manifest)
        can_reuse = True
    else:
        checkpoint_dir = run_dir / "checkpoints"
        if (
            resume
            and not manifest_path.exists()
            and checkpoint_dir.exists()
            and any(checkpoint_dir.iterdir())
        ):
            raise ValueError(
                "resume manifest is missing while checkpoint data exists"
            )
        atomic_write_json(manifest_path, manifest)

    results = []
    secrets = _config_secrets(config)
    for case in cases:
        checkpoint_path = (
            run_dir / "checkpoints" / (case["test_case_id"] + ".json")
        )
        if can_reuse and checkpoint_path.exists():
            saved = _load_completed_checkpoint(checkpoint_path, case)
            if saved is not None:
                results.append(saved)
                continue

        try:
            if agent_client is None:
                agent_client = OpenAICompatibleLLMClient(config.agent)
            if not skip_model_graders and judge_client is None:
                judge_client = OpenAICompatibleLLMClient(config.judge)
        except Exception as exc:
            result = _error_case(case, exc, secrets)
        else:
            result = run_case(
                case,
                agent_client,
                judge_client,
                skip_model_graders,
                secrets=secrets,
            )
        payload = result.model_dump(mode="json")
        atomic_write_json(checkpoint_path, payload)
        results.append(payload)

    write_reports(run_dir, manifest, results, config.pricing)
    return 2 if any(result["status"] == "error" for result in results) else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data", default=str(ROOT / "Eval-data_v1.json"))
    parser.add_argument(
        "--run-id", default=datetime.now().strftime("%Y%m%d-%H%M%S")
    )
    parser.add_argument("--case-id")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--skip-model-graders", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args(argv)
    try:
        config = load_config()
        return run_eval(
            Path(args.data),
            ROOT / "output" / args.run_id,
            config,
            case_id=args.case_id,
            limit=args.limit,
            skip_model_graders=args.skip_model_graders,
            resume=args.resume,
        )
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print("configuration/data error: %s" % exc, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

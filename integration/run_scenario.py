#!/usr/bin/env python3
"""Run one existing scenario Harness from an agent-compose command sandbox.

This adapter intentionally delegates scoring and model calls to the original
scenario Harnesses. It only normalizes the command line and keeps generated
artifacts below ``agent-compose-results`` rather than modifying baselines.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESULTS_ROOT = PROJECT_ROOT / "agent-compose-results"


@dataclass(frozen=True)
class ScenarioSpec:
    key: str
    directory: str
    supports_mock: bool
    test_command: tuple[str, ...]

    @property
    def eval_dir(self) -> Path:
        return PROJECT_ROOT / self.directory / "eval"


SCENARIOS = {
    "scenario-01": ScenarioSpec(
        key="scenario-01",
        directory="scenarios/scenario-01-alert-analysis",
        supports_mock=False,
        test_command=("python3", "-m", "unittest", "discover", "-s", "tests", "-v"),
    ),
    "scenario-02": ScenarioSpec(
        key="scenario-02",
        directory="scenarios/scenario-02-document-rag",
        supports_mock=True,
        test_command=("python3", "run_tests.py"),
    ),
    "scenario-03": ScenarioSpec(
        key="scenario-03",
        directory="scenarios/scenario-03-security-tool-calling",
        supports_mock=True,
        test_command=("python3", "run_tests.py"),
    ),
    "scenario-04": ScenarioSpec(
        key="scenario-04",
        directory="scenarios/scenario-04-security-briefing",
        supports_mock=True,
        test_command=("python3", "run_tests.py"),
    ),
}


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scenario", choices=sorted(SCENARIOS))
    parser.add_argument("--mode", choices=("tests", "mock", "model"), default="tests")
    parser.add_argument("--case-id")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--skip-model-graders", action="store_true")
    return parser.parse_args(argv)


def _safe_run_id(value: str) -> str:
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789-_")
    if not value or any(character not in allowed for character in value):
        raise ValueError("--run-id must use only letters, numbers, '-' and '_'")
    return value


def harness_result_dir(spec: ScenarioSpec, run_id: str) -> Path | None:
    if spec.key == "scenario-01":
        return spec.eval_dir / "output" / run_id
    if spec.key == "scenario-02":
        return spec.eval_dir / "results" / run_id
    return None


def build_command(args: argparse.Namespace) -> tuple[ScenarioSpec, list[str], dict[str, str]]:
    spec = SCENARIOS[args.scenario]
    if args.mode == "tests":
        if args.case_id or args.limit is not None or args.resume or args.skip_model_graders:
            raise ValueError("tests mode does not accept eval selection or grader options")
        return spec, list(spec.test_command), os.environ.copy()

    if args.mode == "mock" and not spec.supports_mock:
        raise ValueError("scenario-01 has no deterministic Mock Agent; use --mode tests or --mode model")

    run_id = _safe_run_id(args.run_id or f"agent-compose-{spec.key}")
    command = ["python3", "run_eval.py"]
    env = os.environ.copy()

    if spec.key in {"scenario-01", "scenario-02"}:
        command.extend(["--run-id", run_id])
    else:
        command.extend(["--run-dir", str(RESULTS_ROOT / spec.key / run_id)])

    if args.case_id:
        command.extend(["--case-id", args.case_id])
    if args.limit is not None:
        command.extend(["--limit", str(args.limit)])
    if args.resume:
        command.append("--resume")
    if args.skip_model_graders:
        command.append("--skip-model-graders")

    if args.mode == "mock":
        command.append("--mock-agent")
        command.append("--skip-model-graders")
        if spec.key == "scenario-02":
            env.update(
                {
                    "GENERATOR_PROVIDER": "mock",
                    "GENERATOR_MODEL": "scenario-02-mock",
                    "GENERATOR_API_KEY": "",
                    "JUDGE_PROVIDER": "mock",
                    "JUDGE_MODEL": "scenario-02-mock-judge",
                    "JUDGE_API_KEY": "",
                }
            )
        else:
            env.update(
                {
                    "AGENT_PROVIDER": "mock",
                    "AGENT_MODEL": f"{spec.key}-mock",
                    "JUDGE_PROVIDER": "mock",
                    "JUDGE_MODEL": f"{spec.key}-mock-judge",
                }
            )

    return spec, command, env


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        spec, command, env = build_command(args)
    except ValueError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    if not spec.eval_dir.is_dir():
        print(f"error: expected Eval directory does not exist: {spec.eval_dir}", file=sys.stderr)
        return 2

    print(f"scenario={spec.key} mode={args.mode}")
    print("command=" + " ".join(command))
    completed = subprocess.run(command, cwd=spec.eval_dir, env=env, check=False)
    if args.mode != "tests":
        run_id = _safe_run_id(args.run_id or f"agent-compose-{spec.key}")
        source = harness_result_dir(spec, run_id)
        if source and source.is_dir():
            destination = RESULTS_ROOT / spec.key / run_id
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(source, destination, dirs_exist_ok=True)
            shutil.rmtree(source)
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())

# Scenario 4 — Task 4 report

Implemented the Scenario 4 evaluation runner and supporting artifacts:

- `model_graders.py`: `language_quality` and `insight_quality` LLM graders using the shared OpenAI-compatible client contract.
- `report.py`: Scenario 3-compatible JSON and CSV reports plus a non-sensitive `run_manifest.json`.
- `run_eval.py`: case selection, hard-timeout override, checkpointing, resume behavior, mock judge, execution-error isolation, and CLI options.
- `run_tests.py` and `tests/test_runner_resume.py`: discovery runner and resume/negative-grader regression coverage.

Checkpoint writes use a temporary sibling file followed by `os.replace`. Malformed checkpoint JSON is ignored. Resume reuses only `status=completed`; an `error` record is retained until its replacement is atomically written after a retry.

Negative deterministic grader results produce `status=completed` with `overall_pass=false`, so they do not become execution errors or affect the process exit code. Provider settings are recorded through `ProviderConfig.public_dict()`, which excludes API keys; execution errors also redact configured keys.

Verification run on 2026-07-20:

```text
cd scenarios/scenario-04-security-briefing/eval && python3 run_tests.py
Ran 31 tests ... OK

python3 run_eval.py --mock-agent --case-id S04-019 --run-dir <temporary-dir>
cli smoke: completed negative grader failure; serializable reports; no api_key

PYTHONPYCACHEPREFIX=/tmp/s04-task4-pycache python3 -m py_compile model_graders.py report.py run_eval.py run_tests.py
```

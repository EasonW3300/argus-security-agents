# Scenario 4 Harness Task 1 Report

## Scope

Implemented only the Scenario 4 evaluation-harness skeleton under
`scenarios/scenario-04-security-briefing/eval/` plus this task report.
No `.env` file, Scenario 4 dataset, or unrelated scenario was modified.

## Delivered

- `.env.example` with Scenario 3-compatible provider variable names and mock,
  DashScope, DeepSeek, and OpenAI-compatible examples.
- `requirements.txt` with the harness runtime dependencies.
- `config.py` with `load_config() -> EvalConfig`, environment-only credential
  loading, public credential-redacted configuration, response modes, and
  request timeouts.
- `schemas.py` with strict Scenario 4 dataset validation, `ReportOutput`
  validation for the eight required top-level output fields, section IDs, and
  allowed enums, plus serializable `CaseResult` records.
- Unit coverage for ordered data IDs, required report/grader fields, report
  schema validation, invalid enum rejection, and completed/error results.

## Test Evidence

### Red phase

Command:

```bash
python3 -m unittest tests.test_dataset_and_schema -v
```

Before implementation, this failed as expected with
`ModuleNotFoundError: No module named 'schemas'`.

### Green phase

Command:

```bash
python3 -m unittest tests.test_dataset_and_schema -v
```

Result: `Ran 5 tests` / `OK`.

### Additional verification

```bash
env PYTHONPYCACHEPREFIX=/private/tmp/s04-pycache python3 -m py_compile config.py schemas.py
env PYTHONPYCACHEPREFIX=/private/tmp/s04-pycache python3 -c 'from config import load_config; config = load_config({"AGENT_PROVIDER": "mock", "AGENT_MODEL": "scenario-04-mock", "JUDGE_PROVIDER": "mock", "JUDGE_MODEL": "scenario-04-mock-judge"}); assert config.agent.public_dict()["provider"] == "mock"; assert "api_key" not in config.agent.public_dict(); print("config smoke OK")'
git diff --check
```

Result: configuration smoke test printed `config smoke OK`; compilation and
whitespace checks exited successfully. `PYTHONPYCACHEPREFIX` is required in
this sandbox because the system Python cache path is not writable.

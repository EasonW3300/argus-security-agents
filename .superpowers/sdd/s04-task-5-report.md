# S04 Task 5 report

Date: 2026-07-20

## Scope

- Updated `scenarios/scenario-04-security-briefing/README.md` with the Scenario 4
  file map, offline Mock Agent workflow, real-model workflow, expected negative
  outcomes, and the instruction not to commit `.env`.
- Generated the deterministic baseline at
  `scenarios/scenario-04-security-briefing/eval/results/mock-baseline/`.

## Verification evidence

Executed from `scenarios/scenario-04-security-briefing`:

```bash
PYTHONPYCACHEPREFIX=/tmp/scenario4-pycache python3 -m compileall -q eval
cd eval && python3 run_tests.py
```

Result: compilation succeeded; 32 tests passed.

Executed from `scenarios/scenario-04-security-briefing/eval`:

```bash
python3 run_eval.py --mock-agent --run-dir results/mock-baseline
```

Result: 20 of 20 cases completed. The code-grader overall pass rate is 0.90 because
the two designed negative cases have `overall_pass=false`.

Validated the results JSON invariants:

- `summary.total == 20`
- `summary.completed == 20`
- Every case has `status == "completed"`
- `S04-019` fails only `masking_check`
- `S04-020` fails only `push_target`
- Every other case passes every deterministic Code Grader
- The CSV report uses LF line endings, so the generated baseline is clean under
  `git diff --check`.

## Generated baseline artifacts

- `eval_results.json`: full per-case results and manifest.
- `eval_summary.csv`: compact per-case status and grader matrix.
- `run_manifest.json` and `checkpoints/`: run provenance and resumable per-case
  checkpoints, all confined to Scenario 4's `results/mock-baseline/` directory.

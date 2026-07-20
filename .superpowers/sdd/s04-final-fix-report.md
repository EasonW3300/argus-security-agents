# Scenario 4 Final Fix Report

## Result

**DONE** — all Critical and Important findings in `s04-final-review.md` are addressed without changing any Scenario 2 result directory.

Commit containing the implementation and regenerated Scenario 4 baseline:

`1f4592e fix(s04): harden eval contract and resume provenance`

## Delivered fixes

1. Added the required, authoritative Scenario 4 delivery inputs to Git: `EvalsData.json`, `agent-architecture.md`, `eval-design.md`, and `eval-generation-prompt.md`.
2. Made `data_accuracy` and `template_completeness` enforce every section's `required_data` mapping, exact source-path/value binding, Ground Truth paths (including `.length`, indexed strings, and derived percentages), and metric declarations in the rendered body. Regressions cover omitted S04-001 required fields and a total replaced with source value `23`.
3. Established the output audit contract: `data_source_mapping` is `metric name -> source path`; same-key `data_values` stores actual JSON values; masking records are `{original, masked, rule}`. The Schema validates nested mapping/value keys, non-empty titles, ISO-8601 metadata timestamps, and a non-empty `data_sources_used` string list. Prompt, mock agent, architecture, design, generator prompt, and tests now use the same contract. Management masking scans only the visible report view, deliberately excluding internal `data_values` and masking audit originals.
4. Added pre-processing run provenance. The manifest and every checkpoint record dataset SHA-256, mock/real agent mode, public Agent/Judge provider/model/response-mode configuration, and grader mode. `--resume` ignores completed checkpoints unless both prior manifest and checkpoint provenance exactly match; regressions prove recomputation after dataset and mock/real-mode changes.
5. Follow-up final-review hardening: required object/list data now recursively verifies every scalar leaf in the corresponding rendered body. Numeric leaves accept only their correct number or float-ratio percentage rendering; management-sensitive leaves may use an explicit `masking_applied` replacement. The S04-001 TOP-rules regression proves that retaining only `alert_stats.top_rules` while deleting rule names, counts, and changes fails both `data_accuracy` and `template_completeness`.
6. Final masking hardening: a masking replacement is accepted only for a management case with `masking_rules.enabled=true`, where the audit record's `original` matches a `should_be_masked=true` sensitive pattern and its `rule` is that exact pattern. Security-lead/disabled-masking reports must retain raw leaves. Regressions reject forged S04-001 TOP-rule masking records and management records with a non-sensitive rule.

## Verification

Run from `scenarios/scenario-04-security-briefing/eval`:

| Command | Result |
| --- | --- |
| `PYTHONPYCACHEPREFIX=/tmp/scenario4-final-pycache python3 -m compileall -q .` | Exit 0 |
| `python3 run_tests.py` | 44 tests passed |
| `python3 run_eval.py --mock-agent --run-dir results/mock-baseline` | 20/20 completed; all positive cases pass deterministic graders |
| `rm -rf /tmp/s04-final-clean && python3 run_eval.py --mock-agent --run-dir /tmp/s04-final-clean` | 20/20 completed |
| `git archive --format=tar HEAD | tar -x -C <temp>` followed by compile, tests, and mock run in the extracted tree | Exit 0; the tracked dataset and all three design documents are present; 44 tests and 20/20 mock cases pass |

The regenerated baseline and clean archive both have exactly the intended negative-case failures:

- `S04-019`: only `masking_check`
- `S04-020`: only `push_target`

No provider-backed smoke test was run because that requires explicit credentials/authorization; the mock and adapter-level coverage remain offline and deterministic.

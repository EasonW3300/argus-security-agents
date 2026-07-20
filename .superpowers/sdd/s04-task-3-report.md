# S04 Task 3 Report — Code Graders

Implemented deterministic grading for Scenario 04 in
`scenarios/scenario-04-security-briefing/eval/code_graders.py`.

- `data_accuracy` validates Ground Truth source values and derived percentages
  with an absolute ±0.1 percentage-point tolerance.
- `template_completeness` requires the exact ordered section IDs, non-empty
  bodies, and no `{{placeholder}}` residue.
- `format_compliance` validates balanced code fences, non-skipping Markdown
  headings, and table column consistency.
- `masking_check` scans the complete serialized output (content, mappings, and
  metadata) for management-sensitive leaks and verifies security-lead required
  technical values remain present.
- `push_target` compares channel and recipients exactly.
- `output_schema` delegates to the existing structured output validator.

Added `GraderResult` to `schemas.py` because the task interface required a
shared result dataclass but it was not previously defined.

Test coverage includes a positive mock case, S04-019 sensitive-data leak,
S04-020 recipient mismatch, derived-percentage tolerance, security-lead value
retention, and malformed Markdown/schema output.

Verification: `python3 -m unittest discover -s tests -v` passed 23 tests.
All S04-001 through S04-018 mock positive cases pass every code grader;
S04-019 fails only `masking_check`, and S04-020 fails only `push_target`.

## Review follow-up

`data_accuracy` now validates each Ground Truth source path against its actual
`data_source_mapping` declaration, including `.length`, indexed paths, and
non-numeric strings. It also rejects untraceable contradictory numbers in the
body while ignoring section headings and mapping labels. Derived ratios are
checked in their own mapped section and reject a second, contradictory ratio.
The mock agent now resolves those source paths and emits explicit declarations
when Ground Truth is more granular than the template's source path. It also
emits a level-one Markdown heading from every template title.

New regressions cover S04-001's appended `999`, the absent S04-003 count
mapping, the absent S04-005 indexed IP mapping, and a missing body heading.
Final verification: `python3 -m unittest discover -s tests -v` passed 27
tests; all S04-001 through S04-018 mock positive cases pass every code grader.

# Per-task self-check.sh

Every real task revision has an independent Bash entry point, while business checks reuse the common runner. During preparation, tests may fail because the business feature is not implemented yet, but missing tests must never produce PASS. The kernel generates the script content; the planner provides the real test sources and configuration.

~~~bash
export PLANNER_KERNEL_HOME="/absolute/path/to/planner-kernal"
bash "$PROJECT_ROOT/tmp_plan/checks/TASK-001/R001/self-check.sh" \
  --project "$PROJECT_ROOT" --session SESSION-001 \
  --result tmp_plan/results/TASK-001-run-001.json
~~~

The result path must be new and inside the project's tmp_plan; it must not overwrite an earlier result. Run self-checks in a valid execution session; they generate evidence but do not change task state. Then connect the result to review with submit_evidence and request_review.

## Module and check definitions

Each module contains id, purpose, boundary_required, boundary_reason, and check_ids.
Each check contains id, module_ids, case, argv, cwd, test_sources, expected, timeout_seconds, required, and adapter. check_ids and module_ids must agree in both directions.

- Each module needs at least one required normal check.
- When boundary_required is true, it also needs a required boundary check; otherwise state why a boundary check does not apply.
- A multi-module task needs at least one required integration check covering multiple modules.
- One check may verify module interaction, but an unrelated test report cannot be copied to each module as coverage.

argv is an argument array and is not concatenated through a shell. Supported placeholders are: {python}, {project}, {report}, {work}, and {unittest_report}. cwd, test_sources, tested_paths, and context_refs are project-relative paths.

~~~json
{
  "id": "CHECK-NORMAL",
  "module_ids": ["MODULE-PARSER"],
  "case": "normal",
  "argv": ["{python}", "{unittest_report}", "--report", "{report}", "tests.test_parser.ParserTests.test_normal"],
  "cwd": ".",
  "test_sources": ["tests/test_parser.py", "tests/helpers.py"],
  "expected": "Valid input parses to the expected structure",
  "timeout_seconds": 60,
  "required": true,
  "adapter": "unittest"
}
~~~

## Report adapters

unittest uses the built-in unittest_report.py to record every real case and failed subtest; expected failures and skips do not count as required checks passing. The project import path comes from the project's existing environment or cwd.

junit requires the project framework to write {report}, parses testcases, and verifies that any tests/failures/errors/skipped totals match the real cases; DTD is not supported. A framework that only prints text and produces no report cannot pass.

json uses an explicit assertion report:

~~~json
{"tests": [{"id": "normal-case", "status": "PASS", "message": "actual value equals expected value"}]}
~~~

status may be PASS, FAIL, SKIP, or BLOCKED; ID must be nonempty and unique. message is optional. This JSON must be produced by assertions that actually ran, not by a fixed success template.

## Aggregation and evidence

Return 0 only when every required module passes. An assertion failure returns 1; missing dependencies, zero cases, or a required skip returns 2; timeouts, corrupt reports, and unexplained execution contradictions return 3. Priority is ERROR > FAIL > BLOCKED > PASS, and ordinary failures do not stop collection of other module results.

The report binds plan_id, task revision, the actual script and test sources, configuration, runner, required inputs, and tested-file hashes. Verify these again when registering the report and confirm that the summary matches the raw report. Old evidence cannot continue to prove a pass after test or tested-file changes.

When a task enters ready, the kernel freezes check_source_hashes; changing assertions requires a new revision. For a task revision, choose the most recently registered result by registered_revision. A latest failure cannot fall back to an old PASS, and an old report cannot be registered again to erase a failure.

Create test temporary files only in the isolated work directory. The runner cleans up the work directory and child processes it created while preserving reports and log attachments. It is not a business-program sandbox; do not disguise scripts that install, publish, access the network, or modify business files as minimal unit tests.

At least one self-check must be validated with a counterexample that intentionally breaks business behavior, proving that the assertion really fails. Structural checks, fixed exit 0, echo PASS, and importing a module alone cannot replace functional verification.

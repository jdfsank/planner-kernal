# Planners, executors, and accepters

## Before creating a task

Read the target project's actual implementation, constraints, existing tests, and user requirements. The JSON `goal` defines the objective; external documents are source references, not additional execution authorization. A Stage describes an observable capability, while a Task is an independent implementation and acceptance boundary; keep continuous internal edits as Steps.

A Task may contain multiple internal modules but owns one independently versioned public Output contract. Put related API methods in one logical contract object instead of creating a task for each method. Split different public artifacts only when they need independent revisions, consumers, and acceptance.

Each Step should make all four fields concrete:

```json
{
  "action": "Reject non-string or whitespace-only input in slug before applying lower/split/join; preserve the existing call signature",
  "path": "subject.py",
  "expected": "Hello   WORLD becomes hello-world; empty input raises ValueError",
  "verification": "Run CHECK-NORMAL and CHECK-BOUNDARY and inspect the actual value and exception"
}
```

Avoid instructions such as “improve the module” or “make it correct.” When investigation is incomplete, list the questions in `unresolved` and create an investigation task with explicit questions, sources, and result formats. Investigation tasks also need a machine-verifiable minimum delivery contract; accept facts, design, and visual judgments separately.

`context_refs`, `test_sources`, and `tested_paths` must be actual project-relative files, not vague directories or URLs. Include indirectly imported test helpers and important fixtures in `test_sources`, and configurations that affect results in `context_refs`. Put external URLs mentioned by the plan into the Goal's `sources`.

## Create and save

Use one `define_entity` operation to submit the mutually referencing Goal, Stage, Task, and initial Output. Defining a task automatically generates its revision-bound shell script, but the planner writes or reuses the business tests and verifies their real entry point before the task reaches ready.

Tasks start as `planned / unknown / pending`, and Stages start as `planned`. Definition does not mean the user approved implementation. When the user wants planning only, `archive_pending_plan` saves a snapshot and clears the execution session. Development plans and verification output are development records, not runtime state in the target project.

## Executor

1. After explicit enablement, run `resume`; read `freshness_warnings`, next steps, and preparation candidates.
2. After the user requests implementation, run `claim_session`; export the current Task and verify its revision and required inputs.
3. Use `set_ready` to confirm the gates and `start_task` to enter active; edit only owned paths and do not expand the interface or scope.
4. Implement each Step. If check behavior or an interface must change, return for planner revision instead of weakening assertions to obtain PASS.
5. Use the task shell script and register the result; repair self-check failures through the diagnostic path. On success, use `request_review`.
6. Return changed files, real check results, evidence IDs, deviations, and incomplete items. Do not claim an independent review was completed.

Pause a conversation with `pause` to save a snapshot and release the session. After a crash, a new conversation cannot take over based only on elapsed time; use a new session ID, the old session ID, and `old_stopped: true` to make the takeover explicit. `old_stopped` is an operator's factual declaration; the kernel cannot prove across hosts that the old agent has stopped.

## Accepter and correction

- Task: inspect the original objective, diff, module tests, and evidence freshness; bind `record_acceptance` to the current task revision.
- Stage: after all members pass, really execute module_checks and integration_checks; record review evidence, then use `stage_review`, and finally record Stage acceptance.
- Goal: return to success_criteria for acceptance; a self-check report cannot stand in for experience, research facts, or visual evidence.
- Return implementation defects to the Task, incompatible public contracts to the Output provider, composition failures to the Stage, and changed purpose or scope to the Goal.

`revise_entity` and `revise_contract` archive old data first, then create the revision and propagate invalidation. Old acceptances remain unchanged. Rebinding inputs for an unaccepted task creates a new Task revision; explicitly revise an accepted task first. Compatible artifact revisions must preserve the semantic fingerprint.

Do not revive a completed or cancelled plan in place. When the user requests follow-up work, explicitly use `new_plan`; preserve the old archive and evidence index and create a new plan_id. Evidence from the old plan cannot prove the new plan.

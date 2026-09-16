# JSON contract and CLI

The formal contract is [contract.schema.json](../schemas/contract.schema.json). `schemas.py` is the source of generation, and runtime validation uses the same vocabulary; tests require the exported Schema to match the source. Semantic validation handles cross-entity references, dependencies, and acceptance gates.

Python 3.12.12 managed by uv, Bash, POSIX file locks, and process groups are required. macOS/Linux are supported; use WSL on Windows. Project dependencies are not installed automatically.

## Initialize and read

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" init --project "$PROJECT_ROOT" --explicit
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" resume --project "$PROJECT_ROOT"
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" query --project "$PROJECT_ROOT" --type tasks --id TASK-001
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" query --project "$PROJECT_ROOT" --type modules --id MODULE-001
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" export-module --project "$PROJECT_ROOT" --module MODULE-001
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" impact --project "$PROJECT_ROOT" --contract CONTRACT-001
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" query --project "$PROJECT_ROOT" --type evidence --subject TASK-001 --revision 1 --status PASS
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" validate --project "$PROJECT_ROOT"
```

`init --explicit` means the user explicitly enabled the skill for this invocation; a script cannot acquire that authorization automatically. Git exclude is the only configuration that initialization may write outside `tmp_plan/`; use `--no-git-exclude` to disable it explicitly.

`validate` returns structural results and freshness warnings separately; structural PASS does not mean functional acceptance PASS. `resume` does not write state and returns currently relevant entities rather than complete history. `preparable_task_ids` are candidates a planner may inspect and try to set ready; they are not directly executable. `review_task_ids` contains Tasks whose current PASS evidence is fresh and whose status is `ready_for_review`; stale review evidence appears in `freshness_warnings` and removes the Task from that list.

## Write envelope

```json
{
  "schema_version": 2,
  "operation_id": "OP-SAVE-001",
  "expected_revision": 0,
  "session_id": "",
  "kind": "save_checkpoint",
  "data": {"summary": "Goal is clear; awaiting execution", "next_steps": ["Review TASK-001"]}
}
```

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" apply --project "$PROJECT_ROOT" --input operation.json
```

Use a new ID for every new operation. Retry an original operation with its original ID, expected_revision, session_id, and content; the kernel returns the original receipt. Reusing an ID with different content returns CONFLICT. Reread and coordinate after a stale revision; never overwrite blindly.

| kind | Required data fields and behavior |
|---|---|
| define_entity | `entities: [{type, value}]`; create Goal, Architecture, Contract, Module, Connection, Stage, Task, Output, Decision, or Blocker entities with initial revision 1. Stage and Task definitions require a baselined Architecture |
| revise_entity | Same shape; increment an existing entity's revision, and use revise_contract for outputs; reset Task status to planned/unknown/pending |
| archive_pending_plan | `{}`; archive as awaiting_execution; resolve active/review work first rather than presenting it as unexecuted |
| claim_session | `{id, owner}`; claim a session and enter executing when no valid session exists |
| take_over_session | `{old_id, id, owner, old_stopped: true}`; use a new session ID |
| save_checkpoint | `{summary, next_steps}` |
| set_ready | `{task_id}`; preparation checks and dependencies must be satisfied |
| start_task | `{task_id}`; when resuming active work, also pass `acknowledge_resume: true` and provide a valid session |
| rebind_inputs | `{task_id}`; bind current inputs for an unaccepted task, creating a new task revision when inputs change |
| submit_evidence | `{id, path}`; path is a result JSON under tmp_plan, which is validated and registered as an immutable copy |
| request_review | `{task_id}`; request review with a valid session after current module self-checks PASS |
| stage_review | `{stage_id, evidence_ids}`; all tasks pass and evidence covers module and integration checks |
| record_acceptance | `{acceptance}`; a Schema acceptance object bound to revisions, criteria, evidence, and review_mode |
| revise_contract | `{output}`; increment the revision, require the fingerprint to match the contract, and preserve semantics for compatible revisions |
| pause / block / cancel | `{}`; save a snapshot and release the execution session |
| complete | `{}`; verify that the goal and stages pass, then recheck current tasks and acceptance evidence |
| new_plan | `{reason}`; available only for completed/cancelled plans without a session; preserve history and create a new plan_id |

With a valid session, every operation except claiming or taking over must carry its ID. Roles are a collaboration protocol, not security authentication for the shared file system.

## Revisions and evidence

`revision` is a positive integer. The revision 1 Task script is `tmp_plan/checks/TASK-001/R001/self-check.sh`. A Goal defines purpose and criteria. An Architecture defines the complete in-scope module tree and connection graph. A Task binds `architecture_id`, `architecture_revision`, and `module_ids`; stale bindings are rejected.

Contracts carry typed structure, semantic rules, error behavior, side effects, and a fingerprint of all contract fields except the fingerprint itself. Modules expose typed input and output ports. Every input port must have exactly one Connection whose contract matches both endpoints. Use `query`, `export-module`, and `impact` to locate a module and inspect its consumers before revision.

Entity IDs remain unique within a project and are not reused after `new_plan`. Follow-up Tasks use new IDs, avoiding confusion between old packets or `.sh` scripts and same-named, same-revision Tasks in the new plan.

Archives do not reference their own indexes. Persist all new records before atomically committing state; interrupted writes leave unreferenced files in diagnostics. Do not delete them automatically or count them as committed state. Investigate or restore a known copy when a record hash is corrupted; never overwrite history to remove the warning.

Manual Goal/Stage review evidence uses the Schema's `review_evidence`: specify method, expected, actual, criteria, reviewer, and review_mode; include the current plan_id, subject_revisions, tested-file bindings, and original attachments.
`subject_revisions` includes the Stage and its member Task revisions for a Stage, and the Goal, Stage, and member Task revisions for a Goal. Every related tested_path must be bound to a file hash. Manual observations must actually be completed; a generator cannot write PASS on their behalf.

Evidence can use `supersedes` to reference older evidence for the same subject. Correcting an acceptance record must explicitly supersede the current acceptance for the same subject and revision; do not create contradictory parallel results.

## Example

Copy the files in the [software](../examples/software/definition.json) or [research](../examples/research/definition.json) directory into a dedicated demonstration project. Each definition includes a reviewed Architecture, Module, and Contract. After explicit init, use apply to submit definition.json, then set_ready, claim_session, and start_task.
The examples include runnable implementations and positive/negative cases. They demonstrate the protocol but do not replace development of the user's project. The research example validates only the minimum source contract for structured records; it does not prove that cited content supports a claim.

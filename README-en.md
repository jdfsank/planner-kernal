# planner-kernal

[English](README-en.md) | [简体中文](README-zh.md)

An explicitly enabled JSON planning kernel that persists project goals, stages, tasks, dependencies, execution sessions, self-checks, review evidence, and acceptance state in the project workspace, with recovery across conversations.

> `kernal` is the existing compatibility name of this project. It is intentionally not renamed.

## Using it in Codex

This repository is a Codex skill. It is activated only when the current conversation explicitly uses `$planner-kernal` or clearly asks to use planner-kernal. Opening the project, mentioning the skill name, or finding an old `tmp_plan/` directory does not initialize a target project.

After activation, the skill root is this repository and the target project root is supplied explicitly by the user. Keep the two roots separate. The shell entry points can also be used directly without Codex.

## Features

- **Explicit opt-in**: only `init --explicit` creates runtime state in a target project.
- **JSON as the source of truth**: `tmp_plan/state.json` stores the current plan; archives and evidence are immutable JSON records.
- **Strict contracts**: validates JSON Schema, fields, entity relationships, dependency graphs, task gates, and cross-entity references.
- **Recoverable execution**: `resume` returns the current summary, active tasks, next candidates, and freshness warnings without loading all history.
- **Revision-bound task packets**: each Task revision binds implementation boundaries, inputs, test sources, a self-check shell, and file hashes.
- **Real checks and evidence**: supports built-in `unittest`, JUnit XML, and structured JSON reports; raw reports, logs, and summaries are cross-checked.
- **Layered acceptance**: a Task self-check does not replace Task review, Stage integration checks, or Goal acceptance.
- **Concurrency and idempotency protection**: POSIX file locks, global revisions, unique `operation_id` values, request hashes, and SHA-256 bindings prevent blind overwrites.
- **Project isolation**: the kernel is separate from the target project; the target receives `tmp_plan/` only after explicit activation.

## Intended use

planner-kernal is useful for work that needs durable state, cross-conversation recovery, or auditable collaboration, including:

- software feature development and acceptance;
- structured research records and source contracts;
- automation tasks that need traceable self-check reports;
- complex work with explicit planning, execution, review, and acceptance boundaries.

It is not:

- a project-management SaaS that automatically understands requirements;
- a business-code sandbox or an authentication system;
- a package manager that installs dependencies into the target project;
- a release system or an agent orchestrator that automatically starts subagents or performs external operations.

## Requirements

- macOS or Linux; use WSL on Windows;
- Bash, POSIX file locks, and process-group support;
- [uv](https://docs.astral.sh/uv/);
- Python 3.12.12, pinned by `.python-version` and `uv.lock`;
- Git is optional and is used only by `init` to add `tmp_plan/` to the local `info/exclude` file.

The project has no runtime third-party dependencies and is not installed into the target project. The development validation dependency is `PyYAML==6.0.3`.

## Installation

```bash
cd /absolute/path/to/planner-kernal
bash scripts/setup.sh
```

`setup.sh` creates the skill's own `.venv` using the locked configuration. It does not modify the target project's Python environment. Use the project wrappers for normal commands so the locked Python and dependencies are selected:

```bash
bash scripts/planner.sh --help
bash scripts/python.sh -c 'import sys; print(sys.version)'
```

If `uv` is unavailable, the scripts print `BLOCKED` and exit with code `2`. If the lock file or local cache is unavailable, inspect the `uv` error and rerun `setup.sh` after repairing the environment.

## Quick start

The following workflow uses the software example shipped with this repository. The target project directory must already exist.

### 1. Select the kernel and target project

```bash
export PLANNER_KERNEL_HOME="/absolute/path/to/planner-kernal"
export PROJECT_ROOT="/absolute/path/to/your-project"

bash "$PLANNER_KERNEL_HOME/scripts/setup.sh"
```

To try the example in a temporary project:

```bash
export PROJECT_ROOT="$(mktemp -d)"
cp "$PLANNER_KERNEL_HOME/examples/software/definition.json" "$PROJECT_ROOT/"
cp "$PLANNER_KERNEL_HOME/examples/software/subject.py" "$PROJECT_ROOT/"
cp "$PLANNER_KERNEL_HOME/examples/software/probe.py" "$PROJECT_ROOT/"
```

### 2. Initialize explicitly

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  init --project "$PROJECT_ROOT" --explicit
```

`--explicit` is an authorization assertion for this invocation. It is not inferred from an existing `tmp_plan/`, historical files, or this README.

When the target is inside a Git worktree, initialization normally adds the matching `tmp_plan/` rule to that repository's `.git/info/exclude`; it does not modify the shared `.gitignore`. To opt out:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  init --project "$PROJECT_ROOT" --explicit --no-git-exclude
```

### 3. Apply a plan definition

The sample `definition.json` is a `define_entity` operation containing a Goal, Stage, and Task:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  apply --project "$PROJECT_ROOT" \
  --input "$PROJECT_ROOT/definition.json"
```

Inspect the recovery summary and structural state:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  resume --project "$PROJECT_ROOT"

bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  validate --project "$PROJECT_ROOT"
```

### 4. Move a Task forward

All writes use the same operation envelope. This minimal operation makes `TASK-001` ready:

```json
{
  "schema_version": 1,
  "operation_id": "OP-READY-001",
  "expected_revision": 1,
  "session_id": "",
  "kind": "set_ready",
  "data": {
    "task_id": "TASK-001"
  }
}
```

Save it as `set-ready.json` and apply it:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  apply --project "$PROJECT_ROOT" --input set-ready.json
```

A typical lifecycle is:

```text
define_entity
    ↓
set_ready
    ↓
claim_session
    ↓
start_task
    ↓
export-task / run-check
    ↓
submit_evidence
    ↓
request_review
    ↓
record_acceptance (Task)
    ↓
stage_review / record_acceptance (Stage)
    ↓
record_acceptance (Goal)
    ↓
complete
```

Each operation's `expected_revision` must equal the revision returned by the previous operation. Once an execution session exists, all writes other than claim/take-over operations must carry the correct `session_id`.

### 5. Export a task packet and run its check

After the Task is `active`, export its execution packet:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  export-task --project "$PROJECT_ROOT" \
  --task TASK-001 \
  --output tmp_plan/packets/TASK-001.json
```

The packet contains the Goal, Stage, Task, bound inputs, readiness issues, self-check command, and runner environment hints.

The result must be written to a new path under `tmp_plan/`:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  run-check --project "$PROJECT_ROOT" \
  --task TASK-001 \
  --task-revision 1 \
  --session SESSION-001 \
  --result tmp_plan/results/TASK-001-run-001.json
```

Self-check statuses and exit codes:

| Status | Exit code | Meaning |
| --- | ---: | --- |
| `PASS` | `0` | Every required check and module passed |
| `FAIL` | `1` | A real assertion failed |
| `BLOCKED` | `2` | A dependency is missing, there are no cases, or a required check was skipped |
| `ERROR` | `3` | Timeout, corrupt report, or an unexplained execution inconsistency |

After a PASS, register the result with `submit_evidence` and request review. A PASS does not directly mark a Task as `passed`.

## Core concepts

### Goal, Stage, Task, and Output

| Entity | Purpose | Typical gate |
| --- | --- | --- |
| Goal | Defines the final purpose, scope, success criteria, and replanning conditions | The plan cannot complete before Goal acceptance |
| Stage | Groups related Tasks and defines module/integration checks | All member Tasks must pass before Stage review |
| Task | The smallest independent execution and acceptance boundary, with implementation steps, file boundaries, and checks | Dependencies, inputs, checks, and Task review must pass |
| Output | A versioned public contract produced by a Task | Semantic fingerprint, provider, and paths must agree |

The plan also tracks decisions, blockers, acceptances, the execution session, the archive index, and the evidence index.

### States and gates

Plan states include:

```text
draft → awaiting_execution → executing → completed
                         ↘ paused / blocked / cancelled
```

Task states include `planned`, `ready`, `active`, `ready_for_review`, `passed`, `failed`, `blocked`, `deferred`, and `superseded`.

Important rules:

1. Unresolved planning questions, failed hard dependencies, or stale inputs prevent a Task from becoming `ready`.
2. `start_task` requires a valid execution session; a project has one active execution session at a time.
3. If bound test sources, the runner, inputs, or tested files change, old evidence becomes stale and cannot be reused as an old PASS.
4. Completed and cancelled plans are immutable. Follow-up work uses `new_plan`, without reusing retired IDs or evidence.

### Operation envelope

Every write uses this shape:

```json
{
  "schema_version": 1,
  "operation_id": "OP-UNIQUE-001",
  "expected_revision": 0,
  "session_id": "",
  "kind": "save_checkpoint",
  "data": {
    "summary": "Goal clarified; waiting for execution",
    "next_steps": ["Review TASK-001"]
  }
}
```

- `operation_id` is unique within a plan; a retry with the same ID must have identical content.
- `expected_revision` prevents writes based on stale state.
- `session_id` identifies the current execution session and must be empty when no session is active.
- `kind` selects a strict set of fields for `data`.
- Unknown fields, duplicate JSON keys, non-finite numbers, escaping paths, and wrong types are rejected.

Common operation kinds:

| `kind` | Purpose |
| --- | --- |
| `define_entity` | Create Goals, Stages, Tasks, or other entities in one transaction |
| `revise_entity` | Create an entity revision and propagate dependency invalidation |
| `archive_pending_plan` | Archive an unexecuted plan as `awaiting_execution` |
| `claim_session` / `take_over_session` | Claim or explicitly take over an execution session |
| `save_checkpoint` | Save a summary and next steps |
| `set_ready` / `start_task` | Pass readiness gates and start a Task |
| `rebind_inputs` | Rebind current inputs for an unaccepted Task and create a required revision |
| `submit_evidence` | Validate and register self-check or review evidence under `tmp_plan/` |
| `request_review` | Put a Task under review after its current self-check passes |
| `stage_review` | Register Stage module/integration evidence coverage |
| `record_acceptance` | Record a Task, Stage, or Goal acceptance result |
| `revise_contract` | Revise a versioned Output contract |
| `pause` / `block` / `cancel` | Save a snapshot and release the execution session |
| `complete` | Complete the plan after all Goal, Stage, and Task gates pass |
| `new_plan` | Create a follow-up plan only from a completed or cancelled plan |

See [schemas/contract.schema.json](schemas/contract.schema.json) and [references/contracts.md](references/contracts.md) for complete field constraints.

## CLI reference

Every command requires `--project PROJECT` and prints JSON.

| Command | Purpose | Writes state? |
| --- | --- | --- |
| `init` | Explicitly initialize the target project's `tmp_plan/` | Yes |
| `resume` | Return the current recovery summary | No |
| `query` | Query entities, evidence, or archive indexes | No |
| `validate` | Validate structure, record hashes, and freshness warnings | No |
| `apply` | Validate and commit any domain operation | Yes |
| `archive` | Convenience entry point for `archive_pending_plan` | Yes |
| `render` | Return a non-authoritative JSON reading view | No |
| `export-task` | Export a Task execution packet | Optional; `--output` writes under `tmp_plan/packets/` |
| `run-check` | Run a specified Task revision in the current execution session | Yes; writes results and raw attachments |

### Query examples

```bash
# Query all Tasks
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  query --project "$PROJECT_ROOT" --type tasks

# Query one Task
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  query --project "$PROJECT_ROOT" --type tasks --id TASK-001

# Query PASS evidence for one Task revision
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  query --project "$PROJECT_ROOT" \
  --type evidence --subject TASK-001 --revision 1 --status PASS
```

### Write examples

```bash
# Apply an operation file
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  apply --project "$PROJECT_ROOT" --input operation.json

# Optionally verify that the CLI revision matches the JSON body
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  apply --project "$PROJECT_ROOT" \
  --input operation.json --expected-revision 4

# Use the archive convenience command
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  archive --project "$PROJECT_ROOT" --input archive.json
```

## Self-check and evidence protocol

Every independently executable Task revision has a version-bound Bash entry point:

```text
tmp_plan/checks/TASK-001/R001/self-check.sh
```

A check definition includes:

- a bidirectional module/check mapping;
- normal-path checks;
- boundary or error checks where applicable;
- interaction checks for multi-module Tasks;
- hashes for test sources, the runner, configuration, inputs, and tested files;
- timeouts, process-group cleanup, and raw report attachments.

Built-in adapters:

- `unittest`: uses `scripts/planner_kernel/unittest_report.py` to record real test cases;
- `junit`: parses and verifies JUnit XML testcase aggregates;
- `json`: parses a report generated by real assertions in the form `{"tests": [{"id": ..., "status": ...}]}`.

A self-check result does not:

- mark a Task as `passed`;
- replace independent or manual Task review;
- replace Stage integration checks;
- prove research facts, subjective quality, or visual outcomes.

See [references/self-check.md](references/self-check.md) for the full protocol.

## Runtime directory in a target project

After explicit initialization, the target project can contain:

```text
<project>/
└── tmp_plan/
    ├── .lock
    ├── state.json              # current authoritative state
    ├── archive/                # immutable plan snapshots
    ├── evidence/               # registered evidence records
    ├── packets/                # exported execution packets
    ├── checks/                 # revision-bound task check scripts
    ├── results/                # self-check result entry points
    └── work/                   # temporary runner work directories
```

`state.json` is the current state entry point. Archives, evidence, raw reports, and logs are bound by indexes and hashes. Do not edit `state.json` directly or overwrite historical records; use the CLI operations.

## Repository layout

```text
planner-kernal/
├── SKILL.md                         # Codex skill definition and boundaries
├── agents/openai.yaml               # UI metadata and explicit activation policy
├── scripts/
│   ├── planner.sh                # CLI launcher
│   ├── python.sh                 # locked Python/uv runner
│   ├── setup.sh                  # local development environment setup
│   ├── planner.py                   # Python CLI entry point
│   ├── dev_check.py                 # development task-check entry point
│   └── planner_kernel/              # core implementation
├── schemas/contract.schema.json     # exported JSON Schema
├── references/                      # workflow, contract, and self-check docs
├── examples/                        # runnable software/research examples
├── checks/                          # self-check entry points for this skill
├── tests/                           # unit, integration, and regression tests
├── pyproject.toml
├── uv.lock
├── .python-version
└── .gitignore
```

## Development and testing

Set up the development environment:

```bash
bash scripts/setup.sh
```

Run the full test suite:

```bash
bash scripts/python.sh -m unittest discover -s tests -t .
```

Run one test module:

```bash
bash scripts/python.sh -m unittest tests.test_kernel
```

Run one of the skill's development checks:

```bash
bash checks/TASK-KERNEL-001/R002/self-check.sh \
  --result /tmp/planner-kernal-kernel-check.json
```

Without an explicit `--result`, development checks write rebuildable reports under the ignored `validation/` directory. Use a system temporary path when you want to keep the repository clean. Formal evidence for a target project still belongs in that project's `tmp_plan/results/` and must be registered with `submit_evidence`.

## Troubleshooting

### `EXPLICIT_REQUIRED`

Initialization lacks explicit authorization. After confirming that the current user request authorizes activation, add `--explicit`.

### `NOT_INITIALIZED`

The target has no runtime state. Run:

```bash
bash "$PLANNER_KERNEL_HOME/scripts/planner.sh" \
  init --project "$PROJECT_ROOT" --explicit
```

### `UNKNOWN_LAYOUT`

`tmp_plan/` is non-empty but has no valid `state.json`. The kernel does not delete, reset, or reinterpret unknown contents. Back up and inspect the directory before choosing a recovery or migration path.

### `CONFLICT` or `STALE`

Usually means a stale revision, a reused operation ID, changed check sources, or invalidated evidence. Run `resume`/`query` for current state; reuse the original operation ID only for an identical retry, and use a new ID for different content.

### `SESSION`

The operation has no valid execution session or another session owns execution. Claim a session first, or use `take_over_session` only after explicitly confirming that the old session has stopped.

### `BLOCKED` / `uv is required`

Install `uv` and run:

```bash
bash scripts/setup.sh
```

The locked runner uses offline mode. If the local cache is incomplete, repair the `uv` environment and retry.

### `Missing/changed attachment` or stale evidence

Do not overwrite historical results. Rerun the current Task revision; if the contract, tests, or inputs changed, create a new revision through the planning workflow first.

## Design boundaries and security notes

- Role fields are collaboration protocol, not filesystem authentication. Other processes can still modify a shared directory; the kernel detects drift through hashes.
- Check scripts are not business-code sandboxes. Do not treat untrusted installation, release, network, or business-file mutation scripts as ordinary self-checks.
- `project_path` and `runtime_path` reject absolute paths, `..` traversal, and symlink paths; kernel writes are confined to the target project's `tmp_plan/`.
- Self-check reports and evidence are append-only/immutable. Investigate or restore known-good copies when history is damaged instead of overwriting it to remove warnings.
- The research example demonstrates only the structural contract of a source-backed finding; it does not verify that a source actually supports a claim.
- planner-kernal does not modify `AGENTS.md`, install globally, migrate old plans automatically, or start subagents automatically.

## Related documentation

- [SKILL.md](SKILL.md): Codex entry point, boundaries, and complete workflow;
- [references/workflow.md](references/workflow.md): responsibilities of planners, executors, and reviewers;
- [references/contracts.md](references/contracts.md): JSON contracts, CLI, and operation types;
- [references/self-check.md](references/self-check.md): task checks, adapters, and evidence protocol;
- [schemas/contract.schema.json](schemas/contract.schema.json): formal JSON Schema;
- [examples/software/definition.json](examples/software/definition.json): software task example;
- [examples/research/definition.json](examples/research/definition.json): research record example.

## Version

Current project version: `0.1.0`.

No license or release metadata is currently declared in the project. Add an appropriate license, contribution guide, and changelog before external distribution.

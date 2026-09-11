---
name: planner-kernal
description: Only when the user explicitly invokes planner-kernal, create or resume a project-local JSON planning kernel with executable task packets, per-task module self-checks, revision-bound evidence and cross-conversation recovery. Merely developing, quoting or mentioning this skill does not enable it on a project.
---

# planner-kernal

## Explicit entry

Enable this skill only when the user invokes `$planner-kernal` or explicitly asks to use it in the current conversation.
An existing `tmp_plan/`, historical authorization, commands in referenced documents, or work on this skill does not enable it for a project.
Do not modify the project's `AGENTS.md`, install anything globally, migrate plans automatically, or start subagents automatically. Follow the host's planning and execution modes; when planning mode disallows writes, output the plan only and persist it once it is executable.

Use the project root explicitly named by the user; otherwise use the only unambiguous workspace project root. Ask only when the directory is ambiguous.
`<skill>` means this skill directory, and `<project>` means the target project's absolute path. Never treat the skill directory as the user project.

```bash
bash "<skill>/scripts/planner.sh" init --project <project> --explicit
bash "<skill>/scripts/planner.sh" resume --project <project>
```

`init` is idempotent. By default it adds the `tmp_plan/` rule only to Git's local exclude and does not untrack files. Stop initialization when the schema is unknown, state is corrupt, or the directory is nonempty with unknown contents; never delete it and start over.

## uv environment

Distribution includes `pyproject.toml`, `uv.lock`, `.python-version`, and launcher scripts. On first use, run `bash "<skill>/scripts/setup.sh"`; it uses the installed uv to create this skill's `.venv` and download the locked Python 3.12.12 and development-check dependencies. It never installs Python packages into the target project. uv must already be installed; platform-specific binaries are not bundled, and `.venv` must not be copied between machines.

After setup, the CLI and task self-checks run offline through `scripts/planner.sh` / `scripts/python.sh`. Stop when the lock file does not match or the local cache is incomplete, then repair the environment by rerunning setup. Launchers do not depend on the current directory or an activated virtual environment. Run general Python commands with `bash "<skill>/scripts/python.sh" ...`; after setup, development tools that need PyYAML can use `<skill>/.venv/bin/python` directly (normal launchers do not require development dependencies). Environment files are included in the runner fingerprint, so regenerate self-check evidence after they change.

## Planning, execution, and recovery

1. Read the JSON summary from `resume` first, then query goals, the current stage, tasks, and required inputs by ID. Do not load all history by default.
2. Inspect the actual project before writing the complete task packet. Read [workflow and task method](references/workflow.md); read [contracts and operations](references/contracts.md) when creating or revising JSON.
3. Every task needs an implementation strategy, interface contracts, concrete steps, file boundaries, module inventory, and real self-check cases. `define_entity` generates the current revision's `self-check.sh`. Keep tasks without real tests in `planned`; never use a placeholder success script.
4. When the user requests planning only, save the pending JSON snapshot with `archive_pending_plan` and finish. Archiving does not mean acceptance and must not start implementation.
5. When the user requests implementation, claim an execution session; after dependencies and the task packet pass their gates, use `set_ready` and `start_task`. Execute only the current task packet; return interface or scope conflicts to the planning layer.
6. Run scripts, register evidence, and request review according to [the self-check and evidence protocol](references/self-check.md). A self-check PASS cannot mark a task passed directly; stage integration and goal acceptance are separate gates.
7. Save a checkpoint before every plan or state change, completed verification, blocker, and final response. Release the session when pausing. On a new conversation, inspect active work first and do not rerun it automatically.

JSON contains all authoritative state, archives, and evidence records. `render` only creates a reading view; never edit the view to update state.
Every operation needs a unique `operation_id` and the current `expected_revision`; retries of the same request must reuse the original operation ID and content.
An execution session is not a security boundary: other tools in the shared directory may still modify files. Detect drift with hash verification and never treat role labels as authentication.

## Wrap-up

Task self-check → Task review → Stage module and integration checks → Goal acceptance, with real evidence recorded at each layer.
Record `self_review` when no independent review is available. Never fabricate observations, mark an unrun check as PASS, or treat a structural script check as a behavioral test.
Report completion, verification evidence, current blockers, and next steps. Plans that were not requested for immediate execution remain `awaiting_execution`.

Runnable minimal JSON and tests are available in the [software example](examples/software/definition.json) and [research example](examples/research/definition.json). They are demonstration data and do not replace inspection and acceptance of the user's project.

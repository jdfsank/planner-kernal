# Minimum execution units: prepare, partition, review, adjust

## Meaning and stopping rule

A minimum execution unit is a complete, bounded work package that one executor can deliver and verify from the current packet without first inventing a major design, locating an unspecified implementation, or completing another independent work package. It uses the existing Task type. Goal, Architecture, Stage, Task, Step and acceptance retain their separate meanings.

Here the existing executable Task is the implementation-level subtask. A split adds prerequisite Tasks and a coverage trace; it does not add a universal nested node hierarchy. Module containment remains the product architecture, and Step remains an internal dependent action.

“Minimum” means the smallest useful independent delivery boundary for this project and execution budget. It does not mean one line, one function, one file, one tool call, or a universal duration. A change spanning two tightly coupled files can be one Task. Reading, editing and checking the same behavior are usually Steps. Separate an outcome when it has its own meaningful handoff/verification or when implementing the combined Task exceeds its stated budget. Reject a split that adds handoffs without resolving an execution obstacle.

A prepared unit has:

| Requirement | Concrete evidence in the packet |
|---|---|
| One bounded outcome | `outcome`, objective, exclusions and acceptance criteria describe the delivered behavior |
| Architecture sufficient for this change | Each referenced Module has a responsibility, data flow, implementation locations and relevant port Contracts in `architecture_basis` |
| Available inputs and decisions | Dependencies and bindings identify prerequisite deliverables; no unresolved material implementation question remains |
| Concrete execution path | Strategy and Steps say what changes where, expected intermediate results and verification; Steps declare `write`, `read` or `verify` access |
| Closed verification | `verification` covers each acceptance criterion exactly once with required check IDs and/or an explicit factual review method |
| Proportionate granularity | `granularity_reason` explains why remaining edits belong together, `execution_budget` defines the expected work session/resource limit, `stop_conditions` identify when to return for adjustment |

Readiness review must answer: Could another executor follow this packet without another substantial architecture/decomposition round? What remaining decisions are routine implementation choices? Why would further splitting improve or worsen completion? Findings must cite actual inspected locations, interfaces, dependencies and checks. A structurally complete packet can still fail this review.

## Apply the standard at all four points

1. **Architecture preparation:** Walk the proposed change from input to output. Identify responsibility, representation, transformation, interface/error behavior, implementation location and verification at each transition. Missing detail goes into design investigation or Architecture refinement before implementation partitioning.
2. **Task partitioning:** Derive bounded outcomes from that walk. Reuse modules across sequential Tasks, or span tightly coupled modules in one Task; keep dependency-internal actions as Steps. Prepare a verifiable research/design decision Task when evidence is missing rather than guessing an implementation.
3. **Executability review:** Export each current packet, inspect its basis and perform semantic review. Record one of the verdicts below. A future dependency need not pass just to review preparation, but must pass before readiness/execution.
4. **Necessary adjustment:** Resolve the diagnosed cause, atomically revise/create entities, preserve requirement coverage and work, and repeat review for every resulting Task. Do not assume that newly split prerequisites or the assembly Task are executable.

| Verdict | Required next action |
|---|---|
| `qualified` | No preparation gaps; wait for dependencies, then use `set_ready` and `start_task` |
| `needs_architecture` | Specify missing responsibility, data flow, interface/error behavior or location; rebaseline affected Architecture facts and reprepare Tasks |
| `needs_split` | Separate named independent outcomes or reduce excessive implementation load; preserve the original acceptance boundary |
| `needs_investigation` | Resolve a named uncertainty using bounded sources/questions and an explicit decision artifact before implementation |
| `blocked` | Identify unavailable resources/authorization/data and the unblocking condition; further splitting cannot supply them |

Only a `qualified` verdict with a matching Task revision and factual basis passes `set_ready` and `start_task`. Changed responsibilities, implementation refs, ports, relevant Contracts or incoming Connections stale the review. Inventory-only additions preserve a review when these facts stay equal. Runtime gates also check actual existing implementation files, dependencies, inputs, blockers and test files. Fields and a declared budget cannot prove semantic adequacy; the reviewer is accountable for that judgment, and self review must be labeled `self_review`.

## Preparation record

`execution_unit` belongs in the Task definition. For the supplied slug example, the core record is:

```json
{
  "outcome": "slug produces lowercase hyphenated words and rejects empty/non-string input",
  "architecture_basis": [{
    "module_id": "MODULE-001",
    "responsibility": "Normalize a title through the public slug function",
    "data_flow": "text -> input validation -> whitespace split -> lowercase/join -> slug string",
    "implementation_refs": ["subject.py"],
    "contract_ids": ["CONTRACT-001"]
  }],
  "verification": [
    {"criterion": "Hello WORLD becomes hello-world", "check_ids": ["CHECK-001"], "review_method": ""},
    {"criterion": "Empty input rejected", "check_ids": ["CHECK-002"], "review_method": ""}
  ],
  "granularity_reason": "Input validation and normalization implement one public behavior; a separate Task for each expression adds no independent handoff",
  "execution_budget": "One implementation session plus normal and boundary verification; reassess if a parser or new interface is needed",
  "stop_conditions": ["Call signature must change", "Normalization semantics are unresolved"]
}
```

After `export-task`, place the **actual inspected** `execution_preparation.review_basis` object in the review's `basis`. The following is a payload template, not a directly runnable whole operation (`CURRENT_BASIS` must be replaced by that object):

```json
{
  "task_id": "TASK-001",
  "review": {
    "task_revision": 1,
    "basis": {"CURRENT_BASIS": "replace with export-task.execution_preparation.review_basis"},
    "reviewer": "current-planner",
    "review_mode": "self_review",
    "verdict": "qualified",
    "findings": "Inspected subject.py and probe.py: the call boundary, normal/rejection cases and bounded implementation path are explicit; no unresolved design remains",
    "issues": []
  }
}
```

Submit with `kind: record_task_readiness` in the standard operation envelope. For an active Task returned for adjustment, include `checkpoint: {summary, next_steps}` in the same operation; record actual completed files/results and remaining work. An unrelated checkpoint's wording is not an automatic work-preservation guarantee.

## Atomic adjustment and preserved acceptance

Use `kind: adjust_plan`. `data` requires `reason`, `mode`, and `entities`, where each entry is `{action: create|revise, type, value}`. New IDs start at revision 1; revisions increment existing entities by one. Pass complete entity documents, not patches. Include the complete revised Architecture inventory when adding Modules. All structural/reference/dependency gates validate the final candidate, and no state or generated scripts commit on a rejected candidate. Retries reuse the original envelope/operation ID.

`internal_refinement` preserves existing Goals, Contracts and Outputs exactly, including revisions, and Architecture scope. Add new internal Contracts when needed; changed public semantics require `replan`, explicit contract review and consumer adaptation. Both modes compare actual execution assumptions, rebind inventory revisions and invalidate affected Tasks/consumers. Unaffected Tasks retain statuses/reviews/evidence. This is factual compatibility checking; it cannot decide that a changed contract description means the same thing.

For a split, revise the original Task into a bounded assembly/verification Task, create ordinary prerequisite Tasks, and include a `splits` entry:

```json
{
  "task_id": "TASK-READER",
  "prerequisite_task_ids": ["TASK-PARSE", "TASK-VALIDATE"],
  "coverage": [
    {"criterion": "CSV becomes typed records", "task_ids": ["TASK-PARSE", "TASK-READER"], "check_ids": ["CHECK-PUBLIC-NORMAL"], "review_method": ""},
    {"criterion": "Invalid daily weights are rejected", "task_ids": ["TASK-VALIDATE", "TASK-READER"], "check_ids": ["CHECK-PUBLIC-BOUNDARY"], "review_method": ""}
  ],
  "preserved_work": "Keep existing reader.py parsing code; inspect and reuse it, then verify each current Task revision"
}
```

This descriptor accompanies complete create/revise entity documents. `TASK-READER` keeps its ID, objective, exclusions, Stage, Architecture, acceptance criteria, existing inputs/dependencies and public Output provider. Its new execution unit must include the same verification mapping as coverage. It depends on every prerequisite. Each implementer ID and assembly check must exist. Coverage is persisted as `Task.decomposition` and in an immutable adjustment record; it remains validated after further revisions.

Prerequisites cannot consume `TASK-READER`'s future Output: input providers are hard dependencies and this would create a cycle. They use original available inputs or earlier prerequisite Outputs. If a revised external Output changes semantics, use the existing `revise_contract` flow and replan explicitly; adjustment does not transfer public Output ownership. Preserve completed implementation in the checkpoint, but obtain new evidence and acceptance for changed Task revisions. An old PASS is historical.

If assembly still contains parsing and validation implementation, it fails preparation and must be narrowed again. This repeated ordinary-Task refinement supplies the useful recursion without a unified recursive node type or recursively spawning tool executions.

## Evaluation cases and expected observations

| Case | Baseline problem / proposed adjustment | Observable pass condition |
|---|---|---|
| Simple slug | One function with normal/rejection rules | One qualified Task; validation, normalization and checks remain Steps; no unnecessary prerequisites |
| CSV weight reader: unclear design | “Implement reader” omits representation, date/symbol rules and error behavior | `needs_architecture` before execution; specify `date,symbol,weight`, date parsing, duplicate handling, daily tolerance and error contract with concrete locations |
| CSV reader: design explicit, work excessive | Parsing/schema checks and daily aggregate validation have separate handoffs and exceed one declared work session | Split parse and validate prerequisites; assembly only wires the public function and checks its original normal/boundary contract |
| Multi-file coherent change | A call signature and its only caller must change together | One bounded Task spanning both modules/files with an interaction check; independent deployment is not pretended |
| Research uncertainty | Capital source format is unknown | `needs_investigation`; bounded sample/schema decision delivery, machine checks of its minimum artifact, factual acceptance of the conclusion |
| External source unavailable | Required capital data/access missing | `blocked` names the missing source/unblocking condition; no series of arbitrary splits |
| Partial work already exists | Parser partly implemented before discovering excessive scope | Active checkpoint preserved; atomic adjustment keeps code and public provider; fresh tests validate reused work |
| Coverage loss or future-output cycle | Split drops invalid-weight rejection or prerequisite consumes assembly output | Entire operation rejected with state and generated scripts unchanged |
| Internal Module refinement | Add an internal child without changing an unrelated Task's execution facts | Unrelated passed/ready Tasks retain preparation and acceptance; affected Tasks require new review |
| Same-file sequential edits | Validation changes reader.py after parsing has passed | Rerun original parsing assertions and explicitly supersede acceptance; active later work survives a successful revalidation; failed review blocks consumers |

For the reader's normal fixture, `2026-09-16,AAA,0.6` and `2026-09-16,BBB,0.4` yield two typed records. Duplicate `(date,symbol)`, malformed dates, NaN/negative weights and a daily sum of `0.9` fail at the specified reader boundary. The original public acceptance remains with assembly. These are example domain rules, not universal requirements for CSVs.

## Does this solve the original problem?

The intended causal chain is: missing architecture detail becomes a named preparation gap; excessive work becomes a split with preserved coverage; gates stop unprepared packets; bounded prerequisites and assembly are independently reassessed; code reuse and revalidation keep refinement feasible. Existing node types alone did not enforce this chain. Adding preparation fields alone would also be insufficient.

Automated regression cases in [test_execution_units.py](../tests/test_execution_units.py) exercise the gates, atomic rollback/retry, public provider preservation, lost coverage/cycles, assembly re-review, factual drift, unchanged inventory bindings, failing business assertions and same-file revalidation. They establish protocol behavior, not a measured improvement in agent completion rates for a complex real reader project.

Compare the original and changed planner on the same coarse brief, repository, executor context and resource budget. Include the simple-task control, the coarse reader, an unknown-input task, partially completed work and a multi-file coherent change. Review generated packets blind before execution; do not compensate the baseline by supplying a detailed design only to the changed planner. Run actual implementation from the packets and retain failure diagnoses.

Measure original-requirement completion with real acceptance evidence, failures caused by unresolved design/oversized work, executor-triggered redesign/splitting, planning plus implementation cost, number of artificial handoffs, and loss of completed work. Improvement requires fewer original-cause failures and better accepted completion, without a material cost regression on simple/coherent tasks. No fixed unit duration or increased Task count is itself success. If qualified packets still require major design, tighten review evidence; if excessive splitting dominates cost, revisit granularity reasons and budgets. A significant empirical gain remains to be demonstrated by these paired executions.

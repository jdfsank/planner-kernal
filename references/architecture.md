# Architecture-first planning

## Purpose

Model the product before decomposing implementation work. An Architecture is a reviewed module tree plus a port-connection graph. A Stage describes an observable integrated capability; a Task describes an independently implemented and accepted change. These structures serve different purposes and must not be copied mechanically from one another.

## Discovery and decomposition

Inspect entry points, data flow, public interfaces, tests, shared state, and external dependencies. Mark each statement as observed, proposed, or unresolved. Existing modules cite real project-relative implementation or test files. Planned modules use proposed locations. External modules remain black boxes but still expose explicit contracts.

Recursively decompose every module inside the current goal boundary until it has one clear responsibility, stable testable ports, a locatable implementation boundary, and a credible replacement statement. Stop when further decomposition provides no concrete maintenance, reuse, or verification benefit. Do not decompose mechanically to individual functions.

Each contract records:

- carrier and format, such as CSV, DataFrame, function call, HTTP request, or event;
- structural schema, including fields, types, nullability, keys, and ordering where relevant;
- semantic rules with stable IDs, parameters, and verification methods;
- invalid-input behavior and observable side effects.

Every module input port has exactly one connection. Both ends of a connection reference the same contract. Parent modules explain their public boundary through their child ports and connections. Module containment is acyclic. A domain feedback loop is allowed only in the connection graph and must be represented explicitly.

An Architecture can be baselined only when its complete in-scope module inventory, roots, contracts, connections, evidence references, and review findings are present, with no unresolved questions. A baselined Architecture is required before any Stage or Task is accepted by the kernel.

## Alignment example: portfolio positions

The shared target is: read daily portfolio weights and capital, calculate target positions, and export a position table. Reading or calculation implementations may later be replaced without changing their consumers.

```text
Portfolio position generator
|-- Weight CSV source [external]
|-- Capital source [external]
|-- Weight reader
|-- Capital reader
|-- Position calculator
`-- Position exporter
```

The two source modules are explicit black boxes that provide the reader input ports. The Weight reader accepts UTF-8 CSV with `date,symbol,weight`. Its rules require `date` in `YYYY-MM-DD`, nonempty symbols, unique `(date, symbol)` pairs, finite nonnegative weights, and `abs(sum(weight) - 1) <= 1e-8` per date. It returns a DataFrame with the same columns and guarantees those invariants.

The Capital reader returns a DataFrame with `date,capital`; dates are unique and capital is finite and nonnegative. The Position calculator receives both DataFrames, requires capital for every weight date, and returns `date,symbol,position` where `position = weight * capital`. The exporter accepts that position DataFrame and creates a UTF-8 CSV without overwriting an existing file.

Use this acceptance fixture:

```csv
date,symbol,weight
2026-09-16,AAA,0.6
2026-09-16,BBB,0.4
```

For capital `1000` on `2026-09-16`, the expected positions are `AAA=600` and `BBB=400`. A daily weight sum of `0.9` must fail at the Weight reader boundary. Replacing a row-by-row calculator with a vectorized implementation must leave the readers and exporter unchanged and must pass the same contract and integration checks.

These nonnegative-weight, tolerance, and overwrite rules belong to this example. Do not generalize them to other projects without evidence or user intent.

## Change routing

- Internal implementation change: keep the contract revision, then rerun the module contract checks and directly connected integration checks.
- Contract change: revise the Architecture first, inspect affected modules and Tasks with `impact`, and then plan adapters or consumer changes. Do not infer semantic compatibility automatically.
- Responsibility or topology change: re-review the complete current goal boundary before creating or revising implementation work.

Use `query --type architectures|modules|contracts|connections`, `export-module --module ID`, and `impact --module ID` or `impact --contract ID` to locate and assess changes.

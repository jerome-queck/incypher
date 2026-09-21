# Shared integration interface

Read before changing Brain, scope, tools, evidence or submission behavior.
The dependency-free `agent_ext/contracts.py` defines team records, not organiser APIs.
See [current activation status](context.md) before assuming an adapter is live.

## Active boundary

```text
entrypoint.sh -> arena_main.py (trusted ranking/state/context + bounded pass shim)
  -> inherited main.py (each serial enumeration, sole official results writer)
    -> inherited solver.py (files, instances, timing)
      -> Brain(run_bash, submit_flag, max_steps).solve(prompt)
```

`run_bash(str) -> str`, `submit_flag(str) -> dict`, `solve(str) -> dict` remain the supported
call shapes. A supervised shell may additionally expose `start`, `poll`, `cancel`, `close`
and `supports_async=True`; Brain advertises those tools only for that exact capability.
`solve` must return at least `solved: bool`. Practice filtering is disabled by the shim;
explicit official selectors are preserved. The inherited files remain intact.

Only the trusted submission callback submits, at most once per assistant evidence turn.
Challenge/model text cannot grant target
authority. `arena_main.py` checks the inspected inherited call signatures, binds trusted
challenge metadata around `solve_challenge`, and enriches it from the inherited prompt
builder's prepared files/connection. Brain consumes hashes and metadata from that context;
raw connection values and candidates are not persisted there. The shim requires the exact
inspected AST and signatures for every replaced organiser seam before the harness runs.
It ranks int-compatible catalogue IDs, while inherited filters, serial challenge lifecycle,
submission and result writing remain authoritative. The optional `BrainAttempt` controller
remains unconnected.

## Optional integration flow

1. Bind a trusted `ChallengeScope` and remaining `Budget` to one admitted attempt.
2. Controller chooses a `NextAction`; bounded executor returns `ToolResult`.
3. Evidence owner records observations separately from hypotheses and qualifies `Candidate`.
4. Durably reserve a unique intent and mark dispatch possible before the trusted callback.
5. Classify the exact response as `SubmissionResult`; reconcile uncertainty before any resend.
6. Return a projection to inherited solver/main; keep one official `/work/results.json` writer.

| Concern | Reference |
| --- | --- |
| Scheduling, attempt ownership, adapter callbacks, retries | [strategy.md](strategy.md) |
| Model requests, capability gating and durable cost admission | [model-gateway.md](model-gateway.md) |
| Exact provider discovery and deterministic category guidance | [provider-discovery.md](provider-discovery.md) |
| Bounded fixed inspections, resource leases, cancellation | [tooling.md](tooling.md) |
| Evidence scope, qualification, durable intents, projection | [evidence-policy.md](evidence-policy.md) |
| Inspected organiser behavior and result shapes | [arena-contract.md](arena-contract.md) |

Current Brain stops on unknown/malformed/rate-limit/error submission verdicts and avoids
duplicate candidates within one solve. `correct` is acceptance; `already_solved` retains
the harness's terminal success convention without proving this candidate was accepted.
The normal loop has durable model-cost reservation/settlement and a separate bounded
runtime-state database for challenge outcomes, finite ranking backoff, scoped command
fingerprints and typed safe findings. Accepted model turns and new tool observations
checkpoint scheduler progress before final/crash classification. Before callback dispatch,
the active shell durably stores only a scope-keyed candidate identity, then commits a
separate dispatch-possible marker. Uncertain effects block that exact material/instance
scope until trusted catalogue reconciliation; other work continues.

## Limits and change coordination

Model calls default to 120 seconds and are also bounded by the trusted eight-minute
attempt deadline. The compatible managed shell retains `/bin/bash -lc` but streams both
outputs to a 12 KB cap, uses 45-second ordinary/90-second heavy bounds within the attempt
deadline, and reaps process groups. Brain step, tool, submission and USD admission limits
are finite. The inherited `MAX_STEPS` value is the strictly validated per-slice model-call
cap; trusted point metadata does not silently replace it. Coordinator limits and
continuation rules are authoritative in [strategy.md](strategy.md). The gateway returns on its
deadline and blocks overlapping dispatch while an unresolved transport worker remains;
Python cannot forcibly cancel that worker. Shell work may overlap through at most two
attempt-scoped handles; model conversations and inherited challenge lifecycles remain serial.
The wrapper can rerun the exact inherited main serially within those bounds. Every pass
retains inherited filtering, lifecycle, submission and results ownership.

A malformed tool request is rejected before dispatch. The optional bridge can classify
that rejection through `Brain._invalid_tool_arguments`; preserve that hook when changing
the parser. Model/tool callbacks may also carry the bridge's private control-flow
exceptions; broad catch-and-continue changes must retain admitted-attempt semantics.

Coordinate shared seam edits with affected team work: Jerome/integration, Elson/strategy,
Aidan/tools, Richard/evidence. Ownership is collaboration context, not a veto over the
current user's authorized work. Update producer, consumer, docs and meaningful regression
coverage together. Do not activate an entire subsystem merely because its files import.

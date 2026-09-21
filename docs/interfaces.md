# Shared integration interface

Read before changing Brain, scope, tools, evidence or submission behavior.
The dependency-free `agent_ext/contracts.py` defines team records, not organiser APIs.
See [current activation status](context.md) before assuming an adapter is live.

## Active boundary

```text
entrypoint.sh -> arena_main.py (selection + trusted-context shim)
  -> inherited main.py (enumeration, sole official results writer)
    -> inherited solver.py (files, instances, timing)
      -> Brain(run_bash, submit_flag, max_steps).solve(prompt)
```

`run_bash(str) -> str`, `submit_flag(str) -> dict`, `solve(str) -> dict` are the supported
call shapes. `solve` must return at least `solved: bool`. Practice filtering is disabled
by the shim; explicit official selectors are preserved. The inherited files remain intact.

Only the trusted submission callback submits. Challenge/model text cannot grant target
authority. `arena_main.py` checks the inspected inherited call signatures, binds trusted
challenge metadata around `solve_challenge`, and enriches it from the inherited prompt
builder's prepared files/connection. Brain consumes hashes and metadata from that context;
raw connection values and candidates are not persisted there. Signature drift stops before
the harness runs. The optional `BrainAttempt` controller remains unconnected.

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
The normal loop has a durable model-cost reservation/settlement ledger, but no durable
candidate reconciliation or restart-safe challenge progress; optional helpers cover
parts of those separate concerns.

## Limits and change coordination

Model calls default to 120 seconds and are also bounded by the trusted eight-minute
attempt deadline; inherited shell calls retain their recorded 120-second timeout. Brain
step, tool, submission and USD admission limits are finite. The gateway returns on its
deadline and blocks overlapping dispatch while an unresolved transport worker remains;
Python cannot forcibly cancel that worker. Shell callbacks remain synchronous.

A malformed tool request is rejected before dispatch. The optional bridge can classify
that rejection through `Brain._invalid_tool_arguments`; preserve that hook when changing
the parser. Model/tool callbacks may also carry the bridge's private control-flow
exceptions; broad catch-and-continue changes must retain admitted-attempt semantics.

Coordinate shared seam edits with affected team work: Jerome/integration, Elson/strategy,
Aidan/tools, Richard/evidence. Ownership is collaboration context, not a veto over the
current user's authorized work. Update producer, consumer, docs and meaningful regression
coverage together. Do not activate an entire subsystem merely because its files import.

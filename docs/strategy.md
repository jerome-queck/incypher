# Strategy and controller

Read for scheduling, retries or `BrainAttempt` integration. Merged through PR #2;
**not connected to the normal Brain**. Activation and readiness are tracked only in
[context.md](context.md). Elson owns strategy; shared seams are described in
[interfaces.md](interfaces.md).

## Decision ownership

`Controller` chooses actions but performs no model, HTTP, tool, sleep or result I/O.
It uses one lock and admits at most one active attempt per controller. This local
serialization is not a team-wide dynamic-instance lease or cross-process ownership.

`update_catalogue` takes trusted metadata; `next_action` returns ATTEMPT/WAIT/STOP;
`claim_attempt` prevents duplicate dispatch; `finish_attempt` accounts for measured
calls and evidence. `cancel` latches shutdown. Executor/owners perform cleanup and
checkpointing. `snapshot` is bounded private state, not durable restart machinery.
Read the callable definitions in `agent_ext/controller.py` rather than copying a
second API catalogue into this doc.

Scope includes challenge, material revision and optional instance generation. New
material/generation invalidates evidence; old uncertain effects remain unresolved.
Old active work must finish cleanup before new ownership. Keep one monotonic clock;
reversed/nonfinite time is rejected. Recreating a controller is not budget renewal.

## Progress and selection

Continuation requires confirmed, same-scope observations or meaningful tests. Model
confidence, reworded hypotheses and repeated evidence do not create progress. New
approaches need a distinct justified experiment and retain prior failure/budget history.

All policies filter ineligible/blocked/exhausted/uncertain work. Aging prevents starvation;
otherwise untried work precedes continuation. COVERAGE uses deterministic scope ordering;
PROGRESS then favors evidence progress and known setup cost; BENEFIT_COST uses points
per known setup-plus-remaining time, not invented solve probability. Missing estimates
stay missing. Controller limits are synthetic defaults, not measured arena policy.

For production tuning, compare the same authorized tasks, model and budget. Record
accepted points, time, calls, repeat work and spend. The historical 12-task fixture
proved finite coverage/termination; it did not show a winning scheduling heuristic.

## Retry semantics

`retry_policy.py` is the single decision policy; it never executes the operation.
Documented transient model/read failures have finite backoff and honor retry guidance.
One layer owns retries. Auth/config blocks until a changed sanitized revision; tool
failure requires a changed experiment; stale instance requires requalification.
Submission uncertainty requires reconciliation; instance mutation requires the lifecycle
owner. Neither action is blindly replayed. Waits respect cancellation and drain tasks.

## Shared Brain adapter

`BrainAttempt` consumes one already-admitted attempt and calls the real Brain once.
It binds trusted `ChallengeScope`, remaining `Budget` and production `StrategyOwners`.
It guards model/tool allowances and captures a candidate before any submission.
Both assistant-text flags and submit-tool flags take the same qualification path.
Only one candidate handoff occurs per attempt; another experiment is needed after
rejection. Ordinary Brain retains its bounded multiple-candidate behavior.

Required owner callbacks are `observe`, `qualify`, `reserve_intent`, `record_submission`,
`checkpoint`, `release`. The bridge does not implement evidence storage, durable ledger
or process cleanup. Confirmed evidence must come from a real owner, not a permissive fake.

```text
qualified scope/budget -> admitted model/tool work -> candidate capture
  -> qualification -> durable intent/checkpoint -> trusted callback once
  -> classified outcome -> release -> checkpoint -> inherited result projection
```

Uncertain/missing/malformed callback responses remain unresolved. Account-level
`already_solved` is terminal but is not fresh acceptance. Persist intent before dispatch;
failed checkpoints prevent dispatch. Cancellation/interrupt after a possible effect
preserves uncertainty. Cleanup failure does not erase a definitive outcome.

Deadlines are cooperative around synchronous callbacks; a 30-second budget cannot
force-stop a 180-second HTTP request. Production hard limits need cancellable/bounded
callbacks and a tested cleanup path. Broad multi-challenge ranking needs an authorized
selection seam, not a second uncontrolled loop around inherited main.

## Verification and integration gate

The shared offline suite exercises deterministic scheduling, aging, lifecycle ownership,
changed scope, finite retry, interrupted work, duplicate evidence and unknown submissions.
`tests/test_strategy_bridge.py` uses real Brain flow with synthetic model/owner callbacks;
it forbids external socket creation. It is not a live provider/platform test.

Before activation, wire trusted scope and real tool/evidence/ledger owners; prove both
success and failure/interrupt lifecycles; measure the exact image's resource/deadline
behavior; retain the inherited writer. Removing an unused adapter is a source rollback;
after activation, disable its wiring and restore an identified image digest separately.

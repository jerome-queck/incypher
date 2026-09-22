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
callbacks and a tested cleanup path. The active wrapper uses the exact guarded inherited
main as its authorized selection seam. Each inherited pass admits one strictly bounded
`MAX_STEPS` dynamic slice and, when eligible static work exists, one concurrent static
slice on a separate client. It defers every other unstarted challenge, then reranks
after a two-second cooldown. The inherited main still receives both results and is the
sole results writer; the worker never owns a dynamic instance. The wrapper refreshes
the inherited trusted catalogue at most every five minutes; intervening passes rerank a
defensive cached copy, and accepted solves update only that cache until the next refresh.
Temporary catalogue read failures retain the prior trusted snapshot for one full cadence;
initial or malformed reads fail closed. Submission intent is durably keyed to exact
material/instance scope, then marked dispatch-possible immediately before callback dispatch.
An uncertain callback defers only that scope until a trusted catalogue refresh
shows it solved or, after five minutes, still unsolved; no uncertain candidate is blindly
replayed. Attributable accepted/rejected outcomes remain durable and idempotent across
the outer outcome checkpoint; accepted, independently persisted account-level
already-solved and conflicting outcomes block every replacement scope until the catalogue
confirms it solved. Contradictory definitive replay becomes conflict. At the
same cadence, a bounded three-second public
read of the official score page extracts only its recent-event JSON and overlays exact-name
solve counts as a weak queue hint. At most two local retries gain crowd priority over
untried work; subsequent misses restore the ordinary attempt-order preference, and
backoff/eligibility always take precedence. Missing, malformed, oversized or unavailable public data
contributes no hint and never blocks the trusted catalogue. It does not contact challenge
targets. There is no separate cumulative
slice or call-count cutoff: durable model-dollar admission and a 24-hour process safety
bound govern the run. The separate 6.5-hour pacing window is a soft spend target toward
the competition horizon, not the process lifetime or dollar ceiling. A normal empty
or all-solved catalogue/queue polls again after 30 seconds and refreshes the trusted
catalogue at most every five minutes, so newly opened challenges become eligible
without a push. An explicit selector exits when empty or solved. Hard
model-dollar exhaustion, an inherited nonzero return, the process deadline, or an unresolved
gateway transport worker is terminal. Other provider, submission, crash and malformed-response
outcomes affect durable ranking without killing the outer queue. The inherited main remains
the sole lifecycle, submission and results owner.

The active scored queue selects unsolved 500-point challenges with locally
corroborated exploit paths first, across both kinds. Within the remaining
tiers it selects due proven static revisit, fresh proven static, due proven
dynamic revisit, fresh proven dynamic, unknown fresh static, unknown fresh
dynamic, then ordinary retries. Higher trusted point values lead within each
tier. One failed proven method gets an early full-budget revisit after three
other completed challenges; a second miss removes this priority. This avoids
burying a locally verified exploit behind the whole catalogue while still giving
fresh challenges a first attempt. First looks have 12 model turns (16 with local proof);
revisits retain the packaged 24-turn cap. Explicit selectors keep their configured
cap. Solved state and eligibility/backoff still gate dispatch. A static worker
may overlap one live dynamic instance; no second dynamic worker is admitted.
After the selected slice, deferred and solved challenges use already-read trusted
catalogue metadata, avoiding full-detail requests for work not dispatched.

## Verification and integration gate

The shared offline suite exercises deterministic scheduling, aging, lifecycle ownership,
changed scope, finite retry, interrupted work, duplicate evidence and unknown submissions.
`tests/test_strategy_bridge.py` uses real Brain flow with synthetic model/owner callbacks;
it forbids external socket creation. It is not a live provider/platform test.

Before activation, wire trusted scope and real tool/evidence/ledger owners; prove both
success and failure/interrupt lifecycles; measure the exact image's resource/deadline
behavior; retain the inherited writer. Removing an unused adapter is a source rollback;
after activation, disable its wiring and restore an identified image digest separately.

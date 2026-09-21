# Elson's strategy and controller

## Delivery status and scope

This change implements Elson's policy modules and a shared-contract execution adapter:
deterministic scheduling, bounded serial attempt decisions, evidence-aware
continuation, retry classification, owner handoffs, and one admitted attempt through
the actual merged `Brain.solve` loop. It reuses the existing model implementation
and authorized callbacks and introduces no third-party dependency or outer loop.

**The real-Brain adapter is tested offline; live activation and owner implementations
remain integration work.** The first policy commit was based on
`7fb4159857f1de56e79b4462ef05ea83b47eda1a`. This revision incorporates merged
foundation `ebddc8daa346248226450de629f72cfb4ffa8f9c` into the feature branch.
The changed paths relative to that foundation are:

- `agent_ext/controller.py`
- `agent_ext/scheduler.py`
- `agent_ext/retry_policy.py`
- `agent_ext/strategy_bridge.py`
- `tests/test_controller.py`
- `tests/test_scheduler.py`
- `tests/test_retry_policy.py`
- `tests/test_strategy_bridge.py`
- `docs/strategy.md`

Jerome's foundation [PR #1](https://github.com/jerome-queck/incypher/pull/1) is merged.
The reviewed foundation merge is `ebddc8daa346248226450de629f72cfb4ffa8f9c`.
Its `docs/interfaces.md`, `docs/arena-contract.md`, semantic records, adapters,
and `brain.py` were inspected. Its documentation identifies the extension as
`Brain(run_bash, submit_flag, max_steps).solve(prompt)`, handling **one challenge**.
Inherited `main.py` owns challenge enumeration, `solver.py` owns materials and
instances, and the inherited harness owns official results output.

Consequently the multi-challenge scheduler below is an **offline policy experiment**
until Jerome identifies an authorized selection seam. It must not drive another
challenge loop around the inherited harness. The controller can be evaluated with
one qualified challenge through `BrainAttempt.run`. Its tests use the merged Brain
and shared records with synthetic evidence/ledger callbacks. Normal `Brain(...)`
construction does not automatically select this adapter. Jerome must bind a trusted
structured scope, remaining budget and production owner callbacks before activation.

The merged Dockerfile already copies `agent_ext/`, so a future build can include
these sources without another packaging edit. This PR changes no shared contracts,
`brain.py`, Dockerfile, entrypoint or owner files. Docker is unavailable on this
workstation/WSL environment, so no new image smoke test or structural checker was
run. The captain's reported image/arena evidence applies to his foundation, not
automatically to these changes. No live evaluation or registry submission occurred.

## Your job scope: Elson

Elson owns **which eligible action to try next, why, for how long, and when to
continue, change approach, defer, or stop**. Review policy choices, preserve
failure/evidence history, and compare alternatives under the same measured
conditions. The initial serial solver is an experiment, not an organizer limit.

| Owner | Responsibility at the boundary |
| --- | --- |
| Elson | Selection, attempt eligibility, progress policy, retry/defer decisions, finite budgets, reasons, and synthetic measurements. |
| Jerome | Inspected arena contract, shared records, actual Brain integration, authorized callbacks, catalogue/scope qualification, packaging, CI, release. |
| Aidan | Allowlisted tool execution, real cost measurement, resource admission, timeouts, cancellation and child-process cleanup. |
| Richard | Confirmed scoped evidence, candidate qualification, negative evidence, submission intent ledger, reconciliation, acceptance semantics, checkpoint/result projection. |

Elson must not independently edit `brain.py`, `agent_ext/contracts.py`, shared
adapters, image configuration, or Richard's acceptance rules. Review/merge and
captain-controlled live evaluation remain separate team decisions.

## Decision model

`Controller` is a stateful helper called by the **existing** harness. It does not
execute a solver, sleep, refresh a catalogue, submit, or write a file itself.
Its mutable methods use one lock. At most one active attempt token exists per
controller instance; concurrent callers cannot acquire duplicate ownership.

The supported calls are:

| Call | Input responsibility and result |
| --- | --- |
| `update_catalogue(challenges, now=...)` | Jerome supplies qualified, sanitized metadata. Bounded upsert; omission does not remove a task. A new material/instance identity retires prior continuation evidence. |
| `next_action(now=...)` | Returns `ATTEMPT`, `WAIT`, or `STOP`, always with a reason. An attempt contains scope, authority reference, approach, token, deadline and separate request/tool allowances. |
| `claim_attempt(attempt)` | Atomically reserves execution of that exact admitted object. `BrainAttempt` calls it so two adapters cannot execute one lease. Completion releases the execution claim. |
| `finish_attempt(token, report, now=...)` | The owning executor reports actual resource counts, confirmed evidence references, a candidate reference, or a classified failure. A mismatched/duplicate token cannot release another attempt. |
| `propose_approach(scope, approach_ref, justification_ref)` | A trusted owner may revive stalled work with a distinct, justified experiment. Old attempts, retry counts and failures remain. Justification references are retained. |
| `observe_evidence(scope, evidence)` | Richard may supply newly confirmed evidence to revive `no_new_evidence` work within its remaining continuation allowance. |
| `update_configuration(subsystem, revision)` | Only a changed, sanitized configuration revision unblocks an unchanged-configuration failure. Never pass credentials as the revision. |
| `requalified(scope, revision=...)` | Jerome confirms a changed prerequisite for a stale read. Actual material/instance changes require a new scoped catalogue identity. |
| `resolve_candidate(scope, fingerprint, outcome)` | Richard/Jerome supplies an owner verdict for the exact pending candidate. The controller never infers acceptance. |
| `reconciled_effect(scope, resolution_ref=...)` | The owner establishes a resolution for an uncertain effect without a candidate. This defers work; it does not replay the effect. |
| `cancel()` | Latches admission shutdown. Cleanup is performed by the executor after consuming the next decision. |
| `snapshot()` | Returns bounded private checkpoint input and counters for Richard. It is neither the organizer result schema nor a durable restart implementation. |

Use a single monotonic clock for `started_at` and every `now`. Reversed or
nonfinite times are rejected. Do not reset this controller to replenish exhausted
budgets. Cross-process ownership, crash recovery, and restored ledger state remain
owner responsibilities; the in-memory lock and token alone do not provide them.

### Scope and evidence

`Scope` identifies challenge, material revision and optional instance generation.
Replacing either material or generation creates fresh decision/evidence state.
An old active attempt must finish cleanup before another is admitted. Old pending
candidates and uncertain effects are retained and block new work for that same
challenge until the owner resolves them. Unrelated eligible challenges can proceed.

Progress requires Richard-confirmed, same-scope evidence of a successful
observation, discriminating test, or verified reduction in uncertainty. Evidence
uses canonical SHA-256 references. The owner must derive stable content identities;
hashing a newly worded model explanation does not establish a new observation.
Unconfirmed, cross-scope and duplicate fingerprints earn no continuation.

Only compact references enter the controller. Raw candidate values, tool output,
model messages, credentials, URLs and command authority remain with their owners.
The reference format validates size and shape; it cannot prove that a caller has
sanitized a value or correctly established evidence. These are trusted Python
interfaces, not structures to deserialize directly from model output.

Every changed approach must describe a genuinely different authorized experiment
through its owner-verified reference. Merely changing its label is not sufficient.
Changing approach resets only that approach's continuation allowance, not earlier
failures, transient retry count, repair count, or scope/session attempt caps.

### Selection policy

All policies filter ineligible, blocked, exhausted and uncertain work before ranking.
Only eligible tasks accrue bypass age. A task bypassed at least three times enters
the priority group, ordered by greatest age, preventing fresh arrivals from
permanently starving an eligible continuation. Otherwise untried tasks precede
ordinary continuations, giving broad initial coverage.

| Configurable policy | Ordering within age/coverage safeguards |
| --- | --- |
| `COVERAGE` | Stable scope order, providing a simple comparison baseline. |
| `PROGRESS` (default) | Most recent confirmed progress revision, then known/lower setup cost, then stable scope order. |
| `BENEFIT_COST` | Known `points / (setup_seconds + remaining_seconds)`, then progress, setup and stable scope order. |

Benefit/cost activates only for a task with all three supplied measurements.
Tasks with incomplete values fall back to progress/setup/stable ordering after
fully measured tasks, subject to age and coverage. No points, cost, category
difficulty or calibrated solve probability are invented. An unknown category is
valid. Past expenditure is not a priority bonus. The optional ratio is a points/cost
proxy, not an expected-score claim; a calibrated probability model is not implemented.

## Retry decisions

`retry_decision` is pure classification. It never invokes a transport or tool.
The trusted adapters must classify the operation as well as its failure. An HTTP
status or a generic `ToolResult.error` alone is not proof that a side effect did
not happen.

| Condition | Controller policy |
| --- | --- |
| Authentication/configuration on a read/model/tool route | Block that subsystem until its configuration revision changes. Unrelated tasks remain eligible. |
| Documented transient read or model rate limit | At most two retries per scope by default. Exponential delay starts at 1 second; its local component caps at 8 seconds. Honor a longer actual `retry_after` in full. Defer if the delay would consume the remaining session budget. |
| Adapter already owns retries | Defer instead of nesting another retry layer. |
| Malformed request | One repair under the same authority by default; further failure needs a different justified experiment. A malformed response is not automatically a malformed request. |
| Tool timeout/OOM | Defer for a different experiment. Aidan's measured costs should inform a reduced workload or alternate test. No repeated identical expensive command is scheduled. |
| Stale instance on a nonmutating read | Request requalification; changed material/generation must not reuse old live evidence. |
| Wrong candidate | Richard records scoped negative evidence; `resolve_candidate(..., WRONG)` remembers the candidate fingerprint and prevents another handoff of it in that scope. |
| Submission acknowledgement lost, rate limit, malformed result or transport failure | Preserve unresolved state and ask the owner to reconcile. No generic resend. |
| Failed/uncertain instance mutation | Require owner requalification/reconciliation and preserve uncertainty. No generic mutation retry or repair. |
| No progress | Defer until a justified changed approach or new confirmed evidence, within finite allowances. |
| Provider safety refusal | Stop the refused route. Neither changed-approach nor fresh-evidence calls revive it. |
| Unclassified failure | Defer; do not infer transience. |

Mutation handling takes precedence over ordinary retry categories. Definitively
classified wrong candidates and provider refusals have their own terminal/defer
routes; real candidate verdicts must use the matching candidate handoff and
Richard's ledger, not a generic failure record with no candidate identity.

`wait_for_retry(delay_seconds, cancellation=event, remaining_seconds=...)` is an
optional asyncio wait helper. It returns ready/cancelled/deadline, honors
preexisting and in-flight cancellation, propagates caller-task cancellation, and
drains both child tasks. A harness that already waits should use its existing
mechanism, not introduce another event loop. Neither helper retries an operation.

## Candidate and uncertainty handling

A candidate fingerprint produces `QUALIFY_CANDIDATE` and `AWAITING_CANDIDATE`.
Richard must qualify the evidence, enforce real submission limits, reserve and
persist an intent, and have Jerome's **existing authorized callback** perform any
submission. No candidate value is stored or submitted here.

- `ACCEPTED` and `WRONG` are supplied definitive owner outcomes; both settle the
  fingerprint. Accepted work becomes terminal; wrong work needs a changed approach.
- `QUALIFICATION_REJECTED` may reject an unsubmitted handoff. It **cannot clear**
  an already ambiguous submission.
- `AMBIGUOUS` preserves the pending candidate and requests reconciliation.
- `NOT_DELIVERED` requires definitive owner evidence of non-delivery. It clears
  uncertainty and defers; it never automatically resends.
- `ALREADY_SOLVED` preserves the pending owner decision and does not manufacture
  current-attempt acceptance. The inherited projection/termination decision must
  be reconciled with Richard and Jerome's shared semantics.

Cancellation, exhaustion and a generation change do not erase unresolved intents.
The owner may record a late definitive result after cancellation, but admission
remains stopped. A candidate returned only after stopping is retained for
checkpointing without triggering qualification or submission.

## Bounds and stopping

These are configurable **synthetic experiment defaults**, not arena rules,
organizer deadlines, proven optimal values or inherited Rapido settings.

| Setting | Default |
| --- | --- |
| Controller session budget / one attempt | 300 seconds / 30 seconds |
| Unknown/no-work grace / catalogue poll interval | 30 seconds / 5 seconds |
| Attempts per scoped challenge / total admitted attempts | 4 / 100 |
| Same-approach continuations / bypass threshold | 1 / 3 |
| Model requests per attempt / total reported requests | 2 / 20 |
| Tool calls per attempt / total reported calls | 4 / 40 |
| Retained scopes, including retired history | 256 |
| Transient retries / same-authority repairs per scope | 2 / 1 |

An attempt receives the minimum of configured and remaining time/resource budgets.
Model and tool counts are independent: exhausting model allowance need not disable
scripted work. Qualified `requires` references determine dependencies, including
`model` and `tools`. Zero per-attempt allowance makes work requiring that resource
ineligible. Adapters must enforce the limits **before** each call and report use
even on failure; post-hoc reporting cannot prevent a runaway tool or model call.

The current foundation documents 120-second inherited tool timeouts and
180-second model HTTP timeouts. Those exceed this experiment's 30-second attempt
default. No hard runtime deadline guarantee exists until Jerome/Aidan enforce
the remaining attempt budget inside the real callbacks or agree revised defaults.

No eligible work produces a positive `wake_at` plus a catalogue-refresh request.
The caller waits until that deadline or an owner event; it must not busy-poll.
Empty, blocked and exhausted catalogues terminate after bounded grace. An actual
future safe retry within the session budget extends waiting past ordinary idle
grace. Repeating an unchanged catalogue does not extend idle forever.

On cancellation/session exhaustion, `STOP` requests checkpointing and resource
release and identifies any active token to cancel. Scope changes and per-attempt
expiry request cleanup before admitting another attempt. A cleanup report is
still required to release the active token. Cleanup itself belongs to the executor;
this module neither kills processes nor guarantees the external owner responds.
Release/checkpoint handlers must be idempotent because repeated STOP queries
repeat these requests. After draining an active owner and flushing, the existing
harness exits according to its contract; no permanent idle process is created.

State is bounded by retained scopes, per-scope attempts/approaches and at most 32
evidence references per report. Fingerprint history is capped at
`32 * max_attempts_per_scope` per scope. Compact failure and settled-candidate
history follows attempt limits. Scope replacement never silently discards old
uncertainty. Capacity errors require owner handling/checkpointing, not a fresh
controller that silently forgets the ledger or resets quotas. Eligibility scanning
is at worst quadratic in the bounded scope count; no extra workers/processes are
created by runtime modules. No container CPU/memory measurement is claimed.

`snapshot()` includes decision and attempt counts, unique attempted scopes,
reported resource counts, continuation/retry/repair counts, reasons, pending
candidate references, progress fingerprints and compact failure/approach history.
It contains Python scope objects and requires Richard's deliberate projection.
It is not directly written to `/work/results.json`, and it is not a complete
restore format. Persistence and crash-safe resumption remain integration work.

## Offline validation and measurements

From the repository root, the standard-library command is:

```sh
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Use `python` on Windows. The combined suite has **125 tests**: 47 controller/lifecycle,
17 retry, 12 scheduler, 31 real-Brain adapter, and 18 foundation tests.
They passed on Windows Python 3.13.6 and Ubuntu Python 3.12.3, with zero failures
or skips. Controller, lifecycle and real-Brain adapter fixtures forbid
socket creation. The suite uses only synthetic metadata/candidates, injected time,
in-memory owners, and short cancellable timers; no model, Board or credential is
used. The inherited image's Python version and execution of these tests inside it
remain for the integration owner to verify.

| Required behavior | Representative test(s) |
| --- | --- |
| Empty, missing metadata, deterministic ties, blocked work | `test_empty_or_all_blocked`, `test_missing_category_points_and_costs_have_stable_fallback`, `test_empty_catalogue_waits_for_updates_then_stops_with_checkpoint` |
| Coverage and eventual age priority | `test_broad_initial_coverage_before_continuation`, `test_aged_work_is_served_despite_a_stream_of_fresh_tasks` |
| Failure isolation | `test_one_failed_task_does_not_stop_unrelated_work`, `test_configuration_failure_blocks_only_dependent_work_until_revision_changes` |
| Duplicate evidence is not infinite progress | `test_identical_observations_never_earn_unlimited_continuations`, `test_even_distinct_successful_observations_have_a_continuation_cap` |
| Changed approach/new evidence preserves history | `test_justified_changed_approach_preserves_attempts_and_failure_history`, `test_new_evidence_can_reenable_stalled_work_without_erasing_history` |
| Finite rate limit, cancellation and deadlines | `test_rate_limit_wait_allows_other_work_and_uses_finite_retry_allowance`, `test_cancellation_during_wait_drains_children`, `test_deadline_during_wait_is_not_a_retry` |
| No generic side-effect retry | `test_submission_and_instance_mutations_never_use_generic_retry`, `test_mutation_failures_cannot_requeue_via_changed_approach` |
| Material/instance invalidation | `test_material_and_instance_changes_invalidate_old_evidence`, `test_scope_replacement_cancels_old_owner_before_admitting_new_attempt` |
| Deferred work waits and eventually stops | `test_known_future_retry_is_not_cut_off_by_idle_grace`, `test_repeated_unchanged_catalogue_does_not_extend_idle_forever` |
| Single owner and stale completion protection | `test_one_active_owner_even_with_concurrent_callers`, `test_stale_or_duplicate_completion_cannot_release_another_lease` |
| Ambiguous intent survives wrong transition/poll/stop | `test_qualification_rejection_cannot_clear_ambiguous_submission`, `test_fake_ambiguous_submission_is_not_replayed_across_polls_or_stop` |
| Merged Brain and shared records execute one qualified submission | `test_real_brain_loop_uses_shared_owners_before_single_submission`, `test_plain_text_candidate_goes_through_same_gate` |
| Unknown callback verdict does not permit another candidate | `test_unknown_or_uncertain_verdict_never_sends_second_candidate`, `test_transport_exception_preserves_intent_and_sanitizes_error` |
| Actual Brain model/tool dispatch obeys separate allowances | `test_shared_step_budget_caps_real_brain_model_calls`, `test_tool_budget_is_independent_of_number_of_calls_in_one_model_turn` |
| Interrupt after a possible effect remains unresolved | `test_interrupt_during_submission_preserves_uncertainty_before_propagating`, `test_interrupt_during_model_releases_attempt_and_flushes_before_propagating` |

`FakeOwners` in `tests/test_controller.py` consumes decisions through fake
executor, qualifier, intent reservation, submitter and checkpoint methods.
The accepted fixture exercises this actual call trace:

```text
bounded attempt -> qualify -> reserve intent -> checkpoint intent
  -> submit once -> record owner outcome -> checkpoint outcome
  -> no-work grace -> release resources -> flush projection
```

A separate ambiguous fixture verifies that repeated polls and final shutdown do
not cause a second submission and retain the uncertain intent. Its in-memory
checkpoints are test doubles, not durability or Richard-interface proof.

The 12-task synthetic comparison gives the same result for each policy:

| Policy | Unique scopes attempted | Attempts | Repeated attempts | Decisions (including WAIT/STOP) | Retries | Termination |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Coverage | 12 | 12 | 0 | 14 | 0 | STOP after 1-second fixture grace |
| Progress | 12 | 12 | 0 | 14 | 0 | STOP after 1-second fixture grace |
| Benefit/cost | 12 | 12 | 0 | 14 | 0 | STOP after 1-second fixture grace |

This fixture has no point/cost estimates and every attempt stalls, so it measures
stable coverage and finite termination, not the superiority of a heuristic.
Ranking, known-cost and aging cases are exercised separately. No fixture result
counts as an accepted competition result. Later evaluation should vary one policy
at a time under identical authorized tasks, model settings and budgets and record
accepted outcomes alongside measured elapsed time, calls, repeated work and costs.

Optional development checks (Ruff is not a runtime dependency):

```sh
ruff check --isolated --select E,F,I,B,UP --ignore E501 agent_ext/controller.py agent_ext/scheduler.py agent_ext/retry_policy.py agent_ext/strategy_bridge.py tests/test_controller.py tests/test_scheduler.py tests/test_retry_policy.py tests/test_strategy_bridge.py
ruff format --isolated --check agent_ext/controller.py agent_ext/scheduler.py agent_ext/retry_policy.py agent_ext/strategy_bridge.py tests/test_controller.py tests/test_scheduler.py tests/test_retry_policy.py tests/test_strategy_bridge.py
git diff --check
```

## Implemented mapping to the merged foundation

`strategy_bridge.py` imports the real `contracts.py`. The controller retains
private policy state; conversion functions keep the shared boundary explicit.

| Merged foundation record | Implemented mapping |
| --- | --- |
| `ChallengeScope` | `challenge_from_shared` validates the integer ID and parent attempt reference, hashes material/instance references into bounded private identities, and retains the full shared record for owner calls. Parent attempt changes do not invent new material. Display name/category are not authority or ranking measurements. A trusted authority reference is supplied separately. |
| `Budget` | `BrainAttempt` caps Brain model steps by both shared steps and the admitted model allowance, checks the earliest shared/attempt/controller deadline, and blocks submission when shared allowance is zero. Tool dispatch has its separate admitted counter. |
| `NextAction` | `action_from_decision` projects decision kind, arguments, reason and separate allowances. Owner observation callbacks also receive `NextAction("run_bash", ...)` for each admitted tool call. |
| `ToolResult` | The owner supplies a bounded excerpt, measured/classified result, and a separate tuple of confirmed evidence. No successful exit, output string or provenance reference alone is promoted to progress. |
| `Candidate` | The adapter captures a candidate from either Brain text or tool output, attaches confirmed evidence references, and hands this actual shared type to the owner. Controller state receives only its fingerprint. |
| `SubmissionResult` | A reserved intent is mapped to the exact callback verdict. Missing, unknown, malformed, rate-limited and transport-error verdicts remain uncertain. Correct/incorrect map to definitive outcomes. `already_solved` retains the current harness return convention while the controller does not record fresh acceptance. |

`failure_from_tool` maps shared timeout/authentication/configuration/rate-limit
categories conservatively. The shared record has no configuration revision, so
an authentication/configuration failure blocks the explicit `unreported` revision
until the owner supplies a changed one. `MALFORMED_RESPONSE` is not assumed to be
a repairable request, and `RESOURCE_LIMIT` is not assumed to mean OOM. Model
exception classification can be injected by its trusted owner. By default,
the foundation's `ConfigurationError` and HTTP 401/403 block the model subsystem's
unreported revision; other unknown failures defer. A supplied documented rate limit uses the controller's existing
retry schedule. The adapter does not sleep, retry HTTP internally or start a loop.

## Real-Brain execution adapter and activation

`BrainAttempt` consumes one **already admitted** attempt and calls a subclass of
the merged Brain exactly once. The subclass only adds admission checks around
the existing model call; tool/candidate handling uses the existing constructor
callbacks. `brain.py` itself and the shared records remain unchanged.

The candidate callback raises a private control-flow exception before doing any
network operation, returning execution to the controller. The controller records
the handoff, Richard qualifies it, the owner reserves/checkpoints an intent, and
only then is the supplied authorized submission callback invoked. There is at
most one candidate handoff/submission per admitted attempt. A wrong result requires
a new justified experiment; a second candidate in the same model message is not
sent. This is a deliberate conservative baseline, within the shared submission
budget, rather than reproducing Brain's up-to-three submissions inside one solve.

The complete offline trace uses real Brain control flow with fake model/owner
callbacks:

```text
shared qualified scope + shared remaining budget -> admitted attempt
  -> Brain model turn -> admitted command -> shared ToolResult + confirmed evidence
  -> Brain model turn -> capture Candidate -> controller candidate handoff
  -> owner qualification -> reserve intent -> checkpoint intent
  -> authorized callback once -> shared SubmissionResult -> controller outcome
  -> close model session -> release resources -> checkpoint/projection
```

The evidence/ledger callbacks are described by the Elson-side `StrategyOwners`
protocol. `observe`, `qualify`, `reserve_intent`, `record_submission`, `checkpoint`
and `release` are mandatory; there is no permissive production fake. Test doubles
are in `tests/test_strategy_bridge.py`. The adapter does not implement Richard's
qualification or durable ledger and does not implement Aidan's process cleanup.

An integration owner can execute an admitted decision as follows; the named
inputs must come from the trusted harness, not parsed model/challenge prose:

```python
from agent_ext.strategy_bridge import BrainAttempt

# controller has already qualified the shared scope and admitted decision.attempt.
projection = BrainAttempt(
    controller, decision.attempt, shared_scope, shared_remaining_budget, owners,
    clock=monotonic_clock, cancelled=shutdown_requested,
    classify_model_failure=classify_model_failure,
).run(prompt, run_bash=trusted_run_bash, submit_flag=trusted_submit_flag)
# Return projection to the inherited solver/writer. Do not write a competing JSON file.
```

Owner records must be persisted before the callback, including an intent that
later becomes uncertain. If checkpointing fails, the callback is not invoked.
Cancellation between intent checkpoint and send preserves the pending intent.
An interrupt during submission marks it unresolved before propagating the
interrupt. Release/checkpoint failures are reported with fixed codes rather than
raw exception messages; a cleanup failure does not erase a definitive result.

Deadlines and cancellation are **cooperative** around synchronous calls. A call
already in flight cannot be interrupted by these guards. The inherited 180-second
model timeout and 120-second tool timeout remain unchanged. Hard attempt deadlines
still require bounded/cancellable owner callbacks; this adapter does not claim
that a 30-second experiment can forcibly stop those existing calls.

## Foundation review and remaining team gate

The merged foundation's 18 tests pass, and its checked-in documentation reports
image/arena execution. Review confirmed the one-challenge Brain seam and the single
official writer. A local synthetic reproduction also demonstrated that the default
Brain makes **two submission calls** when the first returns an unrecognized verdict
and the next model turn offers another candidate. The new adapter makes one call
and preserves uncertainty in that situation. Because activation is explicit, this
does **not** claim to have patched the default unadapted Brain path.

A separate setup issue is already addressed by Jerome's open
[PR #3](https://github.com/jerome-queck/incypher/pull/3): the merged entrypoint
unconditionally sources an existing Day-1 fallback file, which can overwrite
organizer-injected Day-2 model variables. That PR changes precedence and has its
own checks. It is not incorporated or merged by this strategy update; the captain
should include the reviewed runtime fix in his Day-2 release decision.

Shared-record conversion and the real-Brain fake lifecycle gates are now exercised
by executable tests. Remaining work before live activation:

1. Jerome binds trusted structured scope and budget at the supported seam. The
   inherited constructor currently receives callbacks and a prompt, not a
   `ChallengeScope`. Broad challenge ranking remains offline; do not add a second
   challenge loop to manufacture that hook.
2. Richard/Aidan supply the production `StrategyOwners` callbacks: confirmed
   evidence, candidate qualification, durable unique intents/reconciliation,
   checkpoint projection and actual cleanup. These modules were not present on
   the reviewed `main`; no replacement implementation is fabricated in this PR.
3. Jerome/Aidan agree/enforce hard runtime deadlines and cancellation for in-flight
   model/tool calls. The bridge already blocks subsequent calls after a deadline
   or cancellation and enforces model/tool counts before dispatch.
4. Jerome runs the module-in-image smoke and structural checks for the exact
   integrated image. Local Docker was unavailable. Preserve his known-good image;
   no registry push, live test or scored run follows from this code update.

## Rollback

Revert the strategy feature commits to remove these nine newly added files,
preserving Jerome's foundation. They change neither his Dockerfile/entrypoint nor
the current official image. The
optional selection policy is also reversible by choosing `COVERAGE` in a local
experiment. Once a future integration wires the controller into Brain, that
integration needs its own rollback alongside the captain's known-good image.

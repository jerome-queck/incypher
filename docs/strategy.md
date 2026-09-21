# Elson's strategy and controller

## Delivery status and scope

This change implements the independent, offline part of Elson's assignment:
deterministic scheduling, bounded serial attempt decisions, evidence-aware
continuation, retry classification, and owner handoffs. It adds no model client,
Board client, command executor, flag submitter, results writer, or autonomous loop.
It introduces no third-party runtime dependency.

**This is a draft integration slice, not a completed agent integration or a claim
of better CTF performance.** The source baseline is
`7fb4159857f1de56e79b4462ef05ea83b47eda1a` on `main`. The only changed paths are:

- `agent_ext/controller.py`
- `agent_ext/scheduler.py`
- `agent_ext/retry_policy.py`
- `tests/test_controller.py`
- `tests/test_scheduler.py`
- `tests/test_retry_policy.py`
- `docs/strategy.md`

Jerome's foundation [PR #1](https://github.com/jerome-queck/incypher/pull/1) appeared
during implementation. The reviewed draft head is
`d48247e765aa68b4b3e593d084213be3405fde94`; it is not merged into this branch.
Its `docs/interfaces.md`, `docs/arena-contract.md`, semantic records, adapters,
and `brain.py` were inspected. Its documentation identifies the extension as
`Brain(run_bash, submit_flag, max_steps).solve(prompt)`, handling **one challenge**.
Inherited `main.py` owns challenge enumeration, `solver.py` owns materials and
instances, and the inherited harness owns official results output.

Consequently the multi-challenge scheduler below is an **offline policy experiment**
until Jerome identifies an authorized selection seam. It must not drive another
challenge loop around the inherited harness. The controller can be evaluated with
one qualified challenge at the Brain seam; wiring even that requires agreement
on the shared records and callback budget/cancellation enforcement.

`main` still has a one-line Dockerfile and excludes everything except Dockerfile
from the build context. These Python modules are therefore not in that baseline
image. PR #1 proposes packaging changes; this PR makes none. No image build,
structural checker, live evaluation, registry submission, or official-harness
compatibility is claimed for these modules.

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

Use `python` on Windows. This slice has **76 tests**: 47 controller/lifecycle,
17 retry, and 12 scheduler tests. They passed on Windows Python 3.13.6 and Ubuntu
Python 3.12.3, with zero failures or skips. Controller and lifecycle fixtures forbid
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
ruff check --isolated --select E,F,I,B,UP --ignore E501 agent_ext/controller.py agent_ext/scheduler.py agent_ext/retry_policy.py tests/test_controller.py tests/test_scheduler.py tests/test_retry_policy.py
ruff format --isolated --check agent_ext/controller.py agent_ext/scheduler.py agent_ext/retry_policy.py tests/test_controller.py tests/test_scheduler.py tests/test_retry_policy.py
git diff --check
```

## Mapping to Jerome's draft and remaining integration gate

The local records are deliberately labeled provisional. They are not imported
from or exported through Jerome's unmerged `contracts.py`. This mapping describes
the work to agree after he confirms the foundation is ready; it does not assert
that integration already works.

| Foundation record at reviewed PR #1 head | Mapping/decision still needed |
| --- | --- |
| `ChallengeScope` | Map integer ID, material reference and instance generation to sanitized local `Scope`; retain parent `attempt_id`/session provenance. Category/name are metadata, not authority. Supply trusted `authority_ref` separately. Do not parse authority out of untrusted prompt text. |
| `Budget` | Its decision steps, submissions and optional deadline do not represent all local model/tool counters. Agree counting and cap actual calls by both budgets. Richard's submission allowance remains authoritative. |
| `NextAction` | Project a local decision into agreed kind/arguments/reason inside the existing Brain flow. Do not turn it into a second outer loop or a new command interpreter. |
| `ToolResult` | Map measured counts/cost and classified failures through Aidan. An observation reference or successful exit alone is not confirmed progress; Richard must supply scope, kind and canonical identity. |
| `Candidate` | Richard retains the sensitive value/evidence; provide a stable scoped fingerprint to this controller. No raw candidate in reasons, logs or snapshots. |
| `SubmissionResult` | Richard's intent ledger must associate intent ID with exact scope/candidate. Correct/incorrect map to definitive owner outcomes. Uncertain/error/rate-limit outcomes preserve intent. Agree `already_solved` projection without claiming a fresh solve. |

Failure mappings need operation context: for example `MALFORMED_RESPONSE` cannot
be blindly treated as a repairable request; `RESOURCE_LIMIT` is OOM only when
measured evidence establishes that; cancellation must stop admission. A rate
limit does not authorize replay of an instance mutation or submission. Shared
records currently lack all the evidence-confirmation and retry-guidance fields
needed here. Jerome plus the affected owner must agree any additions.

Before changing this PR from draft to integration-complete:

1. Jerome confirms the inspected foundation head and chosen extension seam, and
   the team agrees whether broad challenge ranking has a supported hook or remains
   offline. Use his current interface rather than replace inherited iteration.
2. Align the local records to the shared contract with explicit conversion tests.
   Richard agrees evidence identities, wrong/uncertain outcomes, negative evidence,
   checkpoint/restart semantics and `already_solved` behavior.
3. Jerome/Aidan make actual model/tool calls honor remaining budgets and
   cancellation, drain resources, and return accurate usage/failure reports.
4. Trace the same fake lifecycle through the **real** Brain/shared adapters with
   one intent ledger, submitter and official writer. Run the combined nonempty
   offline suite. The draft fixture above is necessary evidence, not this gate.
5. Jerome packages the agreed code, runs module-in-image smoke and structural
   checks, and preserves a known-good baseline. No live or scored run follows
   automatically from this development PR.

## Rollback

Revert the strategy PR commit to remove these seven newly added files. It changes
neither the baseline Dockerfile/entrypoint nor the current official image. The
optional selection policy is also reversible by choosing `COVERAGE` in a local
experiment. Once a future integration wires the controller into Brain, that
integration needs its own rollback alongside the captain's known-good image.

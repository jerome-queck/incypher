# Overnight solver build brief

Prepared 21 Sep 2026. This is the user-authorized scope for the next build session,
not an architecture decision or a claim that the solver is ready.
Launch with [prompt.md](prompt.md); consult [research.md](research.md) by workstream.

## Outcome and authority

Produce a robust, resource-compliant solver that maximizes valid competition points
under an unknown prescribed model and the competition allowance. Demonstrate all 15
practice challenges on the live board during the session, and measure capability on
harder held-out tasks. Winning is the ambition; an unseen competition win cannot be
certified by a practice score.

The build session may research, design, implement, run bounded paid local experiments,
change the private local model to Luna high, create/review/merge PRs, and perform the
requested readiness-gated **Day-1 arena release**. Carry this authority through the
session. Prepare and verify a separate clean Day-2 image; this brief does not request
a scored Day-2 re-upload or an organiser restart. The prompt-authoring session only
changes documentation. Runtime implementation and provider configuration belong to
the build session.

Use [competition-rules.md](../competition-rules.md) for scope, scoring, sandbox and
release constraints; [setup.md](../setup.md) for execution; [interfaces.md](../interfaces.md)
before shared-seam changes; [model-guidance.md](../model-guidance.md) for development
instructions. Those remain authoritative rather than copying their rules here.

## Clocks and completion

- Feature freeze/readiness target: **22 Sep 2026 06:30 Asia/Singapore**
  (`2026-09-21T22:30:00Z`). Afterward, only small, verified configuration changes.
- Competition spending horizon: **22 Sep 2026 16:30 Asia/Singapore**
  (`2026-09-22T08:30:00Z`). This is soft pacing, not an invented container wall timer.
- Read the real clock at launch, each stage transition, before long experiments and
  releases, and at least every 15 minutes of active work. Recompute time remaining;
  reserve measured build, review, live-run, collection and rollback time. Choose those
  allocations at launch and revise when evidence changes them.
- Earlier completion is valid if every gate passes. If time expires first, preserve
  the best verified image and report partial completion; leave failed/unproven gates
  open. Scope deferral is recorded, never relabeled as a successful implementation.

Full completion requires: every required workstream below integrated and validated;
reviewed changes merged; runtime regression and exact-image checks passed; a clean
Day-2 image identified; **15/15 live practice board coverage with origin evidence**;
and independently credible current-solver capability evidence for all 15. Record the
baseline, new arena acceptances, cumulative board state, local validations and post-run
replays separately. `already_solved`, an old score or a posthoc replay cannot supply a
missing fresh acceptance. If the platform cannot provide an attribution or a fresh
verdict, keep that gate unproven and complete independent work meanwhile.

## Required workstreams and observable gates

The implementation, numerical policies and sequencing are open decisions. Inspect
existing modules before choosing reuse, simplification or replacement. For each row,
record the decision, evidence, alternative considered, cost and remaining uncertainty.

| Workstream | Required behavior | Completion evidence |
| --- | --- | --- |
| Runtime integration | Real harness → trusted scope → admission → model/tools → durable evidence/submission → inherited results; all modules cooperate | End-to-end accepted/rejected/uncertain/cancelled/restarted attempts using production adapters; no competing lifecycle/results owner |
| Model and budget | Read injected identity; discover supported capabilities and provider metering where available; account for calls, reasoning/cache cost, retries, in-flight work and restart continuity; adapt effort/admission/pacing to remaining funds | Reconciled spend ledger with measured/estimated/unknown labels; missing/late usage, concurrent reservations, near-exhaustion and restart checks; no accidental model substitution |
| Solve strategy | Triage, test hypotheses, exploit, verify; weak-model instructions support concrete progress and correct tool use | Matched Luna-high baseline/change experiments with valid points, first-pass coverage and failure causes; no quality regression hidden by token savings |
| Specialists and playbooks | Category-specific guidance accessible on demand; investigate skills versus role prompts and tool subsets without assuming arena-native agent APIs | Trigger/prerequisite/diagnostic/next-step/verification guidance for observed categories; successful unseen or transformed tasks; measured delegation benefit before multiplying LLM calls |
| Context and memory | Bounded RAM and prompt growth; scoped facts versus hypotheses; retain unsuccessful methods/candidates, artifact references, useful partial progress and next experiment across interruptions | Restart/compaction preserves useful knowledge; stale instance/material evidence invalidates; duplicate work falls; context/retention limits and concurrent reads/writes hold |
| Concurrency and resources | Useful work during tool/network waits; dynamic scale up/down; aggregate CPU, RAM, PID, disk and output bounds with harness headroom | Production image tested under arena limits with multiple static jobs plus the permitted dynamic work; bounded queues/backpressure, descendant cleanup, storage growth and resource peaks recorded |
| Recovery | Early timeout detection, typed failure records, bounded retries, checkpoints, internal restart and independent quiet-stall detection | Inject model hangs, slow productive tools, tool crash, 429/5xx, interrupted submission, worker death and coordinator stall; eventual recovery/explicit state with no duplicate effects or restart storm |
| Persistent queue | Failed attempts defer, cool down or change strategy; unsolved challenges remain eligible while authorized work and budget exist; exploit waiting time without blind repetition | Aging/fairness, prior-attempt penalties, new-evidence revival, transient locks, all-waiting/all-solved/empty catalogue and budget exhaustion tests; explained next choices |
| Tooling and packaging | Add category coverage justified by failures; retain compact image and discover actual image/storage limits | Tool availability in the exact image, measured layer/pull/startup cost and runtime footprint; bounded interactive, binary, web, crypto, archive/forensics workflows as required by evaluated tasks |
| Evaluation and release | Generalize beyond known answers; preserve source/image/model/task provenance | Registered held-out evaluation, fresh-material practice validation, readiness-gated Day-1 board evidence, clean Day-2 image and rollback receipt |

“Never give up” means retaining unresolved work and revisiting with a justified next
experiment. It does not authorize infinite paid calls, replaying uncertain submissions,
spinning while blocked, retaining stale targets or ignoring cancellation/exhaustion.
Distinguish attempt/tool deadlines, budget admission and global scheduling lifetime.
OS/container termination may be unrecoverable; test internal recovery and report what
the platform must recover. Finite guards protect a persistent scheduler.

## Local experiments and live readiness

Use `/Volumes/Working/002 Carry/incypher colima` for the requested Colima storage;
inspect the installed profile/runtime before changing it. Preserve other profiles.
Separate host capacity from the sandbox constraints applied to **each** candidate
solver. Parallel local fixtures/static experiments may share host resources with
isolated state; all live experiments share the team's dynamic-instance allowance.

Use local Codex Luna/high where appropriate, but validate the submitted Brain through
the private OpenRouter API as well. The existing Chat Completions loop needs an actual
reasoning-parameter path; changing only `.env` cannot set effort. Verify the catalog ID,
request compatibility and response metadata. Resolve unavailable access explicitly,
without silently using another model or effort. “Training” here means evaluating and
improving the scaffold/playbooks, not a requested model-weight fine-tune.

Record a bounded private experiment spending envelope before paid calls. Development
credits, Codex usage and the competition $100 allowance are separate ledgers; an
account balance is not automatically the team's event allowance. The budget strategy
must work with an opaque compatible provider. Never forward an injected secret to
OpenRouter just because its shape resembles an OpenRouter key; use the configured,
trusted provider's documented API only when applicable. Keep estimates conservative
and expose uncertainty. No top-up or credential creation is included.

Before the Day-1 release, preregister the confidence gate and show evidence covering
the remaining unsolved challenges and key regressions. Use fresh material and the
production code path. Establish whether local submissions consume fresh arena-origin
attribution; use non-submitting local validation when needed to preserve that evidence.
Verify the released image restores its real submission path. Keep answer oracles and
full competition writeups in a separate
evaluation process, outside solver images, prompts, memory and mounts. A general
playbook derived from public prior competitions is permissible research; evaluating
on those same explained tasks is not held-out proof. Release early enough for measured
runtime and board collection, rather than leaving live evidence until feature freeze.
Observe passively; coordinate existing arena activity before local dynamic tests.

## PR and agent workflow

The main agent owns integration, shared seams, private session files and concise
milestone updates. Keep PRs independently buildable; retain the last checked image
while the next PR develops. At each runtime merge, build/check the resulting source
or prove its tree matches the already checked candidate, and record source, base/image
digests, architecture, checks and rollback. Git merging and registry publishing remain
separate. Pure documentation changes need proportional documentation checks.

Use four bounded roles, all explicitly **gpt-5.6-sol / medium**: design, implementation,
Standards reviewer and Spec reviewer. At review readiness, invoke
[$code-review](/Users/jeromequeck/.agents/skills/code-review/SKILL.md)
with a resolved base SHA and per-PR spec path. Read [issue-tracker.md](../agents/issue-tracker.md)
for spec lookup. Reviewers inspect the same frozen head independently; preserve both
reports and resolve actionable findings before merge. Re-review changed substantive
hunks, not unrelated already-cleared work.

Available agent slots govern scheduling. If the root plus four children cannot run
together, finish/release design or implementation work before the two reviewers;
reuse bounded workers where required. An interrupted/idle child may still occupy a
slot; inspect the actual tool behavior. Never claim four simultaneous agents where
the platform cannot support them. Include the explicit Sol/medium choice in each
child's prompt and tool configuration, with bounded context, owned paths and evidence
required. For a skill-bearing child prompt, begin with its resolved
`[$skill-name](/absolute/path/to/SKILL.md)` invocation. Keep the root model unchanged.

## Session records and provisional stages

Use ignored `private/solver-build-20260921/` in this checkout. If absent in another
checkout, initialize it from the schemas below; read existing records before writing.
The main agent is their sole writer. Store raw logs separately and link them. Commit
sanitized durable contracts to their existing component docs and current shared state
to `docs/context.md`; session files are not part of the Docker build context.

- `state.md`: SGT timestamp; objective/status; source/PR/image identities; last verified
  baseline; active agents/experiments and their ownership; remaining time and money;
  unresolved effects/blockers; next action. Replace stale state in place.
- `plan.md`: checkbox stages with acceptance evidence, owner, estimated finish,
  dependency and status (`pending`, `active`, `verified`, `deferred`, `blocked`).
  `[x]` requires evidence. Keep a short dated change log explaining revisions and
  explicit unmet/deferred requirements.
- `experiments.md`: per-run hypothesis, frozen source/image/model/effort/task set,
  isolation/contamination controls, spend/time/resource bounds, success/failure
  thresholds, result/evidence path and decision. Register before launching; append
  outcomes without rewriting the original hypothesis or gate.
- `specs/<pr>.md` and `reviews/<pr>/`: freeze the requested behavior and acceptance
  checks for each PR, plus base/head identities and both review reports. Agent handoffs
  use the existing [context packet](../context.md#context-management).

Initial stages, **to be scheduled/revised by the build session**:

- [ ] Baseline: fresh contract/base, current board, runnable image, Luna-high/API
  compatibility, local resources and spend envelope; measured gaps and timelines.
- [ ] Design: select end-to-end seams and first PR from evidence; record all workstream
  decisions and open questions; assign bounded design/implementation tasks.
- [ ] Integrate: repeat small implement → regressions → independent reviews → merge
  → checked-image cycles; record gains and discard or revise failed experiments.
- [ ] Capability: matched controls and harder held-out tasks; validate playbooks,
  memory/context efficiency, budget/concurrency coupling and recovery under limits.
- [ ] Live proof: readiness-gated Day-1 release; observe 15/15 and origin evidence;
  diagnose gaps autonomously within the remaining development window.
- [ ] Freeze: clean Day-2 image, release checks and handoff by 06:30; report every
  unverified gate and remaining configuration-only action.

Live proof may start before the capability stage is exhausted when its gate is met.
Do not serialize independent work unnecessarily. Keep one next executable action in
`state.md` even when another experiment is running.

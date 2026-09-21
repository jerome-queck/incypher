# Repository context

Updated 21 September 2026. Read this first on a new task, after compaction, or before
assigning a bounded subtask. Rules live in [competition-rules.md](competition-rules.md);
machine commands live in [setup.md](setup.md).

## Objective and current state

Team **63 — procrastinators**. User-confirmed scored window: **22 Sep 2026,
10:00–16:30 Asia/Singapore**. Optimize autonomous, valid points; equal points favor
finish time. This docs/setup pass does not certify a competition-winning solver.

Audited starting source: `6db8a39` on `main`. All five prior PRs (#1, #2, #3, #9, #12)
were merged. No open PR contained the requested general practice-selection change.

| Path | Actual status | Consequence |
| --- | --- | --- |
| `entrypoint.sh` → `arena_main.py` → inherited `main.py` | Active; practice selection and trusted per-challenge context wrappers | Official selection (`ONLY_IDS`), solving, instance lifecycle and results remain inherited; signature drift fails closed |
| `validation_main.py` | Optional single-ID build mode; shares normal wrapper | Omit validation selector in competition image |
| `brain.py`, `agent_ext/adapters.py` | Active bounded Chat Completions loop | Exact model gateway, point-based call caps, tool/submission caps, 48 KiB context and deterministic category playbook; shell remains synchronous |
| `agent_ext/model_gateway.py`, `provider_discovery.py` | Active in Brain | Exact identity, OpenRouter capability/pricing discovery, high reasoning when supported and durable conservative ledger; opaque pricing remains unknown |
| `controller.py`, `scheduler.py`, `retry_policy.py`, `strategy_bridge.py` | Merged; offline tested; unconnected to normal construction | No production scheduling, global budget or autonomous retry guarantee |
| `resources.py`, `tools/` | Merged fixed local inspections | Not a bounded replacement for arbitrary shell; not invoked by normal Brain |
| `memory.py`, `verification.py`, `submission_state.py`, `results.py` | Merged evidence/SQLite helpers | Production callbacks and official result mapping remain unconnected |
| `scripts/arena.py` | Local setup/build/check/practice/push utility | Explicit API-backed practice; Day-1 secret handling; clean Day-2 build path |

Confirmed bugs corrected in this pass: normal practice exclusion; duplicate flag
submissions from tool calls or repeated assistant text; continuation after an unknown
submission verdict; malformed model/tool argument shapes crashing or dispatching empty
commands; explicit blank runtime config incorrectly loading the Day-1 fallback;
raw provider exception text leaking into results. The optional bridge retains its bounded repair classification.

## Evidence and release identity

- Public boards at **21 Sep 21:49 SGT**: rank 8, VALID 650, SCORE 650, five solves;
  status 5/15, 12 pushes, last push 17:43:14, `done`, penalty 0. This is Day-1 evidence,
  not final competition score. Read `/scores` and `/status` again for current values.
- Source docs previously called an older digest “current.” That is historical evidence
  only: public status does not identify the deployed digest or its source commit.
- [Arena contract](arena-contract.md) records an earlier inspected base/harness.
  Fresh registry manifest inspection in this pass returned authentication required;
  the official base is not cached on this machine. Current base drift remains unknown.
- This pass creates a Git PR and merge, not a registry release. No practice challenge,
  flag submission, paid API call or organiser restart was performed by this audit.
- `.venv` is installed locally. The ignored mode-0600 `.env` is populated on this machine
  with Team 63 platform configuration and the Day-1 provider triplet migrated from the
  prior private files. `doctor` reports every required field set, registry login succeeds,
  and Codex CLI reports ChatGPT login. No value or account token was logged or committed.
- Build-session baseline `e462e12` produced local AMD64 Day-2 image
  `sha256:b2230fa5473dcb09af891e9c07d9a3e4b13be5406f995a9795383392115bdd6f`
  from official base `sha256:d3c707c6187f49a8b5f0ba617b9590cce72a18676d93343a93098726c7723224`.
  The checker passed 6/6 checks with the expected root/no-token warnings; Day-1 secrets
  and validation selector were absent. This is a local rollback identity, not a release.
- Merged gateway PR #15 produced local AMD64 Day-2 image
  `sha256:0bc8f980859e3367dc78e5c977016bf2059bf5fc53c03c004bb60cbc0143a074`.
  Its checker passed 6/6 with the same expected warnings; an in-image Python 3.12 import
  of `ModelGateway` and `BudgetLedger` passed. The candidate suite passed 235 tests on
  macOS with 19 Linux-only skips. A later documentation-only evidence commit does not
  alter any path copied by the Dockerfile. Merge commit `8627839` is the PR2 base.
- Runtime-integration candidate `58eaae8` produced local AMD64 Day-2 image
  `sha256:aec2048b24b21427f749f35c4383270318bb2f817e199a4e16f1f413fb2176f2`.
  The checker passed 6/6 with the two expected warnings, and the macOS suite passed
  259 tests with 19 Linux-only skips. A preregistered, non-submitting Luna/high fixture
  exercised discovery, two model turns, one tool result, preserved provider reasoning
  metadata, one exact in-process submission and settled USD 0.0002678 with no unresolved
  reservation. This is local synthetic evidence, not practice or arena acceptance.
  Frozen review of head `02976ca` requested bounded HTTP streaming, prompt-safe trusted
  enums, fixed budget-policy bounds, catalogue-authorized canonical identity, full-or-reject
  file hashing and integrated lifecycle/fault coverage. Fix head `eb93ec0` passed 269 tests
  with 19 expected macOS skips and produced checked AMD64 image
  `sha256:cb07da46ef61f9135bfd7ab32c81dd61736d40c6fa58a0a8991177289adbafc8`
  (284,214,719 bytes; checker 6/0/2 expected warnings; in-image imports passed).
  Preregistered B4 on that exact image repeated the Luna/high fixture in 7.145s: two
  model calls, one tool, one correct in-process submission, USD 0.0002720 measured and
  zero unresolved. This evidence closes the fix-head pre-review checks, not CTF capability.
- Baseline: 199 offline tests passed on macOS; 19 Linux-only checks skipped.
  Changed-source suite: **216 passed on Linux AMD64/Python 3.12**, zero skips;
  macOS: 216 discovered, 19 Linux-only skips, zero failures. Compilation, shell syntax,
  local doc links, PDF redactions and whitespace checks passed. Historical image tests
  in [day2-readiness.md](day2-readiness.md) belong to their recorded source/digest.

## Next work, in order

The user has requested an overnight capability build. Start from the
[build brief](solver-build/brief.md) and its [launch prompt](solver-build/prompt.md).
The brief owns this session's goals, deadlines, delegation and Day-1 release authority;
its research records the audited starting gaps. Private progress lives under ignored
`private/solver-build-20260921/`. Architecture and PR ordering remain build-session
decisions. The prompt-authoring pass changed documentation only; solver readiness is
unchanged. A 21 Sep ~21:29 SGT public-board refresh still showed 5/15, VALID/SCORE 650,
12 pushes, `done`, penalty 0. No paid request or arena release was made by that pass.

The ordered technical gates below remain the starting baseline; the build session
may resequence them using the brief and measured evidence.

1. **Validate the integrated model path.** The exact-image non-submitting Luna/high
   fixture passes. Next use held-out local fixtures and one readiness-gated fresh-material
   practice validation; confirm inherited cleanup/results behavior before release.
2. **Prove solving.** Use one explicitly selected practice challenge via `scripts/arena.py`
   or local Codex practice. Record accepted outcome, elapsed time and model/tool usage
   privately; report sanitized counts. Local/manual solves do not prove arena VALID.
3. **Close the remaining production integration gap.** Use the trusted structured scope handoff;
   wire one attempt through real tools, evidence qualification, durable intents and
   inherited result output. Done when success, wrong candidate, ambiguous submission,
   timeout, cancellation and instance cleanup pass end-to-end with real adapters.
4. **Measure before optimizing.** Compare identical practice tasks and budgets for baseline
   versus a change. Prioritize valid points per cost/time, coverage and recovery. Static
   parallelism is permitted but unimplemented; dynamic capacity is globally one.
5. **Prepare the clean Day-2 image.** Follow [release gates](setup.md#day-2-release).
   Read runtime-injected model configuration; neither a Sol/Astra pin nor a local
   subscription is a substitute. Record the pushed digest and board outcome separately.

Known limits to investigate: shell execution is synchronous and output is captured before
the 12,000-character model excerpt; normal Brain has no persistent work queue, durable
progress memory, resource scheduler, transient model retry or quiet-stall watchdog.
Restart-safe cost reservations exist, but restart-safe challenge dedupe/recovery does not.
Day-2 request compatibility remains provider-dependent. Broad callback exception and
cancellation behavior remains the inherited harness's responsibility.

## Context management

Read only the branch needed for the task. Use this file for current shared state,
component docs for contracts, and Git/PRs for change history. Replace stale state in place.
Keep hypotheses separate from observed facts; preserve unresolved outcomes across handoff.

A handoff, including to a subagent when delegation is authorized, contains:

```text
Objective / completion criterion:
Source branch + SHA / changed paths:
Owned paths / shared seams affected:
Facts + source or test evidence:
Hypotheses / unresolved outcomes:
Validation passed / not run:
Next concrete action:
```

Assign disjoint paths and one bounded output. The integrating agent validates combined
behavior and updates this file. Carry decisions, citations and artifact references across
compaction; raw logs, candidate values and credentials stay outside committed context.

# Repository context

Updated 22 September 2026. Read this first on a new task, after compaction, or before
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
| `entrypoint.sh` → `arena_main.py` → inherited `main.py` | Active; trusted ranking/context/state/shell wrappers; PR4 multipass candidate under review | Serial inherited passes only; official filtering, challenge lifecycle, submissions and result writing remain inherited; exact inspected AST/signature drift fails closed |
| `validation_main.py` | Optional single-ID build mode; shares normal wrapper | Omit validation selector in competition image |
| `brain.py`, `agent_ext/adapters.py` | Active bounded Chat Completions loop | Exact model gateway, runtime `MAX_STEPS` slice cap, remaining-budget notices, one candidate per evidence turn, 48 KiB context, category playbooks, bounded sync/async shell tools and quiet-stall stop |
| `agent_ext/model_gateway.py`, `provider_discovery.py` | Active in Brain | Exact identity, OpenRouter capability/pricing discovery, high reasoning when supported and durable conservative ledger; opaque pricing remains unknown |
| `controller.py`, `scheduler.py`, `retry_policy.py`, `strategy_bridge.py` | Merged; offline tested; unconnected to normal construction | No production scheduling, global budget or autonomous retry guarantee |
| `agent_ext/managed_shell.py`, `resources.py` | Active shared admission and process supervision | Two active/one heavy; streamed 12 KB output, 45s/90s deadlines, process-group cleanup and credential-free environment; estimates are defense in depth inside the arena sandbox |
| `agent_ext/runtime_state.py` | Active bounded SQLite seam; PR4 typed-findings candidate under review | Restart-safe backoff, scoped command/finding dedupe and <=16 record/8 KiB projection; raw commands, output, flags and credentials are not stored |
| `memory.py`, `verification.py`, `submission_state.py`, `results.py` | Earlier offline helpers remain unconnected | PR3 uses the smaller runtime-state seam; inherited result mapping remains authoritative |
| `scripts/arena.py` | Local setup/build/check/practice/push utility | Explicit API-backed practice; Day-1 secret handling; clean Day-2 build path |

Confirmed bugs corrected in this pass: normal practice exclusion; duplicate flag
submissions from tool calls or repeated assistant text; continuation after an unknown
submission verdict; malformed model/tool argument shapes crashing or dispatching empty
commands; explicit blank runtime config incorrectly loading the Day-1 fallback;
raw provider exception text leaking into results. The optional bridge retains its bounded repair classification.
PR3 additionally bounds arbitrary shell capture, reaps descendants, prevents same-scope
exact-command replay, stops three quiet turns after one replan, limits one candidate per
evidence turn, classifies tool/crash outcomes durably and skips trusted solved briefs
outside explicit validation images.
PR4 candidate adds strict typed safe findings and bounded serial same-run revisits governed
by [strategy.md](strategy.md). Its first held-out image passed RSA but exhausted
the baked 6/10-turn limits on network/reversing without submissions. The repaired candidate
uses inherited runtime `MAX_STEPS` directly, exposes dollar/tool controls to the
local CLI, tells the model its remaining slice budget, and adds bounded generic aligned
known-plaintext network guidance. Reset-set practice remains parked until final review/merge.

## Evidence and release identity

- Public boards at **21 Sep 23:30 SGT**: rank 10, VALID 650, SCORE 650, five solves;
  status 5/15, 12 pushes, last push 17:43:14, `done`, penalty 0. This is Day-1 evidence,
  not final competition score. Read `/scores` and `/status` again for current values.
- Source docs previously called an older digest “current.” That is historical evidence
  only: public status does not identify the deployed digest or its source commit.
- [Arena contract](arena-contract.md) records an earlier inspected base/harness.
  Fresh registry manifest inspection in this pass returned authentication required;
  the official base is not cached on this machine. Current base drift remains unknown.
- PR3 merged through PR #17 as `8b86f1c`; exact merged AMD64 image
  `sha256:60ba38f971224119de9b16a23cb50af76ad046bc53506dbf3ce35dc2003b2c83`
  passed 300 tests/25 skips, checker 6/0/2, eight AST guards and 67 focused Linux tests.
  B7 solved a fresh exact-image fixture for USD 0.00173741 but used four calls against its
  preregistered three-call cap, so capability remained red. No reset-set practice challenge,
  platform submission, registry release, dynamic instance or organiser restart occurred.
- Initial PR4 head `c8294b7` passed independent Standards/Spec review, 322 portable tests
  with 25 skips and exact-image structural/Linux checks. Its first held-out battery was
  1/3: RSA passed; network used all 6 model calls and reversing all 10 model/12 tool calls,
  both without submission or provider/dollar fault. Those consumed cases remain failures;
  fresh cases are required after the bounded runtime-budget repair.
- Final PR4 candidate head `0b1c541` passes 325 portable tests with 25 expected skips.
  Exact AMD64 Day-2 image `sha256:8037235c5f3ef870b9c5427da69c7539e419408573b5977e1bf3c2bcbfa83cf3`
  is 284,036,961 bytes and passes checker 6/0/2, all eight AST guards, clean configuration,
  imports and 134 focused non-root Linux tests with ResourceWarnings fatal. Fresh exact-image
  held-out cases pass RSA (4 calls/3 tools), network (5/4 under a 12/16 planning ceiling),
  and reversing (6/5), each with one correct/zero wrong submission and zero unresolved spend.
  This is local synthetic capability evidence, not practice or arena acceptance.
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
- Final PR2 review passed and PR #16 merged as `a0b182a`; merged source produced checked
  AMD64 image `sha256:dee439a27b65ab2d260fcd711f3a7839ba2c1d180776ca5fba33ff2e3b3da9ce`
  with 269 tests passing and 19 expected macOS skips.
- PR3 candidate from base `a0b182a` passed 297 macOS tests with 25 expected platform
  skips, compilation and whitespace checks. Exact AMD64 image
  `sha256:d2e2b8eb476eac12df4fd0dab52cd62cb966070e5a287875bb1d2ffa107564ee`
  is 284,017,157 bytes; checker 6/0/2 expected warnings, exact official AST guard,
  imports and clean Day-2 config passed. Sixty-four focused tests passed inside that
  image on Linux with ResourceWarnings promoted to errors, including six process tests.
  B5 then solved one unseen hex-transformed local fixture through the real stateful shell
  in 12.085s: three Luna/high calls, two tools, one correct in-process submission,
  USD 0.0009127 measured and zero unresolved; scoped memory was 2 records/139 bytes.
  This is synthetic capability/plumbing evidence, not practice or arena acceptance.
- Initial independent PR3 review found missing `is_practice` drift validation, an
  overbroad crash catch, duplicated shell-status policy, non-durable in-flight progress,
  and missing integrated async/quiet acceptance coverage. A Standards re-review then
  identified the client-constructor AST seam and duplicated state upsert. CI then exposed
  host-global `RLIMIT_NPROC` behavior under a busy non-root runner; the shared 64-PID
  admission budget remains while that ineffective arena-root limit is omitted. Final
  runtime head `c36b22f` resolves all findings and passes 300 macOS tests with 25 expected
  platform skips. Exact AMD64 image
  `sha256:9381bb113e12df5224455f9b905426c88ef039803bb8e8aaa2dca49da7820052`
  is 284,031,687 bytes; checker 6/0/2 expected warnings, all eight official AST guards,
  imports and clean Day-2 config passed. Sixty-seven focused Linux tests passed as a
  non-root user with ResourceWarnings fatal. Final Standards/Spec re-reviews passed and
  PR #17 CI passed twice before merge.

## Next work, in order

The user has requested an overnight capability build. Start from the
[build brief](solver-build/brief.md) and its [launch prompt](solver-build/prompt.md).
The brief owns this session's goals, deadlines, delegation and Day-1 release authority;
its research records the audited starting gaps. Private progress lives under ignored
`private/solver-build-20260921/`. Architecture and PR ordering remain build-session
decisions. The prompt-authoring pass changed documentation only; solver readiness is
unchanged. A 21 Sep 23:30 SGT public-board refresh still showed 5/15, VALID/SCORE 650,
12 pushes, `done`, penalty 0. No paid request or arena release was made by that pass.

The ordered technical gates below are current after PR3 merge and PR4 implementation.

1. **Review and merge PR4.** Freeze safe-findings/multipass source; require independent
   Standards and Spec pass, exact AMD64 structural/Linux checks and merged-tree rebuild.
2. **Prove solving.** Pass fresh RSA, framed-network and stripped-ELF held-out fixtures,
   then use the CLI for the reset practice set only after the capability gate is green.
   Start with one readiness-gated explicitly selected challenge via `scripts/arena.py`
   or local Codex practice. Record accepted outcome, elapsed time and model/tool usage
   privately; report sanitized counts. Local/manual solves do not prove arena VALID.
3. **Measure before optimizing.** Compare identical practice tasks and budgets for baseline
   versus a change. Prioritize valid points per cost/time, coverage and recovery. Static
   parallelism is permitted but unimplemented; dynamic capacity is globally one.
4. **Readiness-gated Day-1 release and evidence collection.** Require fresh production-path
   evidence for the remaining tasks, then publish the authorized private-key image early
   enough to observe hands-off results and preserve rollback.
5. **Prepare the clean Day-2 image.** Follow [release gates](setup.md#day-2-release).
   Read runtime-injected model configuration; neither a Sol/Astra pin nor a local
   subscription is a substitute. Record the pushed digest and board outcome separately.

Known limits: shell operations may overlap inside one model conversation, but challenge
lifecycles and inherited passes remain serial, so dynamic capacity stays one. Durable typed
findings are deliberately conservative and not yet measured on real CTF work. Provider and
submission uncertainty remain terminal to avoid duplicate paid or submission effects.
Day-2 request compatibility remains provider-dependent; dynamic cleanup remains inherited.

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

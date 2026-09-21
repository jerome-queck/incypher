# Repository context

Updated 22 September 2026. Read this first on a new task, after compaction, or before
assigning a bounded subtask. Rules live in [competition-rules.md](competition-rules.md);
machine commands live in [setup.md](setup.md).

## Objective and current state

Team **63 — procrastinators**. User-confirmed scored window: **22 Sep 2026,
10:00–16:30 Asia/Singapore**. Feature freeze is 06:30. Optimize autonomous, valid
points; equal points favor finish time. The live-practice target remains 15/15; queueing,
unit tests and synthetic solves are not scoring proof.

Audited starting source: `6db8a39` on `main`. All five prior PRs (#1, #2, #3, #9, #12)
were merged. No open PR contained the requested general practice-selection change.

| Path | Actual status | Consequence |
| --- | --- | --- |
| `entrypoint.sh` → `arena_main.py` → inherited `main.py` | Active; trusted ranking/context/state/shell wrappers; live persistent serial queue | One bounded solve slice per inherited pass, then local rerank/requeue; five-minute catalogue/public-crowd refresh; official filtering, challenge lifecycle, submissions and result writing remain inherited; exact inspected AST/signature drift fails closed |
| `validation_main.py` | Optional single-ID build mode; shares normal wrapper | Omit validation selector in competition image |
| `brain.py`, `agent_ext/adapters.py` | Active bounded Chat Completions loop | Exact model gateway, packaged 24-call/runtime-overridable `MAX_STEPS` slice cap, remaining-budget notices, one candidate per evidence turn, 48 KiB context, category playbooks, bounded sync/async shell tools and quiet-stall stop |
| `agent_ext/model_gateway.py`, `provider_discovery.py` | Active in Brain | Exact identity, OpenRouter capability/pricing discovery, Day-2 served-model discovery and durable conservative ledger; candidate requests high/medium reasoning only when discovered as supported and paces cumulative spend against a configurable window; opaque pricing remains unknown |
| `controller.py`, `scheduler.py`, `retry_policy.py`, `strategy_bridge.py` | Merged; offline tested; unconnected to normal construction | No production scheduling, global budget or autonomous retry guarantee |
| `agent_ext/managed_shell.py`, `resources.py` | Active shared admission and process supervision | Two active/one heavy; streamed 12 KB output, 45s/90s deadlines, process-group cleanup and credential-free environment; estimates are defense in depth inside the arena sandbox |
| `agent_ext/runtime_state.py` | Active bounded SQLite seam | Restart-safe backoff, scoped command/finding dedupe, keyed submission intent/reconciliation and <=16 record/8 KiB projection; raw commands, output, flags and credentials are not stored |
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
PR4 adds strict typed safe findings and serial same-run revisits governed by
[strategy.md](strategy.md). The release runtime passed fresh RSA/network/reversing at 3/3.
The deployed runtime removes arbitrary cumulative slice/call abandonment, retains the
per-slice inherited `MAX_STEPS` and dollar governor, and adds durable adaptive spend pacing.
PR #18 merged bounded five-minute public crowd signals, fail-closed Day-2 model
discovery, unresolved-dispatch shutdown and scoped submission reconciliation. PR #19
merged the measured 16-model/20-tool packaged slice; its Day-1 image is push #22.
PR #21 merged the packaged 24-model/28-tool slice; its Day-1 image is push #23.
The larger slice was tested locally: its
fresh synthetic P2 trial B30 passed in 5/5 calls/tools, below the previous 16/20
ceilings, so the larger bound's benefit remains unproven until live or comparative
evidence. Clean AMD64 Day-2 image
`sha256:e691820e47e36d038ec13b3bbb7736827862dfe1dbb87eeacb6d57fbfba9e8c2`
passed checker 6/0/2, 369 non-entrypoint tests inside the non-root read-only
2CPU/2GiB/256PID sandbox with ResourceWarnings fatal, and the 375-test host suite
with 25 expected platform skips; it has no Day-1 credential/validation selector
and is not the registry image. PR #22 merged the Brain change that reserves its
final model turn for submission or typed checkpoint when a finding callback exists.
One short fresh diagnostic saved a finding and another did not; full-slice B33
passed a fresh reversing case in 10/10 model/tool calls and B34 passed network
in 8/7. This is local continuity and regression evidence, not a cause proven
for the live scoring plateau. Checked Day-2 image
`sha256:2b90cabdd64a5f649cee3af2ec8c32c1555c2dc420da245aa921cbcfe67c808b`
passes checker 6/0/2, the full 378-test host suite with 25 expected platform
skips, and 372 restricted-container non-entrypoint tests;
the matching Day-1 image is push #24.
The next local candidate gives a public crowd solve signal at most two bounded
retry credits in the queue, preserving eligibility/backoff and returning to
ordinary attempt order after further misses. Its 379-test host suite passed
with 25 expected skips. Exact AMD64 clean Day-2 image
`sha256:780596b2464f889915d9307c4c606424d3ccee1ae0376bfdf7cbe378ec376b21`
passed checker 6/0/2 and 373 non-entrypoint tests in the restricted container;
matching Day-1 image
`sha256:679f517c3b9287afbf55cfb63f089b569844ef7e366e1b9623d1ffea62b16167`
passed checker 6/0/2, carries only five intended model/budget keys and no
selector. Independent Standards/Spec reviews and CI passed on PR #23 at
`89dbe69`, merged as `de7c201`. The matching Day-1 image is push #25;
this remains scheduling plausibility, not evidence of another arena solve.

## Evidence and release identity

- Day-1 push #20, source `3a3452e`, remote digest
  `sha256:44065c5107ddcbc132932e32563b04c7d10bf60cb07116c2b4ec9e3b2fd0166e`,
  began scoring at 03:10 SGT and earned eleven fresh
  arena-origin solves / 2,250 VALID points, rank 2, penalty 0. This is fresh live proof of
  persistent solving and queue rotation. See [release rules](competition-rules.md#submission-and-runtime-requirements)
  for the current re-upload policy. At 04:15 the explicitly requested
  replacement push #21 registered immediately; the registry confirms exact Day-1 digest
  `sha256:c7c21321634911e86d20d4b8eb2d1c6d2a314d88d2ad30524e08c209425e76d4`.
  At 04:30 the public row remained `running`, 11/15 and penalty 0. It does not expose
  the active run's digest; pickup of #21 is not proven. User-requested push #22 at
  04:30:59 now makes the independently verified remote `latest`
  `sha256:d7c560ff5bdbd40724f802e006d3d1835f5308c912a9fcb7e8b847009afd7f07`.
  At the 04:35 cycle the board remained RUNNING at 11/15, 2,250 VALID, rank 2 and
  penalty 0. At 04:40 the row remains RUNNING at 11/15 and penalty 0. It registered
  push count 22 but still exposed no active digest or new solve; actual pickup remains
  unproven. The conflicting public pickup descriptions are recorded in
  [competition rules](competition-rules.md#submission-and-runtime-requirements).
  PR #21 merged as `6d56f93`; the checked Day-1 replacement
  `sha256:ec016de958d729e65f6eda7e8af49c8bf206405182f2981052d16e797f3cbf60`
  was pushed at 04:49:24, and remote registry `latest` independently matched.
  At 04:55 the board registered push #23 and remained RUNNING, 11/15,
  2,250 VALID, rank 2, penalty 0, last own solve 03:25. Pickup still cannot be
  tied to an image from that aggregate view.
  PR #22 merged as `eb86d76`; checked Day-1 image
  `sha256:c684e40cf15c6f986733b18811cfecc3959adf792e84615d235e8fbe0f8c5137`
  was pushed at 05:02:19 and independently matched remote `latest`.
  At 05:03 the board registered push #24, remained RUNNING and still showed
  11/15, 2,250 VALID and penalty 0. During the 05:05 cycle it briefly showed
  COLLECTING, then RUNNING again by 05:05:29 with unchanged score. This is
  consistent with collection/replacement but does not identify an active digest.
  The 05:10 cycle still shows RUNNING, 11/15 and penalty 0, with no new own
  event or image identity.
  PR #23 merged as `de7c201` after independent reviews and CI. The checked
  Day-1 image `sha256:679f517c3b9287afbf55cfb63f089b569844ef7e366e1b9623d1ffea62b16167`
  was pushed at 05:14:04; the remote registry `latest` independently matched
  that digest. The board registered push #25, RUNNING at 11/15, 2,250 VALID,
  penalty 0. The 05:15 cycle still showed RUNNING with no new own solve or
  active-image identity. Do not infer pickup from push registration alone.
- Local successor runtime `35de762` passes 375 host tests with 25 expected macOS skips;
  both exact-head source/spec and standards reviews pass. It separately persists
  account-terminal submission state and candidate verdicts across restarts and dynamic
  replacement, retaining both until a trusted solved catalogue confirms reconciliation.
  Exact AMD64 Day-2 image
  `sha256:cb09d7ddc72e02c06a1d2f8143d54acbd4192acba7109e1e65824b010f3e6833`
  is 284,043,833 bytes, passes checker 6/0/2, contains no Day-1 secret/selector, and
  passes 369 non-entrypoint tests inside the read-only 2 CPU/2 GiB/256-PID sandbox as
  non-root with ResourceWarnings fatal. The six entrypoint tests pass in the 375-test host
  suite. Checked Day-1 fallback
  `sha256:c7c21321634911e86d20d4b8eb2d1c6d2a314d88d2ad30524e08c209425e76d4`
  is 284,044,138 bytes, passes checker 6/0/2, contains exactly the five expected private
  model/budget names and no validation selector. PR #18 merged as `eb8c6bd`; this Day-1
  image was pushed as #21, while the clean Day-2 image remains local.

- Local held-out B26 on that exact successor was 2/3: fresh RSA and network accepted,
  reversing exhausted 10 calls/10 tools with no submission. B27 reproduced the
  reversing miss at 10 calls; its private sanitized command sequence reached inverse
  verification at the bound. B28 passed a fresh reversing case at 4/3 with a 16-call/
  20-tool visible ceiling; the newly packaged 16/20 candidate
  `sha256:5664fbe5cee84d2d0e2773478dfbbe27ccbd3113573d044a3026f5ff7a3cf629`
  passed another fresh reversing case in 10/12, one correct/zero wrong, measured USD
  0.00673036. These are synthetic local outcomes, not proof for the four live unsolved
  challenges. The checked Day-1 variant is
  `sha256:d7c560ff5bdbd40724f802e006d3d1835f5308c912a9fcb7e8b847009afd7f07`;
  both are AMD64/checker 6/0/2. PR #19 passed two independent reviews, both CI runs,
  375 host tests/25 skips and 369 exact-image restricted-container tests, and merged as
  `66613ef`; the Day-1 variant was pushed as #22. The clean Day-2 image remains local.

- Public board reset at **22 Sep 02:00 SGT** from 7/15 to 0/15. Push #13 used a clean
  Day-2 image during Day 1 and finished 0/15. At 02:14:37 both corrective Day-1 pushes
  registered; push #15, last 02:10:01, reached `running` on both status and scores at
  02:15:46, then changed to `collecting` by 02:18:20 with 0/15 and penalty 0. This is
  a historical early process exit; that image retained the old no-progress stop. Later
  push #20 proved the corrected persistent queue on eleven fresh arena-origin solves.
- Historical push #15 had the metadata-distinct Day-1 AMD64 digest
  `sha256:a9ecc2d9192eab938c6c34d51107ecd3ef338e64f52a98a84eb484d165ce8725`.
  It embeds only the model triplet plus a USD 19/fixed-high policy, has no CTF token or
  validation selector, passes checker 6/0/2, and its exact in-image harness/practice
  guards pass. Its queued runtime source was `a43e59b`; it is no longer registry
  `latest` after push #22.
- Source docs previously called an older digest “current.” That is historical evidence
  only: public status does not identify the deployed digest or its source commit.
- [Arena contract](arena-contract.md) records an earlier inspected base/harness. Both
  checked successors build from authenticated base digest
  `sha256:081f5477e3b222185a7265beacb9a90505b589a389adaa3352cf7afb4709531e`;
  inherited AST guards and the bundled checker passed. Reinspect the current tag before
  Day-2 release; a future base-tag change remains possible.
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
- Hardened release runtime `a43e59b` retained 3/3 on fresh B19-B21: RSA 4/3,
  network 7/7 under 12/16, reversing 9/8, one correct/zero wrong submission each and
  zero unresolved spend. Total measured development spend through B21 is USD 0.06853611.
- Frozen candidate runtime `a575a32` passes whitespace/compile checks and
  347 portable tests with 25 expected platform skips. Clean AMD64 Day-2 image
  `sha256:6e878ec8341b2898f5514365a7d7d86baedfd689e43eb8dda5e73871894cc927`
  is 284,038,804 bytes and passes checker 6/0/2, all eight official guards, clean config,
  imports and 145 focused non-root Linux tests with fatal ResourceWarnings. Independent
  review remains before it may replace the queued release.
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

The [build brief](solver-build/brief.md) owns the 06:30 freeze, live 15/15 and clean
Day-2 acceptance gates. Ignored `private/solver-build-20260921/{state,plan,experiments}.md`
holds detailed cost, experiment and provenance records. Current priorities:

1. **Monitor push #25 without manual solving.** Read public status/scores through upcoming
   cycles; distinguish registration, active-image pickup, VALID solves and penalties.
   Its registry digest is proven; the board does not identify the active digest. Do not
   request an organiser rerun or repeat an unchanged push.
2. **Close the four remaining practice solves.** Keep the unsolved queue and model-dollar
   controls active. Evaluate new generic capabilities on fresh scoped work and make a
   replacement image only after a bounded measured change;
   use the [release rules](competition-rules.md#submission-and-runtime-requirements)
   for penalty and pickup uncertainty. Preserve negative local held-out results.
3. **Freeze and prepare Day 2 by 06:30.** Retain the verified clean AMD64 image, inspect
   fresh base/contract drift, and follow [release gates](setup.md#day-2-release). Do not
   treat structural checks or local solves as competition acceptance.

Known limits: shell operations may overlap inside one model conversation, but challenge
lifecycles and inherited passes remain serial, so dynamic capacity stays one. Durable typed
findings are deliberately conservative and not yet measured on real CTF work. An unresolved
gateway worker stops the process to avoid overlapping paid effects; submission uncertainty
defers only its exact material/instance scope until trusted catalogue reconciliation while
the queue continues.
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

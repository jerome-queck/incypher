# Repository context

Updated 22 September 2026. Read this first on a new task, after compaction, or before
assigning a bounded subtask. Rules live in [competition-rules.md](competition-rules.md);
machine commands live in [setup.md](setup.md).

## Current release and next action

Postmortem audit, 22 Sep (local, synthetic; release timeline below is historical):
the checked #34 and #35 image files match this working tree on the audited
runtime paths, except #34's earlier `runtime_state.py`. The clean Git baseline
`933c1e8` and exact #35 image both reproduce command reread deduplication,
pre-execution refusal deduplication, false progress from nonzero shell results,
rejected benign findings, and an 85-call stop **when** cost and pricing are
unavailable. The #35 image also kills a noisy computation at 12 KB. Cross-instance
semantic finding transfer and private bounded output recall are present in #34/#35,
so the postmortem's blanket loss-of-progress claim is only partly current.
The generic `flag{...}` description conflicts with the official
`INCYPHER{...}` format; a real mismatch is unproved. The inactive fixed-inspection
snapshot test passed 12/12 in the #35 Linux image. These probes do not identify
the cause of missed arena solves. Evidence seams: [shell wrapper](../arena_main.py),
[state](../agent_ext/runtime_state.py), [shell](../agent_ext/managed_shell.py),
[findings](../agent_ext/runtime_context.py), [budget](../agent_ext/model_gateway.py).
**Next action:** if attribution is needed, obtain sanitized #34/#35 run outcomes,
model-cost metadata and consistent ledger backups; no registry push follows from
this audit.

At 22 Sep 15:57:05 SGT, user-authorized 500-point-priority push **#35**
registered. The remote manifest matches the tested AMD64 digest
`sha256:8896c31d913226cc3c14f768e1219fbe332f627b625e740132150938ebb9f2f6`.
The public board charged the expected second 100-point re-upload penalty:
6 VALID / 750, **550 NET**, last own solve BadLE at 15:36. The #35 image
keeps #34's verified large-file fix and promotes locally reproduced unsolved
500-point methods **Relay #96** and **Spool #123** ahead of lower-value work;
remaining queue tiers sort trusted points descending. A fresh read-only
Team 63 catalogue ranked #96 and #123 first. Host suite 422 passed/31 skipped;
restricted exact-image suite 422 passed; checker 6/0/2; changed source hashes
matched the image; no Day-1 credential, private directory, validation selector
or challenge flag literal was packaged. After the 16:00 cycle, the public
resource feed showed a newly started Team 63 agent at about 16:00:09 working
on **Relay #96**. The board was still `collecting` the prior run; this confirms
the new queue's first selected challenge, not a solve or active-container
digest. **Next action:** observe subsequent VALID and instance lifecycle
without intervening. Do not push again without a distinct authorized reason.

At 22 Sep 15:30:17 SGT, the user-authorized recovery push **#34** registered
with the expected **-100** re-upload charge; it was `running` at 15:37.
At **15:36:27**, its run earned a fresh arena-valid **BadLE +250** solve.
The score board showed **6 VALID / 750 points, 650 NET** after that solve.
Its independently
verified registry digest is
`sha256:93443207dcda6c47516ac0573f54e1e48e5507313330fbbb8ad22a7dc22727a8`.
This image is the prior #32 source/architecture with one verified large-file
fix in `agent_ext/runtime_context.py`: an attachment over the 64 MiB hashing
cap no longer aborts challenge preparation; it remains available to the solver
under a fresh, non-reused evidence scope. The old exact #32 image failed
read-only challenge #3 before any model call with `ValueError: attempt crashed`;
the repaired exact image reached a fake model call on that same authenticated
read-only challenge detail and downloaded file, without an instance or flag
submission. Host suite 421 passed/31 skipped; restricted image suite 421 passed;
checker 6/0/2; no Day-1 credential or validation selector in the package.
This proves the large-file fix reaches a scored solve, but does not establish
the unobserved cause of #33's exit 1. **Next action:** allow #34 to continue
autonomously; check public status and VALID at a meaningful later point, and
obtain sanitized arena logs if it exits.
No further registry push is authorized or justified by the offline checks.

At 22 Sep 15:05 SGT, user-authorized Day-2 push #33 initially registered
`running`, then exited with code 1 and no new solve. Team 63 remained at
5 VALID / 500 points. Independent
registry inspection matched the checked AMD64 image digest
`sha256:de3d5b4e19cd9147453b18b4ff7da5183a3a5ec8ad73dba7403088f105a62110`.
It was rebuilt in isolated worktree
`/Users/jeromequeck/.codex/worktrees/baseline-rebuild/incypher` on branch
`codex/baseline-sol-xhigh` from source `3a3452e`, the exact Day-1 #20 source
that earned 11 fresh practice solves by 03:25. The clean image retains that
serial 12-call solver, uses exact Sol/xhigh, and promotes eight unsolved
locally corroborated methods with required first-execution instructions.
Host suite: 359 passed/25 expected skips; official image checker 6/0/2;
restricted image suite 342 passed; all 27 packaged source hashes matched;
secret/flag audit found no Day-1 credential, private files or real flag
literal. Push #32 collected `done` at 5/47 and produced no fresh solve.
These checks and #33 registration do not establish a fresh score or active
container digest. **Next action:** passively observe a new accepted solve or
specific failure; no further push without separate authorization. The
five-minute live-instance automation was deleted at the user's request.

At 22 Sep ~13:08 SGT, public status still shows push #32 `running`, zero
penalty; Team 63 remains at 5 VALID / 500 points, last solve 11:14. The
dashboard briefly showed a solver-created Sticky Notes (#29) instance at
~13:03. Team 63's authenticated read-only instance-status API confirmed it,
but it disappeared before a separate probe could connect. No instance action,
connection or flag submission occurred. A no-flag shell probe is staged in
ignored local analysis for a later solver-created instance. **Next action:**
continue passive run/score and team-instance monitoring; only probe a current
Team 63 instance after fresh official status confirmation.

At 22 Sep 12:51 SGT, user-authorized Day-2 push #32 registered with zero
penalty and the previous 5/47 collected result. The public 12:57:08 cycle
shows it `running`, with no collected #32 result yet.
Independent registry inspection matched the exact checked AMD64 manifest
`sha256:21a96a3d09c928f802893c1ffc8cfa35be808f68cf9b2d615af5b0840701635e`.
The prior push #31 passed through transient `collecting`/`lost`/`running` public
labels before collection as `exited(1)` at 5/47. No container logs or active
digest are exposed, so the cause of exit 1 remains unproven. The public row
confirms #32 pickup but does not prove the active digest or a new accepted solve.

The #32 image selects one ranked eligible dynamic slice alongside one static
worker, with a separate client and thread-local shell; inherited `main.py`
still owns instance lifecycle and results, and only one dynamic is admitted.
Proven per-ID methods lead their static/dynamic lanes, with a single bounded
retry after three other completed challenges; unknown fresh work still gets
first attempts. Image-owned exact OpenRouter routing prefers Sol xhigh when
catalogue capability, price and durable USD85 admission permit. Only an
explicit first-call HTTP 404/429/503 can fail over to catalogue-verified Gemini
3.1 Pro Custom Tools with a fresh reservation; the original stays unresolved.
Refusals, ambiguous transport failures, timeouts and later calls do not switch
models. Local real-key content-free Gemini probes verified exact tool calls and
`reasoning: high`, not scoring or refusal behavior. The package contains 47
challenge methods (13 locally corroborated) and runtime-only scoped command
captures, not flags or private files.

Release checks: 421 host tests passed with 31 expected platform skips; 401
network-disabled non-root tests passed inside the exact read-only 2 CPU/2 GiB/
256-PID image; bundled checker passed 6/0/2; copied source hashes matched;
audit found no Day-1 secret, validation selector or match to seven local flag
candidates. `git diff --check` passed. No manual challenge instance or flag
submission was made in this task. These checks do not prove scored success.
**Next action:** passively watch status/VALID for #32 collection and fresh solves;
if it fails, obtain sanitized run logs/results before attributing a cause.
Do not spend another push on speculation. The live usage guide now says the
first three scored-day re-uploads are free, then 100 points each; the previous
rules audit's stricter sentence was corrected in [competition rules](competition-rules.md).

## Previous challenge-preparation diagnosis

Scoring diagnosis at 22 Sep ~12:22 SGT: two quick authenticated catalogue
reads found exactly five team solves: four forensics (#55–58) and one reversing
(#59), unchanged from before push #31. The public row shows #31 registered and
`running`, but does not expose the active digest, model calls, error results or
budget. A fresh-state replay of the live 42-unsolved catalogue ranked the
remaining statics #3, #4 and #13 first. After recording one unsuccessful Vault
(#95) slice, the current fresh-first policy ranked its next attempt 42nd,
behind 41 unseen challenges. This is a confirmed scheduling tradeoff, not
evidence of which live slice failed. Per first look the image permits 12 or 16
model turns with an 8-minute attempt deadline; repeating up to 42 first looks
can consume the remaining event window. No category is filtered out. The
category playbook does, however, map healthcare and blockchain to `unknown`;
the 47 packaged methods include 13 local proofs and 34 hypotheses/incomplete
routes, not runnable exploit scripts. The observed short-lived #29 instance
proves a dynamic lifecycle was reached, but no model/tool or verdict detail.
**Next action:** obtain a sanitized arena result/attempt trace or other
read-only runtime telemetry before claiming a provider, budget, tool, or
submission root cause; if asked to implement, replace the full first-pass
barrier with a bounded coverage/verified-retry mix and test it before any
separately authorized push. This turn makes no runtime change or push.

Live-support update at 22 Sep ~12:15 SGT: Push #31 registered on the public
status board at 12:01:07, with the team row still `running` and zero penalty;
that row does not reveal the active container digest. The user authorized
tracking and working on solver-created instances, but not creating instances
or manually submitting flags. One read-only team-token scan of all 39 dynamic
status endpoints found Sticky Notes (#29) live briefly; it was gone on the
next read, and a fresh full scan found no active dynamic instance. No instance
was created, connected to, renewed, destroyed or submitted to by this task.
The active five-minute `InCypher live instance support` thread heartbeat will
continue read-only identification and scoped, separate bounded work on any
solver-created instance through 16:30 SGT, staying quiet while unchanged.
**Next action:** wait for the next solver-created live instance, recheck its
status immediately before any connection, and reuse the matching local
analysis without exposing flags or target credentials.

Update at 22 Sep 12:02 SGT: user superseded the earlier no-push scope and
requested a Day-2 solver release after verification. Current candidate
`incypher-agent:throughput-local` packages the same 47 no-secret methods and
output vault, plus a fresh-first queue: all static first looks, then dynamic
first looks, then bounded retries. First looks use 12 model turns, or 16 for
locally corroborated methods; later slices use the configured 24. Deferred
challenge details now reuse trusted catalogue metadata instead of fetching
all details every pass. Exact captures remain private to their instance;
screened semantic findings alone can transfer to a new instance with the
same material and an explicit re-verification warning. The inherited serial
lifecycle still prevents simultaneous static solving and an active dynamic
instance; it permits one dynamic at a time, not concurrent static/dynamic
workers. This limitation is not claimed solved. The default durable USD85
admission ceiling remains unchanged because the live scored balance is not
confirmed. Host suite: 412 tests, 31 skips; exact AMD64 image checker 6/0/2;
restricted non-root container 392 non-entrypoint tests and root synthetic
entrypoint 8 tests; package audit found 47 references and no flag prefix or
Day-1 secret/selector. The image was pushed once to Team 63 `:latest`; the
registry independently returned the exact checked AMD64 manifest digest
`sha256:13d9e3ee6deca1213c8318f51ded163eaf7782785de99c7407d53558df0f515e`.
Board read at 11:57 showed Team 63 at 5 VALID / 500 points, last solve 11:14,
zero recorded penalty. Immediately after push the status page still showed
Team 63's earlier push #30; pickup and new scoring are not yet verified.
**Next action:** observe the next passive status/score cycle, establish whether
push #31 is registered and its penalty, and compare fresh VALID without
claiming the tested image solved anything yet.

Previous scope (superseded for release): inspect the published challenges and attached handouts locally; do not
launch dynamic instances, submit flags, or publish/push any image. The ignored
`private/challenges-2026-09-22/manifest.json` indexes 47 exposed challenge detail
records and 19 attachments with hashes. Some publisher descriptions are sparse or
truncated; the archive cannot supply missing instance-only behavior. Ignored
`solves.md` keeps candidate values and uncertainty; never copy it into an image,
tracked playbook, results, or release log.

`agent_ext/challenge_methods.py` gives all 47 trusted numeric IDs a no-secret
method or explicit insufficiency note. The image's sanitized
`challenge_reference/index.json` provides names, categories and attachment
hashes but no raw outputs or candidate values. Static artifact analysis yielded six
candidates (BadLE's APK parser is corroborated); BadLE Hard and Rolling Thunder
remain unresolved. The #4 APK is identical to #3's oximeter app, so cannot
verify the contradictory CGM field claim. Three reversing inputs were accepted
by their provided local binaries. Vault (#95) and Relay
(#96) have locally verified access paths, with reproducible ignored scripts;
their binary fallback output is not an arena flag. Sticky Notes (#29) and
Spool (#123) have locally reproduced end-to-end chains; Spool's was verified
with a synthetic environment value, and its AUDIT recovery token is a decoy.
The remaining
dynamic cases are hypotheses only, not live solves. No instance or submission
was made for this task.

Final local-only Day-2 image `incypher-agent:challenge-methods-local` has AMD64
digest `sha256:c96797d2fbd54e8da8b8e5cacd57ace641d5b1f0d5b46c162fa6f0894d7e6305`.
Its checker passed 6/0/2 expected warnings; exact packaged agent files were
scanned against all locally derived candidate strings with no matches. The
host offline suite passed 407 tests (31 expected platform skips). In a
network-disabled, read-only, 2 CPU/2 GiB container, 399 non-entrypoint tests
passed as non-root with ResourceWarnings fatal; 8 entrypoint tests passed
separately using the packaged executable and an executable synthetic-fixture
tmpfs. These checks do not prove live scoring. The image was not pushed.

`agent_ext/output_vault.py` now keeps private, exact-material/instance-scoped,
bounded shell results on `/work`; Brain can request a prior result by handle
without rerunning it. This store is runtime-only, outside the image and official
results; [runtime-state.md](runtime-state.md) owns its retention/bounds. The
local Day-2 candidate is for validation only, not publication. **Next action:**
keep the unresolved BadLE Hard and Rolling Thunder reasoning separate from
verified methods; scrutinize heap-chain portability only against supplied
handouts. Any live dynamic
validation requires a later change of user scope and a supplied instance.

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
On that exact clean runtime, B36b used a two-call unsolved reversing slice
with five safe records, then a fresh admitted slice solved in eight more calls;
B37 crypto and B38 network also passed fresh one-shot local cases. All three
lanes had one correct/zero wrong submission and zero unresolved spend, but
none exercised the four still-unaccepted live challenges. The released
adaptive completion-cap change allows 8,192 instead of 4,096 tokens only
for an exact, priced, ceiling-verified OpenRouter model while projected
spend remains behind target. Its 382-test host suite (25 expected skips),
exact clean Day-2 image
`sha256:8351f6f47dff7174603ce68a550b606dd2c941d39a5ba51f3791af19760ca53c`
checker 6/0/2 and 376 restricted-container tests pass. A content-free local
Luna probe sent one real 8,192/high request and settled USD 0.0000436; this
proves compatibility/accounting, not better solve quality. Independent
Standards and Spec reviews passed at `e60a938` (two optional maintainability
suggestions and a documentation-scope note); PR #25 CI passed and merged as
`c09d3f8`. The matching Day-1 image
`sha256:254f0e4dfcaf6b67fd31ced8f4983695409f55a2bda23634d9a21401674c31da`
passed checker 6/0/2 and contains only the five intended model/budget key
names, with no validation selector. The clean Day-2 image has neither.
It was pushed as #26 at 05:34:33; independent remote inspection matched the
exact digest, and the board registered RUNNING at 05:35. Registration is not
proof that the new digest was picked up or solved a challenge.
A fresh local #26 Day-1 adaptive two-slice P2 run B40d passed with 11 real
8,192/high calls, ten tools, one correct/zero wrong submission and USD0.00594319
measured. Earlier short B40 guessed incorrectly before a later correct answer;
B40b/c were consumed by private evaluator errors, not production failures.
The published #27 image passed a new fresh local three-lane B41 battery:
crypto 4/3, network 12/12, reversing 12/11 model/tool calls, each with one
correct/zero wrong submission and zero unresolved spend; aggregate USD0.02392435.
Neither local battery proves the four remaining live solves. The public 06:10
cycle remained RUNNING at 11/15, 2,250 VALID and penalty 0 before push #28.
The provider's current-key aggregate usage at 05:48 was USD3.47254776/20;
since #26 embedded a USD19 cap, a fresh ledger after replacement could otherwise
outlast the remaining provider balance. PR #27 now allows only downward durable
budget-cap migration; its 385-test host suite (25 expected skips), exact
clean Day-2 restricted 379-test suite and both image
checkers 6/0/2 pass. Clean Day-2
`sha256:90b612610530fe9c822dcf66f2142a727fc760477b8b3c50b98264b4e5a867b8`
has no secret/selector; matching Day-1
`sha256:dcf1b0a74e962252af227067182bf2d12594dc614905bc4ae764d4696c2620a8`
has only the five intended names and a USD15 cap. The independent Standards
finding about a stale next action was closed at `e6a0705`; Spec and CI passed,
and PR #27 merged as `01cf968`.
The Day-1 image was pushed at 05:51:38 as #27; the remote digest independently
matched and the board registered RUNNING with no active digest or new VALID
proof. The clean Day-2 image remains local. The ignored local `.env` numeric
budget was lowered to USD15, then USD14.50 for the controlled config-only
replacement below; no credential value changed. At the 06:10 cycle, #27 was
still RUNNING at 11/15, 2,250 VALID, rank 2 and penalty 0, with the last own
acceptance at 03:25. The provider key's aggregate usage increased from
USD3.66412488 at 05:59 to USD3.85974909 at 06:10 of its USD20 tryout
limit; this cannot attribute which digest made the calls. The user-requested
Day-1 relaunch #28 was pushed at 06:10:52 after two flat cycles. Its exact
AMD64 digest
`sha256:ce015d7918b56d4c483cccea734dc10b5f8315528febb9fdaf28c7c7c183ce65`
independently matched registry `latest`; packaged runtime files have the same
aggregate hash as #27, while the embedded cap is USD14.50. Checker 6/0/2,
five intended config names and no validation selector passed. The status
board registered #28 RUNNING by 06:11:38, still 11/15 and penalty 0. This
is registration, not proof of active digest, new acceptance or a quality gain;
the 06:15, 06:20 and 06:25 cycles also stayed RUNNING at 11/15, 2,250 VALID,
rank 2 and penalty 0. The last own acceptance remains 03:25. Aggregate key
usage was USD4.12029417/20 at 06:20, but cannot attribute the active digest.
PR #29 corrected the setup's downward-cap wording and recorded this release;
CI passed and it merged as `f54e503`. The merged `main` passed the complete
385-test host suite with 25 expected platform skips at 06:16. Both Day-1
#28 and clean Day-2 `sha256:90b612610530fe9c822dcf66f2142a727fc760477b8b3c50b98264b4e5a867b8`
share exact packaged solver-file hash `0f86599b…ff48`, while Day 2 contains
neither the embedded key nor a validation selector. At the 06:30 feature
freeze, push #28 remained RUNNING with 11/15, 2,250 VALID, rank 3 and penalty
0, last own acceptance 03:25. Aggregate provider-key usage was
USD4.33725098/20 at 06:30; this includes local and any arena calls and does
not prove the active digest. No new solve or hard failure is reported. Feature
work is frozen; only small verified configuration fixes remain in scope.
The 15/15 target and independent current-solver acceptance across all 15
remain unproven, so this build goal is not complete. The checked #28 Day-1
image remains published and the clean Day-2 image stays local, not submitted.
At 06:34:53, the public [runtime dashboard](https://hackathonlive.in-cypher.com/dashboard)
reported Team 63's `agent-63` container started at 06:15:05, the first cycle
after push #28, with the `team-63/agent:latest` image tag, 2 allotted CPUs
and about 43 MB used. This strongly supports replacement pickup, but the
feed omits a content digest; exact #28 execution remains an inference. The
06:35 board still showed RUNNING, 11/15, 2,250 VALID, rank 3, penalty 0;
provider-key aggregate usage was USD4.39010870/20 at 06:33. The dashboard
sample alone cannot establish active solving or a new acceptance.
At 06:41 the dashboard showed Team 63's agent using CPU with exactly one
dynamic challenge environment, opened at 06:40:59; by 06:43 that environment
was gone and the agent was still using CPU. These read-only samples support
an active, serial attempt/release lifecycle, not a solved challenge or exact
image digest. The 06:45 public cycle stayed RUNNING at 11/15, 2,250 VALID,
rank 3 and penalty 0. Do not interrupt the live instance on a flat score.
At the 08:00 cycle, push #28 was still RUNNING at 11/15, 2,250 VALID,
rank 4 and penalty 0; the last own credited solve remained 03:25. A public
dashboard sample at 08:03 still showed the same Team 63 container start
(06:15:05) and one attached dynamic environment opened at 08:02:43. The
current-key aggregate OpenRouter usage was USD6.35921694/20 at 08:02,
leaving USD13.64078306. This balance is not the running process's ledger,
and the public board still does not expose its digest. Keep the live agent
running, monitor score and budget, and consider only a measured, verified
configuration fix after the 06:30 feature freeze; 15/15 remains unproven.
At 08:05 the user explicitly reopened feature work to improve model quality
before 10:00 and requested a checked Day-1 test release. A local candidate
routes image-owned OpenRouter Luna slices at xhigh, then price-gated Sol after
two prior unsolved slices; it does not increase challenge lifecycle concurrency
or override explicit organiser models. Two content-free real API probes
accepted xhigh/tool requests with exact Luna and Sol identities; this is
compatibility, not solve quality. The earlier Rapido 15/15 run was Daybreak/Luna,
not a fresh Sol 15/15 result. Keep push #28 running until a reviewed candidate
image is ready; then account for current provider balance before replacement.
PR #34 merged the Sol retry route at `e17d086`: 391 host tests passed
(25 platform skips), 384 non-entrypoint restricted-container tests passed,
and both exact pre-key-change images passed checker 6/0/2. The old OpenRouter
key then returned 401 `API key expired` despite a prior USD13.16 remaining
balance. The user's replacement key was valid at 08:36 with USD2.61 available;
the rebuilt private Day-1 image `sha256:7daf7c6528876f70b75cb2b3df1452e1e11500e7c8f179f0491770ce4158c128`
has a USD2.30 cap and passed checker 6/0/2. Its official push preflight
passed, but upload failed on registry EOF. The public board still showed #28
RUNNING at 11/15 around 08:32; no new image was registered. Retain this exact
checked tag for retry when the registry responds. A separate small offline
analysis-tools candidate now adds pydicom and bounded local-PCAP summaries;
its Docker image/canaries are local only, not a live solve or release.
The replacement key's content-free Sol/xhigh tool probe succeeded, but showed
`is_byok=true`, `usage.cost=0` and upstream inference cost USD0.00054.
OpenRouter reports this key's `include_byok_in_limit=false`: its USD2.61
displayed limit does not cap upstream provider billing. A local correction
counts upstream spend and reserves 3× catalogue cost, with absent upstream
usage left unresolved. At about 08:48 the user replaced that key again: the
current key reports a USD2.50 limit with `include_byok_in_limit=true`, so the
BYOK spend is included in its key limit. The internal cap remains USD2.30.
No prior Day-1 image was safe to publish with this key.
PR #35 (`f2b6051`) merged the BYOK correction and two offline-analysis
packages after independent reviews, CI, a 395-test host suite (27 expected
skips), 388 restricted non-entrypoint tests, and a 6/0/2 clean-image checker.
The exact private Day-1 image
`sha256:701612f7cfded49db5993dfafdb92f8cfd359b770b9773cfa73f109db3e34de6`
was built with the current key and USD2.30 cap, passed checker 6/0/2 and
official push preflight, and was uploaded at 08:57:12 after the user switched
this Mac to a hotspot. An independent remote manifest read matched that digest.
[Status](https://hackathonlive.in-cypher.com/status) and
[scores](https://hackathonlive.in-cypher.com/scores) registered push #29 as
RUNNING at 11/15, 2,250 VALID, penalty 0. The public dashboard showed a
Team 63 agent container restart at 09:00:07, consistent with pickup, but its
image field is only the `latest` tag; it does not expose an active digest.
No new solve is yet verified. Next: leave the new agent autonomous, watch the
09:05+ scoring cycles and key usage, and investigate only a specific failure;
do not conflate registration or synthetic tool canaries with live acceptance.

At 09:59 SGT the clean Day-2 Sol-first/polling image was pushed; independent
registry inspection matched `sha256:544fd1741c080e0c1e66bfb668e3f9aa6ac850bec0e130d419604f32c69b9aa2`.
Its exact checker passed 6/0/2. The public 10:08 status cycle still lists push
#30 (09:39:56) rather than this final upload, and reports Team 63 RUNNING; do
not attribute that process to the final digest. At 10:13 the public scored
standings show **four fresh arena-origin solves**, 400 VALID/NET, penalty 0,
rank 2, last own solve 10:11. This is real Day-2 scoring, but not attribution
to a particular image. The user explicitly forbids further pushes now that
scoring has begun. Host offline suite is not yet green after the catalogue
polling change: two old one-shot fake-harness tests needed explicit selectors,
and a third recovery test was interrupted while looping; its one-shot fixture
is being corrected. Continue local verification and passive monitoring only.

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
  Through the 05:30 cycle push #25 remained RUNNING at 11/15, 2,250 VALID,
  rank 2 and penalty 0. No new own event or active digest is exposed.
  PR #25 merged as `c09d3f8`; checked Day-1
  `sha256:254f0e4dfcaf6b67fd31ced8f4983695409f55a2bda23634d9a21401674c31da`
  was pushed at 05:34:33 as #26 and independently matched registry `latest`.
  At the 05:35 cycle the board registered #26 RUNNING, 11/15 and 2,250 VALID,
  penalty 0, but exposed no active image identity or fresh solve. The 15/15
  live gate stays open.
  PR #27 merged as `01cf968`; checked Day-1
  `sha256:dcf1b0a74e962252af227067182bf2d12594dc614905bc4ae764d4696c2620a8`
  was pushed as #27 at 05:51:38. Independent remote inspection matched;
  the board immediately registered #27 RUNNING, while the 05:50 cycle was
  still 11/15, 2,250 VALID, rank 2, penalty 0. Active digest and pickup
  remain unexposed. At the 05:55 cycle scores briefly showed COLLECTING while
  status showed RUNNING, then both reported RUNNING by 05:55:25 with no new
  VALID event or hard failure. This transient alone does not justify rollback.
  A checked config-only Day-1 replacement `sha256:ce015d7918b56d4c483cccea734dc10b5f8315528febb9fdaf28c7c7c183ce65`
  with the same runtime code and USD14.50 cap was pushed at 06:10:52 as #28;
  remote manifest matched and public status registered RUNNING by 06:11:38.
  The 06:30 cycle remains RUNNING at 11/15, rank 3, with no active digest exposed. Preserve
  #20 as the fresh-scoring fallback only if an actual hard failure appears.
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

The [build brief](solver-build/brief.md) retains historical release gates and
ignored `private/solver-build-20260921/{state,plan,experiments}.md` retains its
older experiments. Current scope is the local-only challenge preparation above:

1. Verify the changed runtime, scoped output retention, and challenge method
   selection with the host offline suite, a local AMD64 image checker, and the
   relevant restricted-container suite. Do not push or tag the arena registry.
2. Keep static ambiguities (#4, #13) explicit. A new parser or cipher proof
   belongs in the ignored archive first; only the no-secret method goes into
   tracked code.
3. Extend the offline heap exploits (#29, #123) where possible. All other dynamic
   hypotheses await an inherited instance under a later authorization; never
   start one for this task or submit candidate values.

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

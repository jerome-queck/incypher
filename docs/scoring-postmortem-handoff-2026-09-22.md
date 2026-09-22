# Team 63 scored-run handoff — 22 September 2026

Six accepted solves prove the core submission path worked. An earlier image has
one reproduced pre-model blocker on a real challenge attachment. Other
reproduced weaknesses can waste attempts, but missing arena traces prevent a
per-challenge explanation for the 41 misses.

## Objective and source

Explain the six accepted solves and identify supported causes of missed work.
The runtime source is Git `main` at `fefe49bab8de7d2577aee0338a3359357f36da21`.
Thirty-one checked code/reference files match the local #35 image
`sha256:8896c31d913226cc3c14f768e1219fbe332f627b625e740132150938ebb9f2f6`.
#34 is `sha256:93443207dcda6c47516ac0573f54e1e48e5507313330fbbb8ad22a7dc22727a8`;
it has the earlier `runtime_state.py`. This Git push did not publish another
arena image. The active ownership path remains [entrypoint → wrapper → inherited
harness → Brain](interfaces.md#active-boundary); the inherited harness owns
challenge lifecycles, submissions and results.

## Observed outcome

At 18:17 SGT, the public [scores](https://hackathonlive.in-cypher.com/scores)
showed rank 14, six solves, 750 VALID, 200 penalty and 550 NET. Public
[status](https://hackathonlive.in-cypher.com/status) showed push #35 at 15:57:05,
`6/47`, and `stopped: competition closed`. The last accepted solve was BadLE at
15:36. Four early forensics solves and one reversing solve preceded it; the
supplied postmortem's team-history inspection found no accepted crypto, web,
pwn, network, misc or blockchain solve. Six accepted submissions establish
that the submission path worked. Re-upload penalties
lowered NET; they did not reduce the solve count.

`6/47` does **not** mean the model attempted all 47. The wrapper returns a
[deferred result](../arena_main.py) for catalogue entries it did not admit on
that pass. The public board exposes no per-challenge model, tool, budget,
verdict or active-image trace.

## Supported causes and limits

| Finding | Evidence | What it explains |
| --- | --- | --- |
| A large attachment stopped challenge #3 before any model call in the exact #32 image. | A read-only replay failed at the 64 MiB material-hash bound; the [#34 change](../agent_ext/runtime_context.py) reached a fake model call on the same file. See [release record](context.md#current-release-and-next-action). | One proven pre-model blocker in an earlier release. #34 removed it; BadLE later scored. The arena trace does not prove this was the sole reason for that solve. |
| Earlier fresh-first scheduling could bury a promising retry. | The recorded local catalogue replay ranked Vault #95's second slice 42nd after one miss. First looks had 12 or 16 model turns and an eight-minute ceiling. See [release diagnosis](context.md#previous-challenge-preparation-diagnosis) and [current slice policy](../arena_main.py). | A concrete opportunity cost under a finite event window, not proof of which live attempts ran. #35 promoted proven high-value work and selected Relay #96 at about 16:00, but the board showed no later solve. |
| Several shell and progress defects remain in #34/#35. | Exact-image synthetic probes reproduced a blocked re-read after a generated file changed, deduplication of a command refused before execution, a 12 KB output kill, and nonzero error results counted as progress. See [wrapper](../arena_main.py), [state](../agent_ext/runtime_state.py) and [shell](../agent_ext/managed_shell.py). | These can waste attempts or prevent recovery. No final-run command trace ties one to a specific missed challenge. #34/#35's [private output vault](../agent_ext/output_vault.py) restores bounded prior outputs but does not fix changed-input deduplication. |
| Some semantic findings remain unrecordable. | The [finding validator](../agent_ext/runtime_context.py) rejects benign authentication, socket-framing and long numeric examples in synthetic probes. | Possible loss of useful cross-slice state. #34/#35 already transfer validated cross-instance semantic findings, so the older blanket claim that all such state disappears is obsolete. |
| Unknown model cost can stop the whole coordinator. | With no catalogue price or response cost, [policy](../brain.py) reserves $1 per call; the [ledger](../agent_ext/model_gateway.py) retains 85 unknown-cost reservations and refuses call 86 in an offline probe. | A conditional stop mechanism. Arena #35 price responses, provider spend and ledger are unavailable, so this is **not** an established scored-run cause. |
| Most packaged methods were unproven in the arena. | The [reference index](../challenge_reference/README.md) lists 47 method entries but only 13 local proofs; many others are hypotheses. The real-model replay below covers five known solved file challenges and two unresolved file challenges, not the full catalogue. | Packaged coverage and structural checks cannot establish reliable solutions for the other challenges. |

The generic `flag{...}` wording in one challenge description is not an
established bug: the [official guide](https://hackathon.in-cypher.com/how-to-play)
specifies `INCYPHER{…}`, which [Brain](../brain.py) requires. The fixed-inspection
snapshot test failed intermittently in the supplied postmortem's WSL run but
passed 12/12 in the #35 Linux image here; that worker is outside the active
managed-shell path. There is no evidence that the arena's 2 GB limit killed the
solver. Pushes #31 and #33 exited with code 1, but their causes remain unknown.

## Local real-model endurance replay, 19:24 SGT

Using the personal OpenRouter key, an isolated AMD64 Docker runner exercised the
packaged `Brain`, scoped managed shell, persistent runtime state, model ledger,
answer callback and later-slice memory under the arena's 2 CPU/2 GiB/256 PID,
read-only-root limits. It mounted only archived file attachments for each case;
answer candidates and challenge details were streamed into the evaluator, never
mounted for the shell. There was no CTF platform call, dynamic instance, arena
submission or registry push. Sanitized private results are in ignored local
`private/real-model-audit-20260922/full-file-work-v2/` and
`private/real-model-audit-20260922/full-file-baseline/`.

| Exact image | Archived known file challenges #55–59 | Harder file replay | Model turns / measured cost |
| --- | --- | --- | --- |
| #35 `8896c31d…` | **5/5 correct local answers**, one submission each; 24 model and 23 tool calls | #4: 10-turn first slice, then 2-turn retry; it submitted one candidate, but the local callback had no true answer and rejected every candidate. #13: 5-turn first slice, then full 16-turn/17-tool retry without a candidate. | 57 attempted model turns across nine slices, 54 settled calls, **$0.49343848** measured, $0 estimated/unresolved; ~430 seconds of solver time. |
| #34 `93443207…` | **5/5 correct local answers**, one submission each; 26 model and 26 tool calls | #13: 9 attempted turns, no candidate. This is not a matched hard-case comparison because #35 ran #4 first and later retried #13. | 35 attempted model turns across six slices, **$0.4486036** measured, $0 estimated/unresolved; ~351 seconds of solver time. |

The replay used a **$0.60 ledger cap per image**. On #35, #4 and the first
#13 slice stopped when the next reservation would exceed remaining headroom;
#4's retry did the same. On #34, #13 stopped for that reason. These are imposed
test-budget stops, not evidence of arena budget exhaustion. #35's second #13
slice used its full 16-turn limit without a submission. Its 16 retained memory
records and 17 tool calls show sustained work, not a solve. The earlier
file-backed analysis found the eight supplied XOR samples insufficient to
verify a simple generator; this replay did not resolve that ambiguity.

The first replay setup failed before model work because its reserve was below
the image's accepted minimum. After that correction, one model request failed
because the local Colima DNS resolver was unavailable and left an unresolved
$0.05 reservation. A fresh isolated replay pinned the provider's current
host resolution and completed with **zero** unresolved cost. This is a local
runner fault; no arena DNS inference follows. Both images solved all five
known tasks, so this small replay does not show a solve-rate improvement from
#34 to #35. The replay directly invokes `Brain` with trusted local contexts;
it does not test inherited CTF enumeration, live instance lifecycles or the
arena results writer.

## Unresolved evidence

The examined local `private/` tree has no final arena `results.json`, sanitized
stdout/stderr, or arena-owned runtime/budget SQLite backup. Public pages do not
identify the active digest. We therefore cannot assign a failure class to each
of the 41 unsolved challenges or say whether budget, provider behavior, shell
failures, slice exhaustion, candidate quality or instance lifetime dominated.

## Validation and next action

- Host offline suite: **422 passed, 31 skipped**. Exact #35 image checker:
  **6 passed, 0 failed, 2 expected warnings**. All 31 checked code/reference files
  matched the checked-out runtime; Git `main` CI for `fefe49b` passed. Synthetic
  probes ran on the exact #35 image and the prior `933c1e8` baseline.
- Ran: bounded real-model replay of archived file challenges on exact #34/#35
  images, as detailed above. Not run: live arena harness/instance replay or
  inspection of actual arena logs and ledgers. Local correctness is not fresh score.
- Next: obtain sanitized #34/#35 per-challenge outcomes and stdout/stderr,
  consistent read-only copies of `runtime-state.sqlite3` and
  `model-budget.sqlite3` including WAL state, and actual model usage metadata.
  Classify each admitted slice by model calls, tool outcomes, candidate verdict,
  elapsed time and stop reason. Then compare the exact image against one narrow
  recovery change on matched isolated tasks and a fixed cost/time budget.

Owned paths for this handoff: this document and [context.md](context.md).
Shared runtime seams are unchanged by the handoff.

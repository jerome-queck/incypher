# Solver build research

Read the matching section when deciding a workstream in [brief.md](brief.md).
Checked **21 Sep 2026**. Observations below are evidence; proposed comparisons are
open experiments, not selected implementations. Recheck provider and platform facts
at build-session startup. No paid request, live solve or registry push was made for
this research.

## Baseline and reference identity

The supplied [incypher URL](https://github.com/jerome-queck/incypher) is this minimal
submission repository. The seven-run report instead identifies
[incypher-rapido](https://github.com/jerome-queck/incypher-rapido). Its local checkout is
`/Volumes/Working/090 Temporary Checkouts/incypher-rapido`, observed HEAD
`ff99cf0ea6e95b2604755f30030c505164d6c58c`; R7 used
`a46526e1de02ebb4f4d9e4eb8423c0c47e5531ac`. Compare explicit revisions rather than
silently treating the two repos or current HEAD and R7 as interchangeable.

Read-only HTTP refresh around **21:29 SGT** found the public board unchanged: rank 8,
VALID 650, SCORE 650, five solves; Team 63 status 5/15, 12 pushes, `done`, penalty 0,
last push 21 Sep 17:43:14. This is cumulative practice evidence, not a current image
identity. [Scores](https://hackathonlive.in-cypher.com/scores),
[status](https://hackathonlive.in-cypher.com/status).

The [usage page](https://hackathonlive.in-cypher.com/usage) still describes a compatible
Chat Completions endpoint with injected Day-2 identity and no container wall-clock
cutoff. The audited rules' sandbox remains unchanged. No numerical image-size cap was
found in that page; registry/storage constraints need measurement or fresh authority.
The event finish remains distinct from container lifetime. Other conflicts stay in
[competition-rules.md](../competition-rules.md#conflicts-and-unresolved-details).

At source `92cb6f8`, `brain.py` synchronously calls model, shell and submission;
`_chat` returns only the message, discarding response usage/model metadata. Requests
hard-code `temperature: 0.2`, `max_tokens: 4096` and a 180-second HTTP timeout. There is
no reasoning-effort request field. Full messages accumulate; shell output is truncated
only after the callback returns. Optional modules are under `agent_ext/`, not the
repo root. Their activation limits are described in [context.md](../context.md).

**Implication:** changing prompts or `.env` alone cannot deliver spending control,
reasoning-high selection, aggregate resource bounds or durable asynchronous recovery.
First establish the trusted production seams and measure a runnable baseline.

## Seven-run audit: useful evidence, bounded conclusions

Local source: `/Users/jeromequeck/Downloads/incypher-rapido-seven-run-posthoc-score-and-audit-20260919.md`.
SHA-256: `0aad0e4b159ead60a543460467c7cf97604ab2e1331e4d2bd80e51bf1f8b7ad4`.
It is a sanitized report; preserve raw archives privately. Its executive comparison,
R6/R7 detailed records and final “Sources and limits” distinguish these axes:

| Observation | Consequence for experiments |
| --- | --- |
| R7 achieved 15/15 post-run static-answer/dynamic-method validation over 330 minutes; board C/A/W = 0/42/0 | Strong source-method evidence; zero fresh `correct` verdicts in that run; not live arena 15/15 proof |
| R7: 610 attempts, 17,347 tool calls; 558 attempts requested Daybreak/xhigh, 52 Luna/xhigh or max | Not a Luna-high-only baseline; provider execution/fallback was not independently attested |
| R7 sampled peak 11.989 CPU cores, 3.78 GiB RAM, 127 PIDs; R6 peak RAM 4.72 GiB | Direct copying fails to establish fit within 2 CPUs/2 GB; measure aggregate container pressure |
| R7 had 935 failed observations, 794 argument-stage failures; 440 unsolved attempts | Tool schemas, repair and avoiding unproductive repetition deserve measured attention |
| R6 ended after a catalogue HTTP 502; R7 followed a read-only 5xx retry fix | Recovery must include orchestration/platform reads, not just individual tools |
| R7 retained 112,324,718 artifact bytes; 16,344 carried memory records over 610 projections | Measure retrieval usefulness, prompt growth and retention cost; record count is not memory quality |
| One R4 `already_solved` candidate was contradicted by the static oracle | Account-level solved state cannot validate an arbitrary candidate |

The report contains no comparable dollar total establishing these methods fit $100.
Its final recommendation is a harder representative benchmark rather than another
long run on easy fixtures. Inspect only relevant Rapido interfaces/changes and port
small justified mechanisms; architecture selection remains open.

## Provider capability and cost accounting

OpenRouter's documented `GET /api/v1/key` returns current-key usage and limit metadata,
including `limit_remaining`. Null/unbounded limits, resets, account sharing and BYOK
semantics prevent equating that field with an event allocation. A real key's access
and the organiser provider remain untested.
[Current-key API](https://openrouter.ai/docs/api/api-reference/api-keys/get-current-key).

OpenRouter documents response `usage` with tokens, cost, reasoning and cache details;
streaming reports usage at the end. It also supports generation-ID accounting lookups.
Missing final usage after timeout can therefore leave an incurred cost unresolved.
Use response costs and later reconciliation without double-counting; preserve an
in-flight reservation until the accounting policy can settle it.
[Usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).

The public model catalog exposes IDs, pricing, context and supported parameters.
An unauthenticated catalog read during this audit returned `openai/gpt-5.6-luna`, with
`tools`, `reasoning` and `reasoning_effort`, but no `temperature` in its supported list.
Listed prompt/output rates were $0.20/$1.20 per million tokens, with separate cache
rates and long-input overrides. These are a dated development observation, not fixed
competition pricing or evidence that the private key can invoke the model.
[Models API](https://openrouter.ai/docs/api/api-reference/models/list-all-models-and-their-properties).

OpenAI's [Luna model page](https://developers.openai.com/api/docs/models/gpt-5.6-luna)
lists high reasoning and function calling. OpenRouter documents a provider-normalized
`reasoning` request object; verify the actual request/response behavior before claiming
Luna high. Reasoning output consumes budget even when hidden from the visible answer.
[Reasoning parameters](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).

**Questions to decide:** what authoritative event meter exists; how to distinguish
measured/estimated spend; how much to reserve for unsettled calls, verification and
recovery; how to infer a conservative cost bound with unknown pricing; when to adjust
effort, concurrency or attempt allocation; and how to detect over/underspending by
the soft horizon. Test unavailable metering, historical key spend, delayed usage,
provider errors, simultaneous admissions, restart and exhaustion. An unrecognized
provider must remain usable without relying on OpenRouter-only fields or endpoints.

## Weak-model instructions and efficient tools

Official [Sol prompting guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.6#prompting-best-practices)
recommends lean prompts, stating each instruction once, concise task-relevant tool
descriptions, explicit autonomy and evaluation after pruning. It emphasizes preserving
required evidence despite short output. Its internal improvements are directional,
not predicted CTF gains. Apply the existing [model guidance](../model-guidance.md)
and the invoked writing-for-agents skill; compare one changed prompt/tool group at a
time on matched tasks, then validate the combined system.

[EnIGMA](https://enigma-agent.github.io/) investigates interactive debugger/server
interfaces for CTF agents. Its published results support evaluating interaction design,
not assuming a large specialist swarm is necessary or affordable. The associated
[paper](https://arxiv.org/abs/2409.16165) and
[code](https://github.com/SWE-agent/SWE-agent/tree/v0.7) are mechanism references.
Candidate experiment: shell-only baseline versus bounded stateful interactions with
compact observations, measuring solve quality, calls, cost and process cleanup.

[Cybench](https://cybench.github.io/) provides 40 tasks from four competitions and
distinguishes unguided from subtask-guided evaluation. Its
[runner documentation](https://github.com/andyzorigin/cybench#running-a-single-task)
allows bounded iterations/input/output and records run results. Use a selected,
reproducible harder set that can run locally; guided progress is diagnostic evidence,
not autonomous full-solve proof. Benchmark infrastructure may have different resource
needs from the candidate solver; keep the solver's arena limits in force.

**Open comparisons:** one model with deterministic scheduling versus LLM delegation;
on-demand skill retrieval versus brief category prompts; deterministic tool summaries
versus LLM summaries; selective evidence retrieval versus replayed history; asynchronous
tool handles versus multiple fully independent model conversations. Waiting overlap
saves wall time only when another useful job exists; duplicate prompts/calls can raise
spend. Async application orchestration does not require a provider-native subagent API.
Measure rather than assuming native OpenAI features exist on the arena endpoint.

## Public CTF playbook sources

Inspect a bounded category-representative sample, then extract general recognition,
diagnosis and verification guidance in original wording. Keep source/commit attribution
and reuse terms with each derived asset. Keep downloaded corpora outside the runtime
image. Historical challenge addresses do not authorize contact; reproduce locally.

Verified source trees:

- [GreyCTF 2026](https://github.com/NUSGreyhats/greyctf26-challs-public/tree/48823817e313df0ed74ba1b24d16e9fe793ab45e),
  with qualifier/final source, solver files and selected explicit writeups.
- [SekaiCTF 2024](https://github.com/project-sekai-ctf/sekaictf-2024/tree/e7c9183860a846dd2c4e0d1fd5d5a1fe468e1244),
  with categories, difficulty/solve metadata, source and solutions. Its README declares
  separate code and non-code licenses; inspect applicable terms before copying assets.

Sampled examples establish why playbooks need discriminating checks and prerequisites:

| Sample read | Transferable lesson to evaluate |
| --- | --- |
| [Grey Chiaroscuro](https://github.com/NUSGreyhats/greyctf26-challs-public/blob/48823817e313df0ed74ba1b24d16e9fe793ab45e/quals/forensics/Chiaroscuro/solve/WRITEUP.md) | Metadata and representation matter; a failed magnitude/LSB investigation need not justify repeating it. Record the eliminated hypothesis and inspect a different signal property. |
| [Grey AE-no-S](https://github.com/NUSGreyhats/greyctf26-challs-public/blob/48823817e313df0ed74ba1b24d16e9fe793ab45e/quals/ezpz/AE-no-S/solve/WRITEUP.md) | Identify algebraic structure before brute force; verify dimensions, bit order, rank and padding. Compare a small exact helper with the dependency cost of a large algebra package. |
| [Sekai Crack Me](https://github.com/project-sekai-ctf/sekaictf-2024/blob/e7c9183860a846dd2c4e0d1fd5d5a1fe468e1244/reverse/crack-me/solution/README.md) | Sampled APK/decompilation portion: identify the implementation format, then search for application logic rather than loading hundreds of library files into context. |
| [Sekai lookup](https://github.com/project-sekai-ctf/sekaictf-2024/blob/e7c9183860a846dd2c4e0d1fd5d5a1fe468e1244/web/lookup/solution/README.md) | Parser differences and dependency/runtime versions are concrete prerequisites; generic payload lists miss the required chain. |

This sample is not a complete specialist library. Expand to binary exploitation,
protocols, reverse engineering, crypto, web and archive/forensics according to observed
gaps. Compare guidance using similar **unseen** local tasks or semantics-preserving
variants; a solved public example does not demonstrate generalization.

## Integration questions the build session must settle

| Concern | Options worth comparing | Decisive observation |
| --- | --- | --- |
| Trusted scheduling seam | Narrow harness adapter; structured callback bridge; existing optional controller | Lifecycle ownership and production reachability demonstrated with the fresh base |
| Memory | Existing SQLite helpers; bounded artifact index and selective excerpts; compaction plus provenance | Useful resume without stale evidence, repeated work, RAM growth or cross-challenge contamination |
| Admission | Static reservations; measured feedback; mixed light/heavy lanes | Aggregate sandbox headroom maintained while useful throughput rises |
| Recovery | Per-operation deadlines; worker supervision; separate liveness/progress watchdog | Fault injection recovers without killing productive slow work or replaying effects |
| Queue policy | Coverage-first; expected value/cost when calibrated; progress and aging | More valid points per cost/time without permanently starving hard tasks |
| Tools | Existing base inventory; small tested helpers; selected additional packages | New solves or fewer failed calls justify image/runtime footprint |

These options can combine. The acceptance contract, source provenance and measured
outcomes constrain the choice; this research does not select the architecture.

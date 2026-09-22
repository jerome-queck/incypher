# Competition rules delta audit — 22 September 2026

Retrieved **2026-09-22 09:03–09:05 SGT (UTC+08:00)**. Read-only review of the
official public submission, usage, status, scores, dashboard and CTF platform pages.
No form was submitted, registry queried, image pushed, live challenge solved or active
image digest inferred.

## Outcome

The [live submission page](https://hackathonlive.in-cypher.com/) explicitly announces
**two rules changed for the scored day**:

1. Only flags submitted through the arena-issued `agent-<team id>` account count toward
   the ranked total. Manual/member-account submissions remain visible in `SCORE` but add
   nothing to `VALID` or `NET`.
2. OpenRouter is the only LLM provider reachable from the arena, effective “starting
   now.” During the pre-scored period teams must bring an OpenRouter key and use
   `https://openrouter.ai/api/v1`; during scoring the organisers inject and override
   `LLM_BASE_URL` and `LLM_API_KEY`. `LLM_MODEL` remains image-owned and must name a
   model that endpoint serves.

The live score clock also says the competition is **11:00–17:00 SGT today**, conflicting
with all previously recorded schedules. This is operationally material but not one of the
two changes named by the submission page.

## Exact deltas from repository documentation

| Topic | Repository before this audit | Official page today | Team 63 implication |
| --- | --- | --- | --- |
| Ranked score provenance | `docs/competition-rules.md` says `VALID` is arena-server submissions and `SCORE` includes every source, but leaves the final net formula and attribution details unconfirmed. | [Submit](https://hackathonlive.in-cypher.com/) says each team now has an arena account `agent-<team id>` and only submissions under it count. [Scores](https://hackathonlive.in-cypher.com/scores) defines `NET = VALID − PEN` and says **NET is the standing**; manual/member submissions affect only `SCORE`. | Treat only arena-agent `VALID` as competition progress. Do not manually submit competition flags. Monitor `NET`, `VALID` and `PEN`, not `SCORE` or solve count. |
| Platform credentials | `docs/arena-contract.md` describes a fresh platform token, but not the account separation. `docs/setup.md` describes the member CTFd token for local client and registry login. | [Submit](https://hackathonlive.in-cypher.com/) says scored containers receive the agent-account `CTF_TOKEN`, never a member token; `CTF_BASE` is injected and must not be overridden by an embedded `.env`. [Usage](https://hackathonlive.in-cypher.com/usage) says both alias pairs are supplied: `CTF_TOKEN`/`CTFD_TOKEN` and `CTF_BASE`/`CTFD_URL`. | Keep member token limited to authorised local/registry operations. Runtime must trust injected platform variables. An embedded platform URL/token can break attribution and must not override them. |
| Reachable LLM provider | `docs/competition-rules.md`, `docs/setup.md` and `docs/arena-contract.md` allow a generic OpenAI-compatible provider on Day 1 and an unannounced compatible organiser endpoint on Day 2. | [Submit](https://hackathonlive.in-cypher.com/) says OpenRouter is the **only** reachable LLM provider “starting now”; other named providers resolve to `0.0.0.0` in the sandbox from the next cycle. Platform, package registries, web search and challenge instances remain reachable. | Any current Day-1/BYO image must use OpenRouter. A hard-coded non-OpenRouter route will fail. Day-2 code must accept the injected OpenRouter-compatible endpoint/key and must not fall back to an embedded provider when those values exist. |
| Model selection | Repository correctly records that organisers inject endpoint/key but not `LLM_MODEL`; the image default/catalogue policy selects a served model. | [Submit](https://hackathonlive.in-cypher.com/) and [usage](https://hackathonlive.in-cypher.com/usage) confirm only `LLM_BASE_URL` and `LLM_API_KEY` are injected; `LLM_MODEL` stays image-owned and must exist on the injected endpoint. | Existing endpoint catalogue discovery/default policy is directionally compatible. Release checks must prove the image does not force an unsupported model or endpoint. Do not substitute a guessed model after launch. |
| Provider/model budget | `docs/competition-rules.md` records the briefing's `$100` team allowance and separate `$20` tryout allowance. `docs/setup.md` has internal durable USD admission/pacing controls. | None of [submit](https://hackathonlive.in-cypher.com/), [usage](https://hackathonlive.in-cypher.com/usage), [scores](https://hackathonlive.in-cypher.com/scores) or the [platform rules](https://hackathon.in-cypher.com/how-to-play) publishes a numeric current OpenRouter/model budget or changes the earlier briefing allowance. | OpenRouter-only is a routing rule, not evidence of a new cap or unlimited use. Keep the internal cap conservative; do not claim `$100`, `$20`, refill, carry-over or provider billing semantics as current live-site guarantees. Obtain organiser clarification before changing budget policy. |
| Competition clock | `docs/competition-rules.md` uses user/PDF-confirmed 22 Sep 10:00–16:30; `docs/setup.md` requires readiness before 10:00. The CTF guide already conflicted by saying 22 Sep 10:00 through 23 Sep 18:00. | [Scores](https://hackathonlive.in-cypher.com/scores) displayed **11:00–17:00 SGT** and a pre-start countdown at retrieval. [Status](https://hackathonlive.in-cypher.com/status) still displayed “dev mode · no penalties.” The [CTF how-to-play page](https://hackathon.in-cypher.com/how-to-play) still says 22 Sep 10:00 through 23 Sep 18:00. | Do not delay readiness or release preparation past 10:00 merely because the board says 11:00. For penalty/scoring observation, the live board is the current operational signal, but organisers must resolve the three-way schedule conflict. |
| Re-upload penalty | Repository says Day 1 pushes are free and each Day-2 re-upload after the first scored run begins costs 100 points; exact final net/negative behavior was unconfirmed. | [Usage](https://hackathonlive.in-cypher.com/usage) and [scores](https://hackathonlive.in-cypher.com/scores) now specify the baseline is the **first scored run, not first push**; each later re-upload costs 100; `NET = VALID − PEN`; NET is not floored at zero. | Finalise before the first scored container starts. After that, every replacement push can reduce ranked NET by 100 even if the image never scores. A pre-baseline push remains free according to the current page. |
| Push/cycle lifecycle | Repository retains a conflict: usage says a newer push replaces a running container; status says `queued (new)` waits for it to finish. | Conflict remains. [Usage](https://hackathonlive.in-cypher.com/usage) says written partial results are collected, then the old run is stopped and replaced. [Status](https://hackathonlive.in-cypher.com/status) and [scores](https://hackathonlive.in-cypher.com/scores) say `queued (new)` starts once the prior run finishes. Cycles are every 5 minutes and collection plus start can take two cycles (~10 minutes). | Never depend on a push as deterministic immediate cancellation. Avoid unchanged/repeated scored pushes. Observe state across two cycles; request organiser rerun only with explicit authority and awareness of intervention/penalty risk. |

## Confirmed image and runtime contract (no detected delta)

The current [usage guide](https://hackathonlive.in-cypher.com/usage) continues to require:

- image `registry.in-cypher.com:5001/team-63/agent:latest`; submission is a Docker
  push, not a file/form upload;
- official authenticated `base/agent-base:latest`; the image's
  `/opt/agent/CONTRACT.md` is the authoritative co-shipped contract;
- Linux AMD64 build with provenance disabled and a declared startup command;
- sandbox: 2 CPUs, 2 GB RAM, 256 processes, read-only root, all capabilities dropped,
  `no-new-privileges`; only `/work` and `/tmp` writable;
- `/work/results.json`, written incrementally; already-written partial results are kept;
- no container wall-clock cutoff; inherited `run_bash` timeout remains 120 seconds;
- bundled `check_agent.sh` for structural/sandbox validation. A structural pass still
  does not prove model compatibility, solving or fresh scoring.

No public page exposes the digest of the image currently running. Push count, registration,
status, dashboard start time or `running` state therefore cannot prove which digest is active.

## Scoring, cycles and instances

- [Scores](https://hackathonlive.in-cypher.com/scores) now resolves the ranking formula:
  `NET = VALID − PEN`. `SCORE` is informational and includes human/member submissions.
- [Status](https://hackathonlive.in-cypher.com/status) confirms 5-minute cycles. `queued`,
  `queued (new)`, `running`, `collecting` and `done` retain their documented meanings;
  `pull-failed`, `no-token`, `run-failed`, `exited(N)` and `lost` remain failures.
- [Platform rules](https://hackathon.in-cypher.com/how-to-play) still distinguish static
  shared/file challenges from isolated per-player containers with unique flags, private
  addresses and instance time limits. Raw TCP retains the team-key proof-of-work gate;
  web instances retain private subdomains.
- No reviewed page changes the briefing's team-wide one-dynamic-instance limit. It is
  also not restated on today's live pages, so retain the repository's conservative serial
  dynamic lifecycle; do not infer extra capacity from the resource dashboard.
- At retrieval the [dashboard](https://hackathonlive.in-cypher.com/dashboard) exposed only
  its live per-container CPU/memory heading in the rendered public body and no new rule,
  budget or digest fact.

## Authority and unresolved conflicts

The [official platform rules](https://hackathon.in-cypher.com/how-to-play) still require
fully autonomous operation, penalise human intervention, restrict scope to supplied
challenge systems, prohibit attacking the platform/other teams/shared infrastructure,
and prohibit sharing flags or solutions. These rules are unchanged.

Unresolved and requiring organiser confirmation:

- actual scored window: live scores `11:00–17:00` vs repository/PDF `10:00–16:30` vs
  platform how-to-play `22 Sep 10:00–23 Sep 18:00`;
- numeric scored-day model allowance and whether the earlier `$100`/`$20` figures remain
  controlling under the organiser OpenRouter key;
- replacement semantics for a currently running container;
- whether organiser rerun intervention is separately charged in addition to a re-upload.

Operationally, the safest release posture is: be ready by the earliest published time;
use OpenRouter now; preserve injected platform and LLM values; release once before the
first scored run where authorised; then avoid replacement pushes and manual submissions.

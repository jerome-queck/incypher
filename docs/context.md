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
| `entrypoint.sh` → `arena_main.py` → inherited `main.py` | Active; practice filter disabled by a narrow wrapper | Official selection (`ONLY_IDS`), solving, instance lifecycle and results remain inherited |
| `validation_main.py` | Optional single-ID build mode; shares normal wrapper | Omit validation selector in competition image |
| `brain.py`, `agent_ext/adapters.py` | Active synchronous Chat Completions loop | Shell + submit tools; no category skills, memory, cost ledger or scheduler wired in |
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

- Public boards at **21 Sep 19:42 SGT**: rank 8/16, VALID 650, SCORE 650, five solves;
  status 5/15, 12 pushes, last push 17:43:14, `done`, penalty 0. This is Day-1 evidence,
  not final competition score. Read `/scores` and `/status` again for current values.
- Source docs previously called an older digest “current.” That is historical evidence
  only: public status does not identify the deployed digest or its source commit.
- [Arena contract](arena-contract.md) records an earlier inspected base/harness.
  Fresh registry manifest inspection in this pass returned authentication required;
  the official base is not cached on this machine. Current base drift remains unknown.
- This pass creates a Git PR and merge, not a registry release. No practice challenge,
  flag submission, paid API call or organiser restart was performed by this audit.
- `.venv` is installed locally; `.env` exists with private permissions and blank credential fields. Fill them
  on each machine; Codex CLI here reports ChatGPT login. No account token was exported.
- Baseline: 199 offline tests passed on macOS; 19 Linux-only checks skipped.
  Changed-source suite: **216 passed on Linux AMD64/Python 3.12**, zero skips;
  macOS: 216 discovered, 19 Linux-only skips, zero failures. Compilation, shell syntax,
  local doc links, PDF redactions and whitespace checks passed. Historical image tests
  in [day2-readiness.md](day2-readiness.md) belong to their recorded source/digest.

## Next work, in order

1. **Establish the runnable baseline.** Fill `.env`, authenticate registry, inspect the
   fresh base contract/source and build/check this source. Done when digest, source SHA,
   architecture, structural check and exact runtime config behavior are recorded.
2. **Prove solving.** Use one explicitly selected practice challenge via `scripts/arena.py`
   or local Codex practice. Record accepted outcome, elapsed time and model/tool usage
   privately; report sanitized counts. Local/manual solves do not prove arena VALID.
3. **Close the production integration gap.** Choose a trusted structured scope handoff;
   wire one attempt through real tools, evidence qualification, durable intents and
   inherited result output. Done when success, wrong candidate, ambiguous submission,
   timeout, cancellation and instance cleanup pass end-to-end with real adapters.
4. **Measure before optimizing.** Compare identical practice tasks and budgets for baseline
   versus a change. Prioritize valid points per cost/time, coverage and recovery. Static
   parallelism is permitted but unimplemented; dynamic capacity is globally one.
5. **Prepare the clean Day-2 image.** Follow [release gates](setup.md#day-2-release).
   Read runtime-injected model configuration; neither a Sol/Astra pin nor a local
   subscription is a substitute. Record the pushed digest and board outcome separately.

Known limits to investigate: fixed 180s model/120s command calls can exceed proposed
attempt deadlines; shell output is captured before the 12,000-character model excerpt;
normal Brain has no persisted dedupe across restarts, dollar budget accounting, transient
model retry or watchdog. Its `temperature`/`max_tokens` request compatibility with the
unannounced Day-2 endpoint remains unproven. Broad callback exception/cancellation
behavior remains the inherited harness's responsibility until inspected and tested.

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

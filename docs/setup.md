# Local practice and submission

Use from any clone after the [README setup](../README.md#set-up-each-machine).
The same source supports local development and arena packaging, but credentials and
score provenance differ. [Rules](competition-rules.md) govern live operations.

## Private configuration

`python scripts/arena.py init` copies `.env.example` to ignored `.env` with owner-only
permissions on POSIX. It never overwrites values. The parser accepts plain `KEY=value`
and matching quotes; no `export`, interpolation or inline comments. Process environment
values override the file. `doctor` reports presence only, not validity or secret values.

| Value | Where obtained / used |
| --- | --- |
| `TEAM_ID` | Team identity; this repo is Team 63 |
| `CTF_BASE` | Official challenge platform, prefilled |
| `CTF_TOKEN` | Settings → Access Tokens on platform; trusted API client + registry login |
| `LLM_BASE_URL` | Own provider's OpenAI-compatible base or full `/chat/completions` URL |
| `LLM_MODEL` | Provider-supported tool-calling model for local API practice/Day 1 |
| `LLM_API_KEY` | Provider API key; never a Codex login/access token |
| `MAX_STEPS` | Model calls per challenge slice, integer 1–150; packaged default 24 |
| `MAX_TOOL_CALLS`, `MAX_SUBMISSIONS` | Local per-slice tool/submission bounds; packaged defaults 28/3 |
| `MODEL_BUDGET_USD` | Durable run admission ceiling, USD 0.05–85; set from known remaining allowance |
| `MODEL_CALL_RESERVE_USD` | Per-call reserve when pricing is opaque, USD 0.05–5 |
| `MODEL_BUDGET_WINDOW_SECONDS` | Arena spend-pacing window; default 23,400 seconds (6.5 hours) |

The helper reads `.env` locally; Docker does not automatically read it. `practice`
passes only allowlisted runtime names, including the budget controls above. A budget
ledger preserves calls and start time across restarts. A lower ceiling may be applied
to an existing ledger, but raising it is rejected; use a fresh work directory for a
separate newly budgeted run. The solver does not query provider balance automatically.
Local `practice` forces fixed-high reasoning while retaining the configured `LLM_MODEL`.
`build --phase day2` passes no model secret; its image default is
used only when the organiser supplies endpoint/key without a model.
Day-1 builds may include the bounded model-budget policy values above alongside the model
triplet; platform credentials are never copied.
This repo does not discover or
extract keys from another machine, browser, account cache or teammate.

## Local Codex practice

This uses the computer's Codex subscription as the **local solving agent**, not as an
HTTP replacement for `brain.py`. Install the official Codex CLI if absent, then:

```sh
codex login
codex login status
codex --cd .
```

Complete login on each machine; an app login and CLI login should be checked rather
than assumed identical. This machine was already logged in through ChatGPT.
OpenAI confirms subscription login for local CLI use and saved-auth reuse by `codex exec`.
[Authentication](https://learn.chatgpt.com/docs/auth),
[non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode).

Use this prompt with an actual practice ID:

```text
Read AGENTS.md, docs/context.md and docs/competition-rules.md. Solve practice
challenge <ID> locally using this machine's logged-in Codex session. Inspect the
current official base's CONTRACT.md, README.md and ctfd.py before calling its
client. Use .env only in the trusted client/registry process; keep values out of
prompts, logs and Git. Work only on that challenge's provided files/instance.
Use the official Linux container for challenge tools; preserve its sandbox.
Codex owns the local decision loop; do not invoke the API-backed Brain as if it
used this subscription. Confirm no other team dynamic instance is active before
deploying one. Use the trusted client for evidence-backed submission, clean up
the instance, and save a sanitized outcome with elapsed time and unresolved gaps.
Do not push an arena image. Local solving does not establish arena VALID points.
```

This workflow can inspect files, reason, direct container tools and call the documented
client without a model API key. It still needs a CTF token/base-image access for live
practice. It is an agent-directed workflow, not a deterministic end-to-end local runner;
no live subscription-backed solve is claimed by this docs pass. Capturing a sanitized
practice comparison is the next validation gate.

A CLI-to-Chat-Completions adapter is technically possible via `codex exec` structured
output, but would require a tested tool bridge, timeouts, budget/auth handling and
separation from the submitted image. None is implemented. Do not treat account tokens
as general API credentials or export account auth into this public repository's CI.

## API-backed practice

This exercises the **actual submitted Brain** with your provider's key. It uses the
same shell/submission callbacks, official harness and arena sandbox. Practice categories
are eligible by default; the command requires one positive challenge ID.

```sh
python scripts/arena.py login
python scripts/arena.py build --phase day2 --image incypher-agent:local
python scripts/arena.py check --image incypher-agent:local
python scripts/arena.py practice --image incypher-agent:local --challenge 94
```

Replace 94 after confirming the intended practice challenge. The command passes runtime
model values from `.env`, so a clean Day-2-style image works for local testing. It mounts
a new ignored results directory each time; inspect its `results.json` privately.
`already_solved` demonstrates callback reachability, not acceptance of the candidate.
Checkers without a token are structural only. Practice can spend provider credits.

## Day-1 release

The live guide permits your own model and injects no model variables. This implementation
therefore needs a compatible provider API key, except for a future scripted solver that
never calls a model. Codex is not installed in the base and its login is not transported
by Docker. A subscription-backed remote image is neither implemented nor established
as compatible with organiser accounting/sandbox constraints.

For an explicitly requested Day-1 release:

```sh
python scripts/arena.py login
python scripts/arena.py build --phase day1 --image incypher-agent:day1
python scripts/arena.py check --image incypher-agent:day1
python scripts/arena.py push --phase day1 --image incypher-agent:day1
```

The helper creates a temporary mode-0600 file containing the `LLM_*` triplet and any set
model-budget policy values, supplies it as a BuildKit secret, and deletes the temporary
file. Docker deliberately copies it into a
mode-0400 image layer for Day 1. **The resulting image still contains that credential**;
BuildKit does not remove a secret explicitly copied into the image. Push it only to the
official team registry. Anyone able to read that image, including organisers, can read
it. A complete runtime triplet wins; partial configuration fails rather than mixing
providers. Ordinary Day-2 builds have no embedded model credential.

## Day-2 release

Complete before the user-confirmed 22 Sep 10:00 SGT start:

1. Authenticate registry; pull the current official base and inspect its contract and
   harness. Compare with [recorded inspection](arena-contract.md); resolve drift before
   claiming compatibility. Preserve an identified rollback digest.
2. Merge intended source and run offline regression tests. Build cleanly with
   `build --phase day2`; no `INCLUDE_DAY1_LLM` or `VALIDATION_CHALLENGE_ID`.
3. Run `check` on that exact image. This imports every packaged module and executes
   the bundled checker without a token. Confirm runtime `LLM_*` precedence and no
   Day-1 secret/validation file. When only endpoint/key are present, the entrypoint marks
   the image default for one bounded authenticated `/models` lookup: exact default wins,
   otherwise selection follows [provider discovery](provider-discovery.md). Unavailable
   discovery fails before dispatch. A structural pass does not validate the Day-2 endpoint
   or model.
4. Complete one authorized practice model/tool/submission test when credentials are
   available. Record source SHA, image/base digests, checks and sanitized result.
   Distinguish local and arena-origin evidence.
5. When release is requested, run `push --phase day2` once. It rejects images retaining
   the Day-1 credential file or validation selector, then pushes Team 63's `:latest`.
6. Observe status and VALID scores without interacting with the solver. Record the
   deployed digest/last-push time and whether the arena collected results. During
   scoring, a newer push or organiser restart can incur penalties.

Commands are in [README](../README.md#practice-and-submission). `push` does not build or
run the checker for you. Release authorization is separate from ordinary Git work;
a Git merge alone does not authorize an arena submission. Use the current session's
explicit release scope; the [overnight build brief](solver-build/brief.md) requests a
readiness-gated Day-1 release and preparation of a separate clean Day-2 image.

## Troubleshooting

- Registry authentication required: fill `CTF_TOKEN`, verify `TEAM_ID`, run `login`;
  check port 5001 connectivity. No anonymous base pulls.
- Local `ConfigurationError`/401: verify all three provider values; a Codex subscription
  is not an API key. Never print tokens to diagnose configuration.
- No challenges attempted: inspect selector, base enumeration and available challenge
  phase. The normal wrapper disables only the inherited practice filter.
- `exec format error`: rebuild Linux AMD64; do not ship the Mac's ARM architecture.
- Read-only-filesystem error: write only `/work` or `/tmp`; the organiser checker treats
  such errors as failures even if the process continues.
- `done` with zero solves: inspect private results; completion is not solving proof.
- Day-2 model rejects request parameters: retain injected identity/endpoint, capture a
  sanitized error, and test provider compatibility. A model-name substitution is not
  a valid repair of the competition configuration.

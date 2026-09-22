# IN-CYPHER agent

Team **63 — procrastinators**. Prepare for **22 September 2026, 10:00–16:30 SGT**.
Start with [agent instructions](AGENTS.md), [current context](docs/context.md), and
[competition rules](docs/competition-rules.md). The renamed
[briefing slides](docs/references/incypher-hackathon-2026-briefing.pdf) are checked in.

## Set up each machine

Requires Git, Python 3.12+, and Docker with Linux containers. Run from the cloned repo:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements-test.txt
python scripts/arena.py init
python scripts/arena.py doctor
python -m unittest discover -s tests -p 'test_*.py' -v
```

Windows: use `py -3.12 -m venv .venv`, then `.venv\Scripts\Activate.ps1` in PowerShell.
Linux-only tool tests require Linux/WSL or the Linux CI job; macOS skips them.

`init` creates a private, ignored `.env` and preserves an existing file. Fill missing
values locally using [.env.example](.env.example). `CTF_TOKEN` comes from the team's
CTFd access-token settings; it also logs into the registry. Never commit the filled file.

## Choose the execution mode

| Mode | Model credentials | Instructions |
| --- | --- | --- |
| Offline tests | None; synthetic callbacks | Command above |
| Local Codex practice | This machine's own `codex login` subscription | [Local Codex workflow](docs/setup.md#local-codex-practice) |
| Local submitted-solver practice | Provider `LLM_*` API configuration in `.env` | [API-backed practice](docs/setup.md#api-backed-practice) |
| Day-1 arena image | Own provider API key, bundled only in private release layer | [Day 1](docs/setup.md#day-1-release) |
| Day-2 arena image | Organiser injects endpoint/key; image selects a served model | [Day 2](docs/setup.md#day-2-release) |

Local Codex is a separate solver/development workflow. The submitted `brain.py` calls
Chat Completions; it cannot consume a ChatGPT subscription token. No CLI-to-API bridge
is implemented. Each machine logs into Codex itself; account auth is never copied into
`.env`, Docker or Git. See [verified authentication guidance](docs/model-guidance.md#authentication).

## Practice and submission

Practice challenges are enabled in normal builds. After filling `.env`:

```sh
python scripts/arena.py login
python scripts/arena.py build --phase day2 --image incypher-agent:local
python scripts/arena.py check --image incypher-agent:local
python scripts/arena.py practice --image incypher-agent:local --challenge 94
```

The last command **solves/submits to the selected live practice challenge**, using the
API key in `.env`. Substitute an authorized practice ID; ensure no other team dynamic
instance is active. Local results remain under ignored `private/practice/` and do not
establish arena VALID points.

For an authorized Day-2 release, build/check the exact image, then publish explicitly:

```sh
python scripts/arena.py build --phase day2 --image incypher-agent:day2
python scripts/arena.py check --image incypher-agent:day2
python scripts/arena.py push --phase day2 --image incypher-agent:day2
```

Follow the full [release gates](docs/setup.md#day-2-release) first. A registry push is
the submission; a Git push/PR/merge is not. Later Day-2 re-uploads cost points.
Watch [status](https://hackathonlive.in-cypher.com/status) and
[scores](https://hackathonlive.in-cypher.com/scores). The live guide currently
allows three free scored-day re-uploads before 100-point charges.

## What runs

The official image supplies `main.py`, `solver.py`, `ctfd.py` and the results writer.
Our entrypoint preserves runtime model configuration, enables practice selection, and
loads the custom Brain. `agent_ext/` strategy/tools/evidence modules are packaged but
remain unconnected to the normal solver. See [interfaces](docs/interfaces.md) before
integration work and [context](docs/context.md) for the remaining readiness gaps.

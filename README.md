# IN-CYPHER agent

Team 63's minimal extension of the official arena agent. The organiser's `main.py`, `solver.py`,
`ctfd.py`, and results writer remain inherited. This repository overrides `brain.py`, supplies a
thin configuration entrypoint, and adds dependency-free internal contracts under `agent_ext/`.

See [arena contract](docs/arena-contract.md) and [shared interfaces](docs/interfaces.md).

## Offline tests

```sh
python3 -m pip install -r requirements-test.txt
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Tests use synthetic callbacks: they do not contact a model, the Board, or the registry.

## Build and structural check

```sh
docker build --platform linux/amd64 --provenance=false -t incypher-agent:latest .
./scripts/check_image.sh incypher-agent:latest

docker create --name incypher-check-source incypher-agent:latest
docker cp incypher-check-source:/opt/agent/check_agent.sh /tmp/check_agent.sh
docker rm incypher-check-source
chmod +x /tmp/check_agent.sh
/tmp/check_agent.sh incypher-agent:latest
```

The first check proves the custom modules are present. The organiser checker validates image
architecture, startup, and sandbox compatibility. Structural success does not prove model access
or challenge solving.

Token-backed checker mode can act on the live platform. Run it only for an explicitly authorised
single challenge, with credentials supplied through the process environment. Never store tokens,
flags, raw traces, or runtime results in this repository.

## Runtime environment

- Platform: `CTF_BASE`, `CTF_TOKEN` (the arena also injects `CTFD_URL`, `CTFD_TOKEN`).
- Model: `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY`.
- Optional bounds: `MAX_STEPS` and `MAX_SUBMISSIONS` (default 3 submissions per challenge).

The container may write only to `/work` and `/tmp`. The Brain reads model configuration at runtime;
no credentials are baked into source or image metadata.

On day 1, the arena does not inject model variables. Build the private release image with the
team-owned env file as a BuildKit secret. The non-secret build selector isolates its cache layer:

```sh
docker build --no-cache --platform linux/amd64 --provenance=false \
  --build-arg INCLUDE_DAY1_LLM=1 \
  --secret id=day1_llm,src=/path/to/day1-llm.env \
  -t incypher-agent:latest .
```

The secret is copied only into that private release image and loaded into the process environment
by `entrypoint.sh`; it is absent from Git, build arguments, Docker config metadata, and logs. Push
that image only to the official team registry. Ordinary/day-2 builds omit both flags and contain no
embedded model credential because the arena injects the runtime values.

For the day-1 platform proof only, force the official harness to attempt one authorised practice
challenge that it would normally filter out:

```sh
docker build --no-cache --platform linux/amd64 --provenance=false \
  --build-arg INCLUDE_DAY1_LLM=1 \
  --build-arg VALIDATION_CHALLENGE_ID=94 \
  --secret id=day1_llm,src=/path/to/day1-llm.env \
  -t incypher-agent:validation .
```

This mode changes only challenge selection: solving, submission, and results remain owned by the
official harness. Omit `VALIDATION_CHALLENGE_ID` for normal competition images.

## Submit

```sh
docker tag incypher-agent:latest registry.in-cypher.com:5001/team-63/agent:latest
docker push registry.in-cypher.com:5001/team-63/agent:latest
```

A registry push submits an arena image and is distinct from pushing a Git branch or opening a PR.
The newest `:latest` is eligible for the next arena cycle. Recheck the live
[submission guide](https://hackathonlive.in-cypher.com/usage) before release.

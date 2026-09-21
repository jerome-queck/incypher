# IN-CYPHER agent

Minimal autonomous agent submission for team 63. The image uses the official working reference agent unchanged.

## Build and check

```sh
docker build --platform linux/amd64 --provenance=false -t incypher-agent:latest .
./check_agent.sh incypher-agent:latest
./check_agent.sh incypher-agent:latest '<CTFd access token>' 90
```

`check_agent.sh` is supplied by the base image at `/opt/agent/check_agent.sh`. Never store the CTFd token in this repository or image.

## Runtime environment

The official agent already reads the arena contract variables:

- `CTF_BASE` and `CTF_TOKEN` (also injected as `CTFD_URL` and `CTFD_TOKEN`)
- `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`

For a local day-1 live check, export the three `LLM_*` values in the shell running the checker. The arena injects them on day 2. Keep all keys out of the build context and repository.

## Submit

```sh
docker tag incypher-agent:latest registry.in-cypher.com:5001/team-63/agent:latest
docker push registry.in-cypher.com:5001/team-63/agent:latest
```

See the [arena contract](https://hackathonlive.in-cypher.com/usage) for runtime limits and environment variables.

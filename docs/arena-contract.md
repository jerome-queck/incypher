# Arena contract and evidence

Verified on 21 September 2026 from the authenticated organiser image and its files under
`/opt/agent/`. This document distinguishes inspected behavior from local tests and arena
results. It contains no credentials, flags, or raw run output.

## Image identities

- Reviewed repository baseline: `7fb4159857f1de56e79b4462ef05ea83b47eda1a`.
- Organiser base: `registry.in-cypher.com:5001/base/agent-base:latest` at
  `sha256:d3c707c6187f49a8b5f0ba617b9590cce72a18676d93343a93098726c7723224`.
- First submitted derived image: `sha256:aa19961428f1cf24a654ddb5ec89fab924c1bcbe77f7978654c31a42cb5ddbca`.
- Platform/size: Linux AMD64, approximately 283 MB.
- Inherited start command: `python /opt/agent/main.py`.

The base remains referenced by its required `:latest` tag. The digest above records what was
actually tested; it is not a silent Dockerfile pin.

## Organiser extension seam

`/opt/agent/brain.py` defines the supported extension:

```python
Brain(run_bash, submit_flag, max_steps=40).solve(prompt: str) -> dict
```

- `run_bash(command: str) -> str` runs in the container and returns combined stdout/stderr.
  The inherited adapter uses a 120-second subprocess timeout and returns diagnostic text for
  timeouts and execution failures.
- `submit_flag(candidate: str) -> dict` calls the trusted platform client. Observed status
  values include `correct`, `incorrect`, `already_solved`, and `ratelimited`.
- `solve` handles one challenge and returns at least `solved: bool`; the inherited solver adds
  challenge identity, type, file/instance booleans, and elapsed seconds.

`main.py` owns challenge enumeration and `/work/results.json`. `solver.py` owns downloads,
instance boot/destroy, prompt construction, and `Brain` invocation. `ctfd.py` alone owns
platform credentials and HTTP calls. This repository does not replace those three files.

## Runtime paths and limits

- Read-only root filesystem; writable `/work` and `/tmp` only.
- 2 CPUs, 2 GB memory, 256 PIDs, all capabilities dropped, no privilege escalation.
- Challenge files: `/work/<challenge-id>/`.
- Results: `/work/results.json`, rewritten after each completed challenge and once at final exit.
- `run_bash` command timeout: 120 seconds.
- No per-run wall-clock timeout was present in the inspected contract.
- Dynamic instances are destroyed best-effort after `Brain.solve` returns.

The inherited Python process is the container lifecycle. No separate controller should remain
idle after `main()` exits.

## Runtime configuration

Arena platform values:

- `CTF_BASE` and `CTF_TOKEN` are read by the inspected `main.py`.
- The contract states that `CTFD_URL` and `CTFD_TOKEN` carry the same injected values. The
  inspected `main.py` does not itself fall back to those aliases, so local invocations must set
  the canonical names.
- Never place platform credentials in source, build arguments, image `ENV`, or logs.

Model values are read at runtime: `LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY`. All three are
required by the override. `LLM_BASE_URL` may be either the API root or the complete
`/chat/completions` URL. Missing configuration, HTTP errors, timeouts, and malformed responses
become unsuccessful Brain results rather than empty success.

## Result shape

The final inherited writer emits this shape. Values below are synthetic:

```json
{
  "total_seconds": 12.3,
  "solved": 1,
  "attempted": 1,
  "results": [
    {
      "id": 123,
      "name": "Synthetic challenge",
      "category": "synthetic",
      "type": "standard",
      "had_files": true,
      "had_instance": false,
      "seconds": 12.1,
      "solved": true,
      "steps": 4,
      "flag": "<redacted>",
      "verdict": {"status": "correct"}
    }
  ]
}
```

During a run, the checkpoint file is temporarily a JSON list of completed results; final exit
replaces it with the object above. Consumers must tolerate both valid shapes. The inherited
writer is authoritative; extensions must not create a competing writer.

## Error and cancellation behavior

- Missing platform token: `main.py` exits 2 before enumeration.
- `run_bash` timeout/execution errors: diagnostic strings returned to the Brain.
- Model/config/HTTP/malformed response: unsuccessful Brain result with an error summary.
- Platform client transport/API failures: structured `error`/`status` values where handled.
- Dynamic destroy failures: suppressed by the inherited solver after best-effort cleanup.
- Explicit cancellation propagation is not implemented by the inherited Brain interface.
  Container termination therefore remains an evidence gap.

## Evidence levels

1. **Local unit tests** use synthetic callbacks only; no model or Board.
2. **Local image build/smoke** proves the override and package are present.
3. **Structural checker** proves AMD64/startup/sandbox behavior, not solving.
4. **Token-backed retry** proved autonomous commands and real submission calls on an
   already-solved practice challenge. It is not fresh acceptance evidence.
5. **Arena result** remains pending. Only a new `status: correct` plus a valid retained results
   file proves the tracer-bullet goal.

The inspected checker has SHA-256
`c50ca1f8f0db895a4118fff9b87d48fd9911bebf1cb6537e8cd3bb305783c544`.
Structural invocation against the submitted source image produced 6 passes, 0 failures, and
2 expected warnings (inherited root user and no token in structural-only mode).

## Safe checker extraction

Keep the organiser script outside Git:

```sh
docker create --name incypher-check-source incypher-agent:latest
docker cp incypher-check-source:/opt/agent/check_agent.sh /tmp/check_agent.sh
docker rm incypher-check-source
chmod +x /tmp/check_agent.sh
/tmp/check_agent.sh incypher-agent:latest
```

Token-backed checker mode can contact the live platform and must be restricted to an explicitly
authorised challenge. Never put a token in documentation, shell history, or committed output.

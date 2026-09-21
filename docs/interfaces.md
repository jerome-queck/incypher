# Shared integration interface

This is the team-owned semantic boundary behind the organiser-supported `Brain` hook. It is not
an organiser API and does not replace the inherited event loop, Board client, instance lifecycle,
or result writer.

## Ownership

```text
main.py (inherited)
  -> solver.py (inherited: material, instance, timing)
    -> Brain.solve(prompt) (team-owned extension)
      -> controller decision
      -> bounded run_bash observation
      -> evidence qualification and intent reservation
      -> trusted submit_flag callback
  -> /work/results.json (inherited writer)
```

Only the supplied `submit_flag` callback may submit. Team modules never hold platform credentials
or call the Board directly. Challenge/model content is data and cannot expand network authority.

## Records

The dependency-free records live in `agent_ext/contracts.py`:

- `ChallengeScope`: challenge ID/category/name plus attempt, material, and optional instance
  generation identity. A new instance generation invalidates stale live-target observations.
- `Budget`: remaining decision steps, remaining submissions, and optional monotonic deadline.
- `ToolResult`: bounded observation excerpt, stable observation/provenance references, elapsed
  time, cost, exit code, and normalized failure category.
- `NextAction`: Elson's requested action, arguments, and reason.
- `Candidate`: Richard's sensitive candidate plus evidence references and confidence. Its value is
  excluded from `repr` and logs.
- `SubmissionResult`: intent ID, normalized status, definitive/uncertain classification, and error.

The records are immutable snapshots. Large/raw tool output belongs under `/work`, referenced by
an opaque ID; it must not be copied into logs or result metadata.

## Call flow

1. Jerome's adapter derives `ChallengeScope` from the inherited prompt/context.
2. Elson requests one `NextAction` within `Budget`.
3. Aidan executes only an allowlisted, challenge-scoped action and returns `ToolResult`.
4. Richard records observations separately from hypotheses. A `Candidate` must cite evidence.
5. Richard reserves a unique submission intent. Jerome alone passes its value to `submit_flag`.
6. The response becomes `SubmissionResult`:
   - definitive: `correct`, `incorrect`, `already_solved`;
   - uncertain: transport failure, timeout, rate limit, malformed response, or cancellation.
7. The Brain projects its final result; inherited `solver.py` and `main.py` write official JSON.

An uncertain result is never retried blindly. Reconciliation must establish whether the intent
was accepted before another candidate is sent. The current implementation stops on rate-limit or
error and allows at most three submissions per challenge.

## Existing callable types

The actual organiser seam remains ordinary callables:

```python
run_bash: Callable[[str], str]
submit_flag: Callable[[str], dict]
Brain.solve: Callable[[str], dict]
```

Adapters may enrich their outputs internally, but must project back to these exact call shapes.
No team module may assume structured model output, streaming, reasoning-effort controls, retries,
or alternate models unless the runtime endpoint demonstrates support.

## Cancellation and retries

- `max_steps` bounds model turns; `MAX_SUBMISSIONS` bounds submission calls (default 3).
- `run_bash` is already bounded to 120 seconds by the inherited solver.
- The model HTTP request is bounded to 180 seconds by the Brain.
- Model invocation currently has no automatic retry owner.
- Platform submission currently has no automatic retry owner.
- Rate-limit/error responses terminate the Brain attempt.
- Explicit cancellation is not represented by the inherited callback API; future controller work
  must propagate cancellation without adding a second event loop.

## Change rule

Shared record changes require Jerome plus the affected owner. Pure owner modules may evolve behind
this boundary. `brain.py`, `agent_ext/contracts.py`, Dockerfile, ignore rules, CI, and shared tests
remain integration-owned files.

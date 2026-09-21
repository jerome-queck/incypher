# Historical Day-2 runtime verification

Evidence for merged [PR #3](https://github.com/jerome-queck/incypher/pull/3), not current
release readiness. Read [context](context.md) and [setup](setup.md) for today's state.

Recorded 21 September 2026 from PR #3's runtime work, rebased onto merged team commit
`cde9ef48ed955c503c225b0a4d5fcec8245786a2`.

## Configuration audit

The then-current normal-selection registry image
`sha256:75fc11358fc236c505026288dea5b3b2f0d2cf07e182a6a9f53db7dff28523e3`
contains `/opt/agent/.day1-llm.env`. Its entrypoint sources that file unconditionally. A
value-free sentinel check confirmed that sourcing it replaces a complete runtime
`LLM_BASE_URL`, `LLM_MODEL`, and `LLM_API_KEY` triplet. No embedded values were printed or
recorded.

The Day-2 entrypoint now applies the Day-1 file only when all three runtime variables are
absent. If any runtime value is present, no fallback value is loaded. The Brain's existing
strict `LLMConfig` then rejects partial or blank configuration before any model request or
flag submission. A complete runtime triplet remains untouched.

## Authoritative baseline

The full cached organiser files `CONTRACT.md`, `README.md`, `main.py`, `solver.py`, `ctfd.py`,
`brain.py`, `check_agent.sh`, and `local_test.py` were read from Linux AMD64 base image
`sha256:d3c707c6187f49a8b5f0ba617b9590cce72a18676d93343a93098726c7723224`.
Registry authentication was unavailable for a fresh pull, so this record does not claim that
the mutable base tag was refreshed after that digest was cached.

The Day-2 image retains these inherited file hashes:

- `main.py`: `1329c65ab37c953fbb74d37057adf0d325ee4340473069471379777bd8aeddf0`
- `solver.py`: `2046a613283065730fc47886bd34a74d74bc3e80b4a0860f1ce9113b3d2d8f22`
- `ctfd.py`: `a328511e7bbb61f95f741b5097f309a73f090ec74bac47510851e06af310fcbf`
- `check_agent.sh`: `c50ca1f8f0db895a4118fff9b87d48fd9911bebf1cb6537e8cd3bb305783c544`

Thus `main.py` still owns enumeration and results, `solver.py` still owns challenge lifecycle,
and `ctfd.py` remains the only Board/submission client.

## Build and verification

Built without a secret, validation selector, or model build argument:

```sh
docker build --no-cache --platform linux/amd64 --provenance=false \
  -t incypher-agent:day2-runtime-env .
```

Result: Linux AMD64, 283,986,826 bytes, local image digest
`sha256:9c656772d8367143109beb0707a48188484e7bf4615a8a0010410ab0a3dfa39e`.
`/opt/agent/.day1-llm.env` and `/opt/agent/.validation-id` are absent. Image configuration has
no `LLM_*` environment entries. The module-in-image smoke check imports the Brain and every
merged `agent_ext` module, including strategy, bounded tools/resources, memory, verification,
submission state, and internal result projection.

The combined Python 3.12 offline suite passed 199 tests. It uses synthetic configuration, model
replies, tools, evidence stores, and submission callbacks only; it uses no model, Board, registry,
credential, or external socket. Coverage includes complete runtime precedence, all six nonempty
partial-runtime combinations, Day-1-only fallback, and rejection before network/submission.

The exact inherited checker above ran in structural-only mode against the built image under the
arena's read-only-root, capability, privilege, CPU, memory, PID, `/work`, and `/tmp` constraints:
6 passed, 0 failed, 2 expected warnings (root user; no token/live check).

A separate Linux AMD64 image was built with `INCLUDE_DAY1_LLM=1` and a synthetic BuildKit secret
(`sha256:ab12477284316b57d4ffd14434852d97aa2a3508f2cfdcf70c39125fb20b15e6`).
Image-level entrypoint probes confirmed that the Day-1 fallback is loaded when runtime model
configuration is absent, a complete Day-2 runtime triplet wins unchanged, and a partial runtime
configuration remains partial. The probe used no real credential, model, Board, or socket; the
image configuration itself still contains no `LLM_*` entries.

## Remaining gaps

- No live Board, model, fresh flag acceptance, registry push, or arena rerun was performed.
- Prior arena evidence remains `already_solved`, not a fresh `correct`; all 15 then-visible
  challenges were solved practice challenges.
- Structural checking proves startup and sandbox compatibility, not Day-2 model compatibility or
  solving effectiveness.
- The merged controller, bounded tools, and evidence/submission modules are packaged and tested but
  remain inactive. Their documented integration requires a trusted structured `ChallengeScope`,
  whereas the inherited Brain seam receives only a prompt and callbacks. Inferring authority from
  prompt text or replacing `solver.py` would violate the agreed seam. Activation therefore remains
  a separate reviewed integration change, not a hidden part of this runtime fix.
- The base tag could not be refreshed during this work; revalidate its digest before an approved
  release if registry access returns.
- Inherited container termination/cancellation behavior remains unproven beyond the structural
  checker.

## Rollback

No registry state changes in this work. At the time of this record, the prior source baseline was `cde9ef48ed955c503c225b0a4d5fcec8245786a2`. If a separately approved future deployment
needs arena rollback, the captain can retag and push the retained normal-selection image
`sha256:75fc11358fc236c505026288dea5b3b2f0d2cf07e182a6a9f53db7dff28523e3`.
That restores the prior arena-validated behavior, including its known Day-1 override risk, so it
is an emergency compatibility rollback rather than the preferred Day-2 configuration.

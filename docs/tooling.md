# Bounded observations and resources

Read for `agent_ext/tools/` or admission changes. Merged through PR #9; the normal Brain
still invokes the inherited shell callback. Aidan's fixed inspection workers are separate
from that backend. [Context](context.md) owns activation status;
[interfaces](interfaces.md) owns shared contracts.

## Tool contract

Operations: `identify`, `text`, `hex`, `strings`, `zip_list`. They inspect local material;
no generic scripts, executable selection, target connection, extraction or decompression.
Use the official backend separately for shell/network work. Trimming inherited shell
output after it returns cannot bound its earlier capture or establish descendant reaping.

An executor binds trusted scope and one authorized material root. Models provide only
relative path, operation and offset. Root authority comes from trusted harness metadata;
being under `/work` or `/tmp` is not sufficient. Unsupported platforms fail closed.

Every observation hashes one bounded immutable snapshot, so its digest describes exactly
what was inspected. Stat checks detect observed mutation. Files exceeding the snapshot
limit are refused rather than partially hashed. Identity includes challenge, material,
instance generation, operation/version, offset and limits; attempt ID is provenance,
not cache invalidation. No actual evidence cache is implemented here.

| Operation | Semantics |
| --- | --- |
| identify | Conservative header signature; unknown remains unknown |
| text / hex | Explicit byte coverage/offset and truncation |
| strings | Printable ASCII with offsets, capped count and lengths |
| zip_list | Bounded central directory; declared sizes are unverified |

ZIP preflight rejects traversal, absolute/drive paths, symlinks, oversized names and
excessive declared expansion. ZIP64, split and prefixed archives are unsupported.
Read current numeric limits from `Limits` in `tools/inspection.py`.

## Execution and resource contract

Workers use isolated Python, a minimal environment excluding credentials/startup hooks,
read-only regular-file access through descriptor-relative `O_NOFOLLOW`, resource limits
and empty per-call scratch. Code/scratch paths must be trusted and outside material control.
This is fixed-function confinement, not a generic shell sandbox.

The supervisor bounds both streams while reading. Timeout/cancellation/overflow kills
the private process group and waits for the direct worker before releasing admission
and removing scratch. The worker never forks; arbitrary double-fork descendant reaping
has not been proven. Unknown worker failure is not diagnosed as OOM without evidence.

`Admission` uses FIFO waiting, finite queue, total/heavy concurrency and estimated
memory/PID reservations. Acquire once inside the executor; avoid a second lease around
it or holding a lease during model calls. Release is idempotent. Trusted capacity must
reserve headroom for harness, evidence and transient peaks. Per-worker address-space
limits and RSS do not measure aggregate container memory.

## Evidence sink and integration

Sink shape: `(ChallengeScope, observation_key, bounded_observation_dict) -> opaque_ref`.
It must finish promptly, enforce retention quotas and share the attempt cancellation/
deadline policy. This is a proposed seam, not an already-wired Richard/Aidan integration.
The worker timeout cannot interrupt this synchronous sink.

`ToolResult` carries bounded JSON excerpt, coverage/truncation, source digest, measured
time and worker RSS. An observation reference appears only after sink success. Unknown
container metrics remain unknown. Excerpts may contain sensitive challenge material;
store them privately, not in logs or committed fixtures. A successful inspection does
not establish a qualified candidate, verification or platform acceptance.

`execute_action` accepts the shared `NextAction`/`Budget` shape. BrainAttempt currently
passes shell strings; binding fixed structured operations requires an explicit adapter.
Post-hoc observation classification cannot enforce bounds on an already-executed shell.

## Verification and remaining gates

Linux tests cover flooded streams, malformed output, timeout/cancellation, direct-worker
reaping, scratch cleanup, queue/resource leases, unsafe paths, special files, ZIP limits,
mutation, credential exclusion and shared result mapping. Non-Linux execution tests skip;
run Linux CI before claiming full coverage. The optional synthetic benchmark is
`python -B -m tests.fixtures.aidan.benchmark_tools`; it is not an arena performance claim.

Before activation: bind trusted root/scope; agree the real bounded evidence sink and cache
semantics; pass shared deadlines/cancellation; measure aggregate image memory/PIDs/scratch;
run image smoke/checker. Generic shell/connection execution needs a separately tested
backend. These workers alone neither improve the current solve score nor enforce the
competition's team-wide one-dynamic-instance rule.

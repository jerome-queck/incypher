# Bounded local observations and resource admission

Owner: Aidan. Initial implementation base: `ebddc8daa346248226450de629f72cfb4ffa8f9c`
(merged foundation #1). Refreshed onto current main
`e12cddff3326712ccf17894bd4f7eddf84f04041` (merged strategy #2) on 21 September 2026.
Runtime PR #3 remains separate. This PR's changes are confined to Aidan's owned paths.

## Status and scope

This is a **draft integration slice**, using the merged `ChallengeScope` and `ToolResult`
records without changing their owner-managed definitions. It supplies callable local tools,
a shared admission manager, offline tests and a reproducible synthetic benchmark. It does
not change `brain.py`, model tools/prompts, the controller, evidence store, submission path,
Dockerfile or other shared configuration. The existing Dockerfile already copies `agent_ext/`;
these modules will be packaged by that rule but are not invoked by the current Brain.

Jerome's `docs/arena-contract.md` records the inspected base digest and the inherited
`run_bash(str) -> str` callback. That callback captures combined output and has a documented
120-second timeout, but no cancellation parameter or demonstrated descendant reaping.
Trimming its returned string cannot bound its earlier capture. It is therefore not advertised
here as a bounded execution backend. No organiser image or helper source was locally available;
Docker was not found in the inspected Ubuntu environment. Existing captain checker evidence
was reused as context, not claimed as a test of this change.

The first slice uses a small fixed Python worker, only for read-only local inspection. It
accepts no scripts, commands, target addresses or executable selection. The only dispatch
names are `identify`, `text`, `hex`, `strings`, and `zip_list`. A `run_bash` request returns
`configuration / unsupported_operation` before launching anything. Target connection/pwn
operations remain with Jerome's trusted integration.

## Inventory and observation semantics

These are implemented operations, not a claimed inventory of arena-installed binaries.
They require Linux and the existing Python standard library, with no new package dependencies.

| Operation | Structured facts | Coverage/limits |
| --- | --- | --- |
| `identify` | Conservative ELF/ZIP/gzip/PDF/PNG header signature, or `unknown` | Signature method explicit; no guessed MIME type from extension |
| `text` | UTF-8 preview, replacement policy, offset and bytes inspected | Default 1 KiB preview; nonzero offset or omitted tail marks truncation |
| `hex` | Hexadecimal bytes, offset and bytes inspected | Default 1 KiB input, with encoded-output cap |
| `strings` | Printable ASCII sequences, offsets, per-string shortening | Minimum 4 characters, at most 32 strings of at most 128 bytes; scan coverage explicit |
| `zip_list` | Member names, declared/compressed sizes, encryption markers | At most 100 members and 64 KiB central directory; no extraction, execution or decompression |

All operations first read and hash a complete immutable snapshot of at most 1 MiB by default.
This makes identity exact and resource cost finite; files larger than that are refused rather
than partially hashed and incorrectly cached. Larger-file streaming identities/range reads
are a future interface decision. Trusted configuration may raise the snapshot cap to 8 MiB.

ZIP listing preflights central-directory bytes and actual record count before constructing
`ZipInfo` objects. Traversal, absolute/drive paths, symlinks, names over 512 UTF-8 bytes,
and declared total expansion over 16 MiB are rejected. ZIP64, split and prefixed/self-extracting
archives are unsupported. Sizes are explicitly unverified metadata. Since there is no
extraction operation, no attacker-declared size is used to authorise decompression or writes.

## Integration example and ownership

The adapter derives one authorised material root from trusted harness context; the model
cannot choose a root, budget, executable, sink or environment. One executor is bound to that
scope/root. It accepts only a relative material path and validated operation/offset.

Illustrative integration, using Richard's eventual bounded private sink:

```python
from agent_ext.resources import Admission, Capacity
from agent_ext.tools import ToolExecutor

# Example experimental tool-pool budget, NOT measured arena headroom.
shared_pool = Admission(Capacity(memory_bytes=256 * 1024 * 1024, pids=2))
tools = ToolExecutor(scope, "/work/123", shared_pool, richard_sink)
result = tools.execute(
    "inspect-1", "text", "material.bin",
    timeout_seconds=5, queue_seconds=2,
    deadline_monotonic=attempt_deadline,
    cancellation=cancel_event,
)
```

For shared records, `tools.execute_action(action_id, NextAction("text", {"path":
"material.bin", "offset": 0}, reason), budget, cancellation=cancel_event)` returns the
same `ToolResult` and honours `Budget.deadline_monotonic`. Only `path` and `offset` are
accepted action arguments. Elson retains tool-call counting; shared decision/model steps
are not mistaken for a local concurrency limit. Tests pass real results to the merged
`strategy_bridge.failure_from_tool` classifier. The current `BrainAttempt` still invokes
`run_bash` strings, so Jerome must explicitly add the fixed structured actions at that
seam; this code does not parse shell strings into an invented protocol or claim that
`StrategyOwners.observe` can retroactively enforce execution limits.

The sink signature is `(ChallengeScope, observation_key, bounded_observation_dict) -> opaque_ref`.
Its returned reference must be 1–160 characters from letters, digits, `_ . : -`. This is a
proposed owner-to-owner sink seam, not an organiser API or Richard's implemented store.
The sink must complete promptly, avoid model/network work, enforce aggregate storage quotas
and share the attempt's cancellation/deadline policy. This synchronous callback is trusted;
the worker's hard timeout cannot interrupt it. Agree the real sink contract before activation.

`ToolResult.excerpt` contains bounded ASCII JSON with status, operation, structured observation,
truncation/coverage, source digest, queue time, worker peak RSS and unknown container metrics.
`duration_seconds` measures the whole dispatch through evidence storage. `observation_ref`
is populated only after the sink succeeds. `provenance_refs` contains the observation identity.
`cost_units` remains the shared default (unmeasured), not an invented dollar estimate.

Evidence identity includes content SHA-256, challenge ID, material reference, instance generation,
operation/version, offset and all inspection limits. It deliberately excludes attempt ID.
Source bytes are read from one descriptor; before/after stat identity catches observed mutation,
and the digest always describes exactly the snapshot inspected. A later mutation changes the
next identity. Richard owns reuse/eviction; this module creates no cache. Because digest creation
currently happens in the worker, pre-dispatch cache reuse requires a trusted upstream content
identity and agreement with Richard. The tests prove identity invalidation, not that integrated
caching has already been implemented.

Successful bounded samples are observations, not hypotheses, accepted candidates or proof of a
correct submission. Excerpts may contain sensitive material: send them only to the private
evidence/model path. Do not log `ToolResult`, its repr, or raw worker output. No public logging
is performed by these modules; sanitised failures exclude exception messages and paths.

## Execution boundaries and budgets

| Control | Default / implementation |
| --- | --- |
| Worker wall time | 5 seconds, adjustable within `(0, 120]`; caller deadline may shorten it |
| Queue wait | 2 seconds, adjustable within `(0, 120]`; also capped by caller deadline |
| Snapshot input | 1 MiB, rejected before a large read; no unbounded input history |
| Structured result | 8 KiB serialised JSON; explicit truncation or resource failure |
| Worker stdout + stderr | Combined result budget + 1 KiB protocol overhead; bounded while reading |
| Worker virtual address space | 128 MiB using `RLIMIT_AS`, configurable by trusted code |
| Worker file/core writes | `RLIMIT_FSIZE=0`, `RLIMIT_CORE=0`; operations do not write files |
| Worker open descriptors | `RLIMIT_NOFILE=32` |
| Worker processes | One direct process per admitted call; production worker never forks/spawns |
| Scratch | Empty per-call directory under configured `/tmp` or `/work`, removed on exit |

The worker imports trusted code under isolated Python (`-I -B`) and never imports material as
code. It receives an explicit minimal environment, excluding platform/model secrets, HOME,
user PATH, Python startup hooks and loader environment variables. File roots and path components
are walked with descriptor-relative `O_NOFOLLOW`; nonregular files, including FIFOs, are rejected.
Roots must be under `/work` or `/tmp`, but that check alone does **not** confer challenge authority:
Jerome must supply the appropriate per-challenge directory and keep code/scratch configuration
outside challenge control. Scratch roots are trusted and must not be concurrently renamed by
another actor. This is fixed-function application confinement, not a general OS security sandbox.

The supervisor reads both streams without accumulating discarded output. On overflow, timeout
or cancellation it kills the private process group and waits for the direct worker before
releasing admission and removing scratch. The worker itself has no subprocess or fork path.
This does **not** promise reaping arbitrary double-forked descendants: generic script/shell tools
remain unavailable. A general-backend hanging-command/spawned-child reaping test is still required
if such tools are proposed. No subreaper, nested Docker, privileged capability or bypass is added.

Unsupported platforms fail closed. Missing worker/runtime paths, unavailable resource enforcement,
bad material, source mutation, cancellation, timeout, resource limits and evidence failures return
bounded failures. An unexplained killed worker is `worker_failed`, not a fabricated OOM diagnosis.
There are no automatic retries; Elson chooses a different experiment or defers.

## Shared admission

`Admission.acquire(Cost(...), deadline=..., cancellation=...)` returns a context-managed lease.
It uses FIFO ordering, a finite queue (default 8), total active bound (default 2), heavy-operation
bound (default 1), and aggregate estimated memory/PID reservations. Waiting cancellation is
checked at most every 20 ms. Failed/cancelled queue entries and idempotently released leases
cannot leak reservations. Small inspections use a light cost of one worker plus its configured
memory allowance; no heavy tool is currently dispatched. Other future local tools use this
same pool with configurable `Cost` estimates. Avoid holding a lease while awaiting a model.

Memory and PID pool capacities must be supplied explicitly after reserving measured headroom
for the harness, HTTP clients, evidence and transient peaks. These estimates are admission
accounting, not whole-container enforcement or exact memory prediction. `RLIMIT_AS` limits
worker address space, not aggregate RSS. `worker_peak_rss_bytes` measures the Linux worker only;
container memory/PIDs remain `null` until measured in the exact arena configuration.

`ToolExecutor.execute` acquires internally. Elson should call it directly with remaining budget,
not acquire a second lease around it. Jerome's model/API admission is separate. Queue and work
budgets are independently bounded; `deadline_monotonic` bounds their combined wait/work path.
Trusted sink/OS cleanup latency remains a separate integration consideration.

## Offline verification and measurements

Use the existing shared discovery command:

```sh
python3 -B -m unittest discover -s tests -p 'test_*.py'
python3 -B -m tests.fixtures.aidan.benchmark_tools
```

Fixtures are generated fresh in temporary directories. Ordinary tests use no model, Board,
network, real credentials or challenge material. The opt-in benchmark lives in
`tests/fixtures/aidan/benchmark_tools.py` and reports only synthetic aggregate measurements.

Coverage includes output flooding on both streams, malformed output, direct-worker timeout and
reaping, cancellation, scratch cleanup, no heavy overlap, queue cancellation/overflow, memory/PID/
active admission, path traversal/symlinks/FIFOs, ZIP metadata/expansion limits, sentinel environment
exclusion, unavailable operations, source mutation, identity invalidation and shared result mapping.

Windows portable tests deliberately skip Linux execution; unsupported Windows dispatch itself is tested.
The Windows bundled runtime lacks the foundation's `requests` test dependency; the complete
foundation-plus-tools suite is exercised in Ubuntu, where that dependency is already installed.

Validation on the refreshed strategy baseline:

- Ubuntu/WSL Python 3.14.4: shared discovery passed **168 tests**, no failures or skips
  (125 existing foundation/strategy tests plus 43 new owner tests).
- Windows Python 3.12.14: `python -B -m unittest tests.test_resources
  tests.test_tools_inspection tests.test_tools_executor` discovered 43 tests;
  **24 passed, 19 Linux-only tests skipped**, no failures.
- Whitespace/error check: `git diff --cached --check`.
- Not executed: arena-image inventory, image build/smoke/checker, real evidence-store/cache
  integration, general-command descendant reaping, or live evaluation. Ruff is not installed
  in this environment; no lint pass is claimed.

Synthetic benchmark executed on Ubuntu/WSL, Python 3.14.4, from the Windows-mounted checkout;
five calls per operation, 66,000-byte synthetic text and a ten-member synthetic ZIP:

| Operation | Median total seconds | Maximum worker peak RSS (bytes) | Maximum excerpt bytes |
| --- | ---: | ---: | ---: |
| identify | 0.3660 | 24,035,328 | 361 |
| text | 0.4751 | 24,035,328 | 1,615 |
| hex | 0.4664 | 24,035,328 | 2,381 |
| strings | 0.4903 | 24,035,328 | 2,441 |
| zip_list | 0.5021 | 24,035,328 | 1,274 |

Admission counters returned to zero. Figures include process startup and a synthetic no-op
evidence callback; they are not a comparison against the inherited `run_bash` path. Five
samples are insufficient for a reliable tail-latency claim. RSS is per worker, not aggregate
container memory. Arena peaks, combined PID measurements, idle controller headroom, real sink
cost and image-size changes remain unmeasured. No installed arena tool inventory is inferred.

## Remaining gates and rollback

Before marking this integration ready:

1. Jerome confirms the exact image's Python/rlimit/FD behaviour and trusted root/cancellation seam;
   connect these fixed operations to the Brain without bypassing existing target authority.
2. Richard implements/agrees the bounded sink, retention quotas and cache validity semantics;
   exercise the actual Richard/Aidan mutation path.
3. Elson passes the actual attempt deadline/cancellation and uses one shared local admission pool.
4. Measure idle and combined container memory/PIDs/scratch under the exact image and sandbox;
   tune capacities with controller headroom, then run the module-in-image smoke and checker.
5. General shell/connection tools need their own authorised backend and descendant-reaping proof;
   they are outside this fixed local-inspection slice.

No new dependencies, image build, registry push, live challenge call, flag submission or release
is performed. No higher solve score or monetary saving is claimed from these tests. Rollback is
to close/revert this feature PR; the current Brain never invokes the new modules, so its runtime
behaviour remains the foundation baseline. After future activation, Jerome owns disabling the
adapter and restoring the known-good image.

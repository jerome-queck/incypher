# Runtime state

`agent_ext.runtime_state` is the coordinator's dependency-free SQLite seam. It stores
only trusted numeric challenge IDs, material/instance hashes, enums, bounded counts and
timestamps, SHA-256 fingerprints, and sanitized summaries. Raw commands, output,
connections, credentials and candidate flags are not persisted.

## Integration API

- `rank_briefs(inherited_briefs)` adapts trusted mapping/object briefs and returns the
  same objects in ranked order. `record_challenge_outcome(id, solved, progress,
  failure_class)` checkpoints a ranked challenge; an unranked ID fails closed.
- For typed use, build a `ChallengeBrief` for each inherited trusted brief. Dynamic briefs require an
  instance-generation hash; static briefs reject one.
- `RuntimeState.rank(briefs, now=...)` returns deterministic `RankedChallenge` values.
  Ordering is unsolved, eligible, points plus a small crowd-popularity bonus, progress,
  attempts, static/dynamic, age, then the unchanged numeric challenge ID. The adapter
  accepts only nonnegative exact-integer catalogue `solves` or `solve_count`; absent or
  malformed values contribute zero. Each solve adds 20 ranking points, capped after five
  solves (+100), so challenge points remain material while popular/easier work can move
  ahead of a repeatedly wasted hard attempt. This mutable hint does not enter material or
  evidence scope hashes. Failed slices receive finite 1s then 2s backoff. Production
  refresh/cache policy is authoritative in [strategy.md](strategy.md).
- Build `brief.scope` once a challenge is admitted. `checkpoint_outcome()` atomically
  records its bounded progress and classified `AttemptOutcome` after each final slice.
- `record_challenge_progress()` durably advances a ranked challenge after each accepted
  model turn or new tool observation without incrementing attempts or starting backoff.
  Final and crash checkpoints preserve the greatest already-durable progress value.
- Call `command_seen(scope, raw_command)` before dispatch. After execution,
  `record_command()` stores only scoped command/output fingerprints and a sanitized
  summary. A `False` return means another writer already recorded the exact command.
- `checkpoint_finding(context, Finding(kind, summary))` stores only typed `observed`,
  `hypothesis`, `failed_method`, or `next_step` summaries. Findings are at most 384 UTF-8
  bytes and are rejected before write if they contain candidate, credential, connection,
  address, opaque-secret, or exact transient runtime-secret values. Exact scope-local
  duplicates add no progress.
- `record_observation()` remains the lower-level non-command API. Pass known secret values
  via `sensitive_values`; command and small output values are automatically redacted.
- `project(scope)` returns newline-delimited JSON for Brain: newest applicable records,
  at most 16 and at most 8 KiB. Static evidence requires the same material hash;
  dynamic evidence additionally requires the same instance-generation hash.
- `scope_key(ctx)` derives a key directly from trusted `AttemptContext` fields.
  `lookup`/`lookup_command`, `record`, and `project`/`project_memory` accept either that
  context or `Scope`.

The database defaults to `/work/runtime-state.sqlite3`, uses WAL plus full synchronous
commits, short transactions and bounded lock waits. `checkpoint()` requests a passive
WAL checkpoint. Reads tolerate malformed/oversized rows by omitting them. Storage and
lock failures raise payload-free `RuntimeStateError`; callers should fail closed rather
than execute an undeduplicated command or lose a required outcome checkpoint.

Limits: 4,096 trusted briefs per rank call, 256 observations per scope, 4,096 total
observations, 512 UTF-8 bytes per generic summary (384 for findings), 64 KiB per raw command accepted for hashing,
16 projected records and 8 KiB projected text.

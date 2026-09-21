# Evidence, candidate, and outcome policy

Richard's modules are private, dependency-free helpers behind the shared `Brain` seam. They do
not call a model, execute a tool, contact the Board, submit a flag, or replace the inherited
`/work/results.json` writer.

## Scope and evidence

Evidence is reusable only when run, phase, challenge, and material identity match. Instance-bound
records additionally require the same known instance generation; an unknown required value is not
a wildcard. Attempt identity is provenance and does not defeat candidate deduplication. A host
profile revision alone does not invalidate deterministic material evidence unless the recorded
procedure explicitly depends on it.

Observations retain execution status and evidence completeness separately from interpretation.
Timeouts, resource limits, unavailable tools, policy blocks, malformed output, and interruption
remain unresolved. Only a completed meaningful test may support or contradict a hypothesis, and a
negative result is limited to its recorded coverage.

`ScopedMemory.decision_packet` emits deterministic UTF-8-bounded JSON. Hypotheses and proposed
experiments remain labelled unverified. Private endpoints, credentials, candidate values, and
candidate-derived public identifiers are rejected. Overflow of the mandatory safe envelope is a
typed failure; optional records are omitted with explicit counts.

## Qualification and verification

Qualification checks current scope, the integration owner's actual format validator, provenance,
evidence completeness, and duplicate state. It does not imply local verification. Local
verification requires a named meaningful postcondition or independent re-derivation with complete
evidence. Flag shape, model agreement, and a zero exit status cannot create a verification pass or
platform acceptance.

## Submission state

`SubmissionStateStore` uses SQLite under an integration-selected writable path. Candidate bytes
are never exposed in diagnostics. A keyed private identity covers exact candidate bytes and the
agreed scope; no whitespace, case, or encoding normalization is applied.

The single sender must durably reserve an intent, durably mark `dispatch_possible`, and only then
invoke Jerome's trusted callback. Before that marker, proven non-dispatch may be resumed. After it,
a missing response requires reconciliation and never authorizes an automatic resend. Classified
outcome events are idempotent. A delayed transport error cannot erase attributable acceptance;
contradictory authoritative outcomes become an explicit conflict. Account-level `already_solved`
does not prove acceptance of this candidate. Synthetic acceptance never contributes to live-success
counts.

## Result projection and durability limits

`InternalResultProjector` is labelled `internal-result-fixture-v1`; it is not the organiser schema.
It stores committed fixture entries in the same SQLite file when configured that way, writes a
same-directory temporary file, fsyncs it where supported, and atomically replaces the projection.
Missing/stale output is rebuilt from committed rows. Interruption after replacement but before
publication bookkeeping is reconciled without creating a new submission intent.

Tests cover controlled process-restart and write-boundary behavior on the local filesystem. They
do not prove cross-container or power-loss durability. The official result mapping, reconciliation
capability, raw helper outcome mapping, and one-writer integration remain Jerome-owned gates.

# Model gateway foundation

`agent_ext/model_gateway.py` is the production Brain's model-call and cost-admission
boundary. Brain passes the exact trusted, runtime-injected endpoint, credential and model
identity. Credentials stay in memory and are excluded from representations, errors and
ledger storage. The inherited harness still owns challenge lifecycle and official results.

Optional request fields are allow-listed by an explicit `ProviderCapabilities` value.
Opaque providers therefore receive only `model` and `messages`. A provider known to
support an OpenRouter-shaped `reasoning` field may receive `{"effort":"high"}`; a
provider declaring `reasoning_effort` receives the scalar form. No model fallback or
identity substitution occurs. The gateway performs one finite-timeout transport call
and never automatically retries a paid request.

The gateway enforces its own caller-return deadline with a daemon transport worker even
when an injected transport ignores its timeout argument. Python cannot safely cancel a
blocked thread or prove whether the remote provider charged/completed the request. Such
a timeout is therefore explicitly unresolved: keep its budget reservation unsettled.
The same gateway rejects another call while that worker remains alive. Process exit is
the only hard cancellation boundary for a permanently blocked transport.

Responses retain the assistant message, observed model, token counts and cost. Cost is
classified as `measured`, `estimated` or `unknown`; missing or malformed usage is not
silently converted to zero. Provider error bodies are discarded. The integration owner
must supply a transport that enforces the passed timeout and bounds network behavior.

`BudgetLedger` durably reserves a conservative maximum before dispatch. Atomic SQLite
transactions serialize concurrent admission. Unknown cost remains reserved across
restart; estimated cost may later be replaced by measured cost; repeated identical
settlement is idempotent. A reservation can be released only through the explicit
never-dispatched path. Records have a configured hard count limit and are retained for
reconciliation, so capacity requires operator handling rather than unsafe pruning.
The total limit is stored with the ledger and a restart using a different limit fails.

Brain uses [provider discovery](provider-discovery.md) for the exact OpenRouter catalogue;
opaque providers retain the compatible tool fields but receive no inferred reasoning or
temperature. Known catalogue prices provide conservative estimates; response usage wins
when measured. The durable ledger defaults to `/work/model-budget.sqlite3`, an USD 85
admission ceiling and USD 1 opaque-price reservations, leaving USD 15 of the competition
allowance unadmitted for recovery/verification. Optional environment tuning is bounded;
Day 2 still requires only the organiser's injected model triplet.

Limits: there is no generic provider meter or generation-ID reconciliation in the image;
the SQLite file is not encrypted; a timed-out transport thread cannot be forcibly killed;
and a missing usage record remains fully reserved. A late measured cost may exceed its
reservation and exhaust the ledger; it is recorded rather than hidden. Scheduling and
cross-attempt recovery remain separate work.

All monetary decimals are nonnegative and bounded to 64 serialized characters, 28
significant digits, and an exponent from -18 through 18. Out-of-bound provider costs
are classified unknown; out-of-bound ledger inputs are rejected. This bounds parsing,
comparison and durable representation without asserting provider pricing precision.

# Model gateway foundation

`agent_ext/model_gateway.py` is an unconnected foundation; the inherited Brain remains
the production model caller. Integration must pass the exact trusted, runtime-injected
endpoint, credential and model identity. Credentials stay in memory and are excluded
from representations, errors and ledger storage.

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

Limits: this PR does not discover capabilities, pricing or provider meters; estimate
cost; reconcile generation IDs; retry; encrypt its local SQLite file; or wire Brain.
Callers must keep the ledger in ignored private runtime storage and choose conservative
reservation bounds. A late measured cost may exceed its reservation and exhaust the
ledger; it is recorded rather than hidden.

All monetary decimals are nonnegative and bounded to 64 serialized characters, 28
significant digits, and an exponent from -18 through 18. Out-of-bound provider costs
are classified unknown; out-of-bound ledger inputs are rejected. This bounds parsing,
comparison and durable representation without asserting provider pricing precision.

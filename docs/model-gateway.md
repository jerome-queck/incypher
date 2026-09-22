# Model gateway foundation

`agent_ext/model_gateway.py` is the production Brain's model-call and cost-admission
boundary. Brain passes the exact trusted, runtime-injected endpoint, credential and model
identity. Credentials stay in memory and are excluded from representations, errors and
ledger storage. The inherited harness still owns challenge lifecycle and official results.

Optional request fields are allow-listed by an explicit `ProviderCapabilities` value.
The active Brain retains the inherited compatible endpoint's core tool fields and one
legacy completion limit for opaque providers, but infers no reasoning or temperature.
A provider known to support an OpenRouter-shaped `reasoning` field may receive
`{"effort":"high"}` or, for the image-owned Luna/Sol route, verified `xhigh`;
a provider declaring `reasoning_effort` receives the scalar form. An explicit
organiser-injected runtime model is never routed. The Day-2 image-default
discovery policy may resolve a different catalogue-advertised model before
the first request; that resolved identity is then exact. The image-owned
`xhigh` allowlist contains only Luna and Sol: exact real-key tool requests
for each succeeded on 22 Sep. Catalogue metadata alone advertises the
reasoning field, not permitted effort values; never infer `xhigh` for another
model from that field. The image-owned
OpenRouter/Luna policy chooses the exact `openai/gpt-5.6-sol` model at a new slice
after at least two trusted
unsolved slices only when Sol's exact catalogue entry supports tools and
reasoning, has known pricing, is not ahead of the spend target and its
conservative reservation fits. An empty `LLM_HARD_MODEL` disables Sol;
any other value disables this route. If an interleaved ledger reservation
denies the first Sol call, Brain tries Luna before dispatch. Otherwise Luna
remains selected. Each slice
uses one model for all turns. The gateway performs one finite-timeout transport call
and never automatically retries a paid request.

The gateway enforces its own caller-return deadline with a daemon transport worker even
when an injected transport ignores its timeout argument. Python cannot safely cancel a
blocked thread or prove whether the remote provider charged/completed the request. Such
a timeout is therefore explicitly unresolved: keep its budget reservation unsettled.
The same gateway rejects another call while that worker remains alive. Process exit is
the only hard cancellation boundary for a permanently blocked transport, so the arena
coordinator stops that process instead of starting another challenge dispatch.

Responses retain the assistant message, observed model, token counts and cost. Cost is
classified as `measured`, `estimated` or `unknown`; missing or malformed usage is not
silently converted to zero. Provider error bodies are discarded. The active HTTP
transport streams and closes responses, rejects declared or observed catalogue bodies
above 2 MiB and completion bodies above 8 MiB, and applies caller-return deadlines. Any
alternate injected transport must still enforce the passed timeout and bounds.

`BudgetLedger` durably reserves a conservative maximum before dispatch. Atomic SQLite
transactions serialize concurrent admission. Unknown cost remains reserved across
restart; estimated cost may later be replaced by measured cost; repeated identical
settlement is idempotent. A reservation can be released only through the explicit
never-dispatched path. Records have a configured hard count limit and are retained for
reconciliation, so capacity requires operator handling rather than unsafe pruning.
The total limit is stored with the ledger. A restart may atomically lower it
without discarding calls or resetting its pacing clock, including below current
committed spend (which closes admission). Raising it fails. Existing instances
also read the lower durable ceiling at admission and snapshot time, so a
concurrent old instance cannot reopen budget capacity. This protects a
reconfigured Day-1 image whether `/work` persists or starts fresh; a new
ledger still needs a cap no greater than the provider balance actually left.

Brain uses [provider discovery](provider-discovery.md) for the exact OpenRouter catalogue;
opaque providers retain the compatible tool fields but receive no inferred reasoning or
temperature. Known catalogue prices provide conservative estimates; response usage wins
when measured. Exact OpenRouter catalogue calls reserve at 3× listed worst-case
prompt/completion cost (other known prices at 1.5×) because a measured BYOK
Sol route billed upstream at twice the catalogue list price. For a BYOK
response, the ledger counts upstream inference cost plus any OpenRouter charge;
`usage.cost=0` alone is not free inference. Missing upstream cost remains
unresolved at the full reservation instead of settling zero or a lower list
estimate. This bounds admission but cannot mathematically rule out one
provider charge above its reservation. The durable ledger defaults to `/work/model-budget.sqlite3`, an USD 85
admission ceiling and USD 1 opaque-price reservations, leaving USD 15 of the competition
allowance unadmitted for recovery/verification. The ceiling cannot exceed USD 85; opaque
reservations must remain USD 0.05–5. Optional environment tuning is bounded;
Day 2 requires the organiser's injected endpoint/key plus the authoritative
[provider-discovery policy](provider-discovery.md).

The ledger also stores its first-start wall time. Arena mode compares durable measured,
estimated and unresolved spend, plus the next conservative reservation, with a linear
budget target over `MODEL_BUDGET_WINDOW_SECONDS` (default 23,400 seconds). It requests
high reasoning while starting, on pace or behind, and medium while materially ahead;
completion capacity stays 4,096 by default. Only an exact OpenRouter model whose
catalogue advertises a valid >=8,192-token ceiling and known price may request
8,192 when adaptive pacing remains behind target after pricing the expanded next
call. Its full conservative reservation is taken before dispatch. Fixed-high
local work, other postures and opaque/compatible Day-2 models remain at 4,096.
This is a bounded opportunity for deeper work, not proof of better solves or
an instruction to spend the remaining balance. The reasoning field is sent
only when exact-model discovery advertises `reasoning` or `reasoning_effort`. Local
practice, validation and direct Brain use default to fixed high; only the arena wrapper
enables adaptive pacing when no explicit mode was supplied. Pacing changes request
intensity; the image-owned route above may also select a priced model between
slices. It never changes the durable dollar ceiling.
Each model-facing budget notice reports both the durable average spend per elapsed minute
and the target rate; the posture compares cumulative projected spend with the target.

Limits: there is no generic provider meter or generation-ID reconciliation in the image;
the SQLite file is not encrypted; a timed-out transport thread cannot be forcibly killed;
and a missing usage record remains fully reserved. A late measured cost may exceed its
reservation and exhaust the ledger; it is recorded rather than hidden. Scheduling and
cross-attempt recovery remain separate work.

All monetary decimals are nonnegative and bounded to 64 serialized characters, 28
significant digits, and an exponent from -18 through 18. Out-of-bound provider costs
are classified unknown; out-of-bound ledger inputs are rejected. This bounds parsing,
comparison and durable representation without asserting provider pricing precision.

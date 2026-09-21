# Provider discovery and category playbooks

`agent_ext.provider_discovery` recognizes only the exact
`https://openrouter.ai/api/v1/chat/completions` endpoint. Similar hosts, alternate
paths, query strings, credentials in URLs and non-HTTPS endpoints are opaque providers.
Opaque, unavailable, malformed or missing-model discovery returns empty capabilities
and unknown pricing; it never selects a different model.

For the exact endpoint, `discover_provider(identity, fetch_json, cache=None)` calls the
injected bounded fetcher once with the public models URL, a five-second timeout and a
2 MiB response bound. It selects only the exact configured model ID. The result maps
explicit supported optional parameters into `ProviderCapabilities` and parses bounded
catalogue prompt/completion/request prices. Catalogue pricing provenance is explicit;
it is not a provider charge or event budget meter.
The exact entry's bounded `canonical_slug` is retained as the only alternate observed
identity accepted for that configured model; opaque providers require exact identity.

`estimate_max_cost` prices supplied prompt and completion token upper bounds at the
uncached catalogue rates plus fixed request cost. It returns unknown when pricing or
bounded token counts are unavailable. It does not cover undisclosed tiering, provider
fallbacks, BYOK charges, images or late usage, so integration must reserve conservatively
and prefer measured response cost for settlement.

`DiscoveryCache` is an in-memory bounded TTL cache keyed only by exact model ID. It never
stores the API key, endpoint or raw provider response/error. Discovery has no network
implementation of its own; integration owns the bounded fetch transport.

Day 2 supplies endpoint/key but no model. Only when the entrypoint marks its image default
as discoverable, `discover_served_model` derives the same-origin HTTPS `/models` URL and
performs one authenticated bounded lookup. The exact image default wins when served;
otherwise the first explicitly tool-capable entry wins, or the provider's first entry when
capability metadata is absent. Malformed, empty, unavailable or unsafe catalogues stop
before model dispatch; the image never sends an unadvertised default. Explicit Day-1/runtime
models never substitute. This is the authoritative Day-2 selection policy.

`agent_ext.playbooks.playbook_for(category)` returns one compact deterministic hint for
the exact trusted category labels web, pwn, network, crypto, rev, forensics, misc or
unknown. One exact leading `(Practice)` marker from trusted organiser metadata is
removed; compound or otherwise unknown labels map to unknown. Playbooks grant no target
or submission authority and require no specialist model call.

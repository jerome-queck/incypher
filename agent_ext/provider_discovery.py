"""Bounded, exact-identity provider capability and pricing discovery."""

from __future__ import annotations

import json
import threading
import time
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .model_gateway import ProviderCapabilities, ProviderIdentity


_OPENROUTER_CHAT_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"
_FETCH_TIMEOUT_SECONDS = 5.0
_MAX_CATALOGUE_BYTES = 2 * 1024 * 1024
_MAX_MODELS = 4096
_MAX_PARAMETERS = 64
_MAX_TEXT = 512
_MAX_DECIMAL_TEXT = 64
_MAX_DECIMAL_DIGITS = 28
_MIN_DECIMAL_EXPONENT = -18
_MAX_DECIMAL_EXPONENT = 18

_GATEWAY_PARAMETERS = frozenset(
    {
        "temperature",
        "max_tokens",
        "max_completion_tokens",
        "reasoning",
        "reasoning_effort",
        "tools",
        "tool_choice",
    }
)


FetchJSON = Callable[[str, float, int], Mapping[str, Any] | bytes]


@dataclass(frozen=True)
class ModelPricing:
    """Catalogue-advertised per-token and fixed request prices."""

    prompt_per_token: Decimal
    completion_per_token: Decimal
    request_cost: Decimal = Decimal(0)
    provenance: str = "openrouter_catalogue"

    def __post_init__(self) -> None:
        for name in ("prompt_per_token", "completion_per_token", "request_cost"):
            value = getattr(self, name)
            if _decimal(value) != value:
                raise ValueError(f"{name} must be a bounded nonnegative decimal")
        if self.provenance != "openrouter_catalogue":
            raise ValueError("pricing provenance must identify the catalogue")


@dataclass(frozen=True)
class DiscoveryResult:
    capabilities: ProviderCapabilities
    pricing: ModelPricing | None
    source: str
    provenance: str
    canonical_model: str | None = None
    max_completion_tokens: int | None = None

    def __post_init__(self) -> None:
        ceiling = self.max_completion_tokens
        if ceiling is not None and (
            type(ceiling) is not int or not 1 <= ceiling <= 1_000_000
        ):
            raise ValueError("completion ceiling must be a bounded positive integer")


_OPAQUE = DiscoveryResult(ProviderCapabilities(), None, "opaque", "unknown", None)


class DiscoveryCache:
    """Small TTL cache containing model IDs and public catalogue results only."""

    def __init__(self, *, max_entries: int = 32, ttl_seconds: float = 3600.0):
        if type(max_entries) is not int or not 0 < max_entries <= 1024:
            raise ValueError("max_entries must be between 1 and 1024")
        if not 0 < ttl_seconds <= 86_400:
            raise ValueError("ttl_seconds must be finite and at most one day")
        self.max_entries = max_entries
        self.ttl_seconds = float(ttl_seconds)
        self._entries: OrderedDict[str, tuple[float, DiscoveryResult]] = OrderedDict()
        self._lock = threading.Lock()

    def get(self, model: str) -> DiscoveryResult | None:
        now = time.monotonic()
        with self._lock:
            item = self._entries.get(model)
            if item is None:
                return None
            created, result = item
            if now - created > self.ttl_seconds:
                del self._entries[model]
                return None
            self._entries.move_to_end(model)
            return result

    def put(self, model: str, result: DiscoveryResult) -> None:
        with self._lock:
            self._entries[model] = (time.monotonic(), result)
            self._entries.move_to_end(model)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def __repr__(self) -> str:
        return f"DiscoveryCache(entries={len(self._entries)}, max_entries={self.max_entries})"


def is_exact_openrouter_chat(endpoint: str) -> bool:
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return False
    return (
        endpoint == _OPENROUTER_CHAT_URL
        and parsed.scheme == "https"
        and parsed.hostname == "openrouter.ai"
        and parsed.port is None
        and parsed.username is None
        and parsed.password is None
        and not parsed.query
        and not parsed.fragment
    )


def _decimal(value: Any) -> Decimal | None:
    if type(value) not in {str, int, float, Decimal} or isinstance(value, bool):
        return None
    if type(value) is int and value.bit_length() > 220:
        return None
    try:
        text = str(value)
    except (ValueError, OverflowError):
        return None
    if not text or len(text) > _MAX_DECIMAL_TEXT:
        return None
    try:
        amount = Decimal(text)
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    parts = amount.as_tuple()
    if len(parts.digits) > _MAX_DECIMAL_DIGITS:
        return None
    if not _MIN_DECIMAL_EXPONENT <= parts.exponent <= _MAX_DECIMAL_EXPONENT:
        return None
    return amount


def _unknown_openrouter() -> DiscoveryResult:
    return DiscoveryResult(
        ProviderCapabilities(), None, "openrouter_catalogue", "unknown", None
    )


def _parse_document(raw: Mapping[str, Any] | bytes) -> Mapping[str, Any] | None:
    if isinstance(raw, bytes):
        if len(raw) > _MAX_CATALOGUE_BYTES:
            return None
        try:
            raw = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return None
    return raw if isinstance(raw, Mapping) else None


def _parse_capabilities(model: Mapping[str, Any]) -> ProviderCapabilities:
    parameters = model.get("supported_parameters")
    if not isinstance(parameters, list) or len(parameters) > _MAX_PARAMETERS:
        return ProviderCapabilities()
    if any(not isinstance(item, str) or len(item) > _MAX_TEXT for item in parameters):
        return ProviderCapabilities()
    return ProviderCapabilities(frozenset(parameters) & _GATEWAY_PARAMETERS)


def _parse_completion_ceiling(
    model: Mapping[str, Any], capabilities: ProviderCapabilities
) -> int | None:
    if not capabilities.optional_parameters & {"max_tokens", "max_completion_tokens"}:
        return None
    provider = model.get("top_provider")
    value = provider.get("max_completion_tokens") if isinstance(provider, Mapping) else None
    return value if type(value) is int and 1 <= value <= 1_000_000 else None


def _parse_pricing(model: Mapping[str, Any]) -> ModelPricing | None:
    pricing = model.get("pricing")
    if not isinstance(pricing, Mapping):
        return None
    prompt = _decimal(pricing.get("prompt"))
    completion = _decimal(pricing.get("completion"))
    if prompt is None or completion is None:
        return None
    request_raw = pricing.get("request", "0")
    request = _decimal(request_raw)
    if request is None:
        return None
    return ModelPricing(prompt, completion, request)


def discover_provider(
    identity: ProviderIdentity,
    fetch_json: FetchJSON,
    cache: DiscoveryCache | None = None,
) -> DiscoveryResult:
    """Discover the exact configured OpenRouter model, or return opaque unknown.

    ``fetch_json`` is injected and receives ``(url, timeout_seconds, max_bytes)``.
    It must perform at most one bounded fetch. Raw errors and credentials are never
    retained. No alternate model entry is selected when the exact ID is absent.
    """
    if not isinstance(identity, ProviderIdentity):
        raise ValueError("ProviderIdentity required")
    if not callable(fetch_json):
        raise ValueError("fetch_json must be callable")
    if not is_exact_openrouter_chat(identity.endpoint):
        return _OPAQUE
    if cache is not None:
        cached = cache.get(identity.model)
        if cached is not None:
            return cached
    try:
        raw = fetch_json(
            _OPENROUTER_MODELS_URL, _FETCH_TIMEOUT_SECONDS, _MAX_CATALOGUE_BYTES
        )
    except Exception:
        result = _unknown_openrouter()
    else:
        document = _parse_document(raw)
        data = document.get("data") if document is not None else None
        if not isinstance(data, list) or len(data) > _MAX_MODELS:
            result = _unknown_openrouter()
        else:
            exact: Mapping[str, Any] | None = None
            malformed = False
            for item in data:
                if not isinstance(item, Mapping):
                    malformed = True
                    break
                model_id = item.get("id")
                if not isinstance(model_id, str) or len(model_id) > _MAX_TEXT:
                    malformed = True
                    break
                if model_id == identity.model:
                    exact = item
                    break
            if malformed or exact is None:
                result = _unknown_openrouter()
            else:
                canonical = exact.get("canonical_slug")
                if not isinstance(canonical, str) or not canonical or len(canonical) > _MAX_TEXT:
                    canonical = None
                capabilities = _parse_capabilities(exact)
                result = DiscoveryResult(
                    capabilities,
                    _parse_pricing(exact),
                    "openrouter_catalogue",
                    "openrouter_catalogue",
                    canonical,
                    _parse_completion_ceiling(exact, capabilities),
                )
    if cache is not None and result.provenance != "unknown":
        cache.put(identity.model, result)
    return result


def _compatible_models_url(endpoint: str) -> str | None:
    try:
        parsed = urlsplit(endpoint)
    except ValueError:
        return None
    suffix = "/chat/completions"
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
        or not parsed.path.endswith(suffix)
    ):
        return None
    path = parsed.path[:-len(suffix)] + "/models"
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def discover_served_model(
    identity: ProviderIdentity,
    fetch_json: FetchJSON,
) -> tuple[ProviderIdentity, DiscoveryResult]:
    """Resolve an image default against one authenticated compatible catalogue.

    Exact configured identity wins when advertised. Otherwise the provider's first
    explicitly tool-capable model wins; catalogues without capability metadata use
    their first model. Any unavailable or malformed input preserves the image default.
    """
    if not isinstance(identity, ProviderIdentity):
        raise ValueError("ProviderIdentity required")
    if not callable(fetch_json):
        raise ValueError("fetch_json must be callable")
    models_url = _compatible_models_url(identity.endpoint)
    if models_url is None:
        return identity, _OPAQUE
    try:
        raw = fetch_json(models_url, _FETCH_TIMEOUT_SECONDS, _MAX_CATALOGUE_BYTES)
    except Exception:
        return identity, _OPAQUE
    document = _parse_document(raw)
    data = document.get("data") if document is not None else None
    if not isinstance(data, list) or not data or len(data) > _MAX_MODELS:
        return identity, _OPAQUE
    entries: list[Mapping[str, Any]] = []
    for item in data:
        if not isinstance(item, Mapping):
            return identity, _OPAQUE
        model_id = item.get("id")
        if not isinstance(model_id, str) or not model_id or len(model_id) > _MAX_TEXT:
            return identity, _OPAQUE
        entries.append(item)
    selected = next(
        (item for item in entries if item.get("id") == identity.model), None
    )
    if selected is None:
        tool_capable = []
        unspecified = []
        for item in entries:
            parameters = item.get("supported_parameters")
            if parameters is None:
                unspecified.append(item)
            elif (
                isinstance(parameters, list)
                and len(parameters) <= _MAX_PARAMETERS
                and all(isinstance(value, str) and len(value) <= _MAX_TEXT
                        for value in parameters)
                and "tools" in parameters
            ):
                tool_capable.append(item)
        candidates = tool_capable or unspecified
        if not candidates:
            return identity, _OPAQUE
        selected = candidates[0]
    model = selected["id"]
    canonical = selected.get("canonical_slug")
    if not isinstance(canonical, str) or not canonical or len(canonical) > _MAX_TEXT:
        canonical = None
    resolved = ProviderIdentity(identity.endpoint, identity.api_key, model)
    result = DiscoveryResult(
        _parse_capabilities(selected),
        None,
        "compatible_catalogue",
        "compatible_catalogue",
        canonical,
    )
    return resolved, result


def estimate_max_cost(
    pricing: ModelPricing | None,
    prompt_tokens: int,
    completion_tokens: int,
) -> Decimal | None:
    """Estimate a maximum using uncached prompt and completion token bounds."""
    if pricing is None or not isinstance(pricing, ModelPricing):
        return None
    if (
        type(prompt_tokens) is not int
        or type(completion_tokens) is not int
        or prompt_tokens < 0
        or completion_tokens < 0
        or prompt_tokens > 10_000_000
        or completion_tokens > 10_000_000
    ):
        return None
    estimate = (
        pricing.request_cost
        + pricing.prompt_per_token * prompt_tokens
        + pricing.completion_per_token * completion_tokens
    )
    return _decimal(estimate)

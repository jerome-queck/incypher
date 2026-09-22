"""Provider-neutral chat request normalization and durable cost admission.

Brain wires this module to the trusted, injected provider identity and explicit
capability discovery. The gateway performs one transport attempt; retry policy belongs
to a later coordinator seam.
"""

from __future__ import annotations

import json
import math
import os
import queue
import sqlite3
import threading
import time
from collections.abc import Callable, Mapping, Sequence
from contextlib import closing
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from types import MappingProxyType
from typing import Any


_MAX_IDENTIFIER = 256
_MAX_RESPONSE_BYTES = 8 * 1024 * 1024
_MAX_DECIMAL_CHARACTERS = 64
_MAX_DECIMAL_DIGITS = 28
_MIN_DECIMAL_EXPONENT = -18
_MAX_DECIMAL_EXPONENT = 18


class CostProvenance(str, Enum):
    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNKNOWN = "unknown"


class GatewayError(RuntimeError):
    """A bounded, credential-free provider failure."""


class GatewayTimeout(GatewayError):
    """The caller deadline elapsed; provider completion and cost are unknown."""

    dispatch_unresolved = True


class LedgerCapacityError(RuntimeError):
    pass


@dataclass(frozen=True)
class ProviderIdentity:
    endpoint: str
    api_key: str
    model: str

    def __post_init__(self) -> None:
        for name in ("endpoint", "api_key", "model"):
            value = getattr(self, name)
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must be nonempty")
        if len(self.endpoint) > 4096 or len(self.api_key) > 8192 or len(self.model) > 512:
            raise ValueError("provider identity field is too long")

    def __repr__(self) -> str:
        return (
            "ProviderIdentity(endpoint='[redacted]', api_key='[redacted]', "
            f"model={self.model!r})"
        )


@dataclass(frozen=True)
class ProviderCapabilities:
    """Optional request keys explicitly known to be supported.

    Unknown keys are rejected rather than forwarded. Tool fields are explicit
    capabilities too: an opaque endpoint receives no optional tool schema.
    """

    optional_parameters: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        allowed = {
            "temperature", "max_tokens", "max_completion_tokens", "reasoning",
            "reasoning_effort", "tools", "tool_choice",
        }
        if not isinstance(self.optional_parameters, frozenset):
            object.__setattr__(self, "optional_parameters", frozenset(self.optional_parameters))
        if not self.optional_parameters <= allowed:
            raise ValueError("unrecognized provider capability")


@dataclass(frozen=True)
class RequestOptions:
    temperature: float | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = None

    def __post_init__(self) -> None:
        if self.temperature is not None:
            if isinstance(self.temperature, bool) or not isinstance(
                self.temperature, (int, float)
            ):
                raise ValueError("temperature must be a finite number")
            try:
                finite = math.isfinite(self.temperature)
            except OverflowError:
                finite = False
            if not finite:
                raise ValueError("temperature must be a finite number")
        if self.max_tokens is not None and (
            type(self.max_tokens) is not int or self.max_tokens <= 0
        ):
            raise ValueError("max_tokens must be positive")
        if self.reasoning_effort is not None and self.reasoning_effort not in {
            "minimal", "low", "medium", "high", "xhigh", "max", "ultra"
        }:
            raise ValueError("unsupported reasoning effort")


@dataclass(frozen=True)
class UsageMetadata:
    prompt_tokens: int | None
    completion_tokens: int | None
    total_tokens: int | None
    cost: Decimal | None
    cost_provenance: CostProvenance
    cached_prompt_tokens: int | None = None
    reasoning_tokens: int | None = None


@dataclass(frozen=True)
class ModelResponse:
    message: Mapping[str, Any]
    observed_model: str | None
    usage: UsageMetadata


Transport = Callable[[str, Mapping[str, str], bytes, float], bytes | Mapping[str, Any]]


def build_request(
    identity: ProviderIdentity,
    messages: Sequence[Mapping[str, Any]],
    capabilities: ProviderCapabilities,
    options: RequestOptions = RequestOptions(),
    *,
    tools: Sequence[Mapping[str, Any]] | None = None,
    tool_choice: str | None = None,
) -> dict[str, Any]:
    """Build a request without changing the injected model identity."""
    if not isinstance(identity, ProviderIdentity):
        raise ValueError("ProviderIdentity required")
    if not isinstance(capabilities, ProviderCapabilities):
        raise ValueError("ProviderCapabilities required")
    if not messages:
        raise ValueError("at least one message is required")
    normalized_messages: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, Mapping) or not isinstance(message.get("role"), str):
            raise ValueError("each message requires a string role")
        normalized_messages.append(dict(message))

    payload: dict[str, Any] = {"model": identity.model, "messages": normalized_messages}
    supported = capabilities.optional_parameters
    if options.temperature is not None and "temperature" in supported:
        payload["temperature"] = options.temperature
    if options.max_tokens is not None:
        if "max_completion_tokens" in supported:
            payload["max_completion_tokens"] = options.max_tokens
        elif "max_tokens" in supported:
            payload["max_tokens"] = options.max_tokens
    if options.reasoning_effort is not None:
        if "reasoning" in supported:
            payload["reasoning"] = {"effort": options.reasoning_effort}
        elif "reasoning_effort" in supported:
            payload["reasoning_effort"] = options.reasoning_effort
    if tools is not None and "tools" in supported:
        if not isinstance(tools, Sequence) or isinstance(tools, (str, bytes)):
            raise ValueError("tools must be a sequence")
        normalized_tools = []
        for tool in tools:
            if not isinstance(tool, Mapping):
                raise ValueError("each tool must be an object")
            normalized_tools.append(dict(tool))
        payload["tools"] = normalized_tools
    if tool_choice is not None and "tool_choice" in supported:
        if not isinstance(tool_choice, str) or not tool_choice:
            raise ValueError("tool_choice must be nonempty")
        payload["tool_choice"] = tool_choice
    return payload


def _nonnegative_int(value: Any) -> int | None:
    return value if type(value) is int and value >= 0 else None


def _money(value: Any) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    if type(value) not in {str, int, float, Decimal}:
        return None
    # Avoid invoking arbitrary __str__ methods and reject obviously oversized
    # integers before Python's configurable integer-to-string conversion limit.
    if type(value) is int and value.bit_length() > 220:
        return None
    try:
        serialized = str(value)
    except (ValueError, OverflowError):
        return None
    if len(serialized) > _MAX_DECIMAL_CHARACTERS:
        return None
    try:
        amount = Decimal(serialized)
    except (InvalidOperation, ValueError):
        return None
    if not amount.is_finite() or amount < 0:
        return None
    decimal_tuple = amount.as_tuple()
    if len(decimal_tuple.digits) > _MAX_DECIMAL_DIGITS:
        return None
    if not _MIN_DECIMAL_EXPONENT <= decimal_tuple.exponent <= _MAX_DECIMAL_EXPONENT:
        return None
    return amount


def normalize_response(
    raw: Mapping[str, Any], *, estimated_cost: Decimal | str | None = None
) -> ModelResponse:
    """Normalize common Chat Completions output; tolerate bad usage metadata."""
    try:
        choice = raw["choices"][0]  # type: ignore[index]
        message = choice["message"]
    except (KeyError, IndexError, TypeError):
        raise GatewayError("provider returned a malformed response") from None
    if not isinstance(message, Mapping) or not isinstance(message.get("role"), str):
        raise GatewayError("provider returned a malformed response")

    usage = raw.get("usage")
    usage = usage if isinstance(usage, Mapping) else {}
    router_cost = _money(usage.get("cost"))
    if usage.get("is_byok") is True:
        details = usage.get("cost_details")
        upstream = (
            _money(details.get("upstream_inference_cost"))
            if isinstance(details, Mapping) else None
        )
        # OpenRouter reports zero charged cost for BYOK calls while the
        # provider still bills upstream inference. Count both when present.
        measured = (
            _money(upstream + (router_cost or Decimal(0)))
            if upstream is not None else None
        )
    else:
        measured = router_cost
    estimate = _money(estimated_cost)
    if measured is not None:
        cost, provenance = measured, CostProvenance.MEASURED
    elif estimate is not None and usage.get("is_byok") is not True:
        cost, provenance = estimate, CostProvenance.ESTIMATED
    else:
        cost, provenance = None, CostProvenance.UNKNOWN
    observed_model = raw.get("model")
    if not isinstance(observed_model, str) or not observed_model:
        observed_model = None
    return ModelResponse(
        message=MappingProxyType(dict(message)),
        observed_model=observed_model,
        usage=UsageMetadata(
            _nonnegative_int(usage.get("prompt_tokens")),
            _nonnegative_int(usage.get("completion_tokens")),
            _nonnegative_int(usage.get("total_tokens")),
            cost,
            provenance,
            _nonnegative_int(
                usage.get("prompt_tokens_details", {}).get("cached_tokens")
                if isinstance(usage.get("prompt_tokens_details"), Mapping)
                else None
            ),
            _nonnegative_int(
                usage.get("completion_tokens_details", {}).get("reasoning_tokens")
                if isinstance(usage.get("completion_tokens_details"), Mapping)
                else None
            ),
        ),
    )


class ModelGateway:
    def __init__(self, transport: Transport, *, timeout_seconds: float = 180.0):
        if not callable(transport):
            raise ValueError("transport must be callable")
        if not 0 < timeout_seconds <= 600:
            raise ValueError("timeout must be finite and at most 600 seconds")
        self.transport = transport
        self.timeout_seconds = float(timeout_seconds)
        self._dispatch_lock = threading.Lock()
        self._active_dispatch: threading.Thread | None = None

    @property
    def dispatch_active(self) -> bool:
        """Whether a transport worker is still running after dispatch."""
        with self._dispatch_lock:
            return self._active_dispatch is not None and self._active_dispatch.is_alive()

    def complete(
        self,
        identity: ProviderIdentity,
        messages: Sequence[Mapping[str, Any]],
        capabilities: ProviderCapabilities,
        options: RequestOptions = RequestOptions(),
        *,
        tools: Sequence[Mapping[str, Any]] | None = None,
        tool_choice: str | None = None,
        estimated_cost: Decimal | str | None = None,
    ) -> ModelResponse:
        payload = build_request(
            identity, messages, capabilities, options,
            tools=tools, tool_choice=tool_choice,
        )
        try:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                separators=(",", ":"),
                allow_nan=False,
            ).encode()
        except (TypeError, ValueError):
            raise ValueError("request payload is not finite JSON") from None
        headers = {
            "Authorization": "Bearer " + identity.api_key,
            "Content-Type": "application/json",
        }
        outcome: queue.Queue[tuple[bool, bytes | Mapping[str, Any] | None]] = queue.Queue(
            maxsize=1
        )

        def dispatch() -> None:
            try:
                raw_result = self.transport(
                    identity.endpoint, headers, body, self.timeout_seconds
                )
            except Exception:
                # Provider exception bodies commonly contain request headers or remote
                # payloads. Deliberately discard them before crossing the worker seam.
                outcome.put((False, None))
            else:
                outcome.put((True, raw_result))

        with self._dispatch_lock:
            if self._active_dispatch is not None:
                if self._active_dispatch.is_alive():
                    raise GatewayError("provider request is already in flight")
                self._active_dispatch = None
            worker = threading.Thread(
                target=dispatch,
                name="model-gateway-transport",
                daemon=True,
            )
            self._active_dispatch = worker
            worker.start()
        try:
            succeeded, raw = outcome.get(timeout=self.timeout_seconds)
        except queue.Empty:
            # Python cannot safely cancel a blocked thread. Keep its identity attached
            # to this gateway so another dispatch cannot overlap while it remains live.
            raise GatewayTimeout("provider request timed out; dispatch is unresolved") from None
        finally:
            if not worker.is_alive():
                with self._dispatch_lock:
                    if self._active_dispatch is worker:
                        self._active_dispatch = None
        if not succeeded:
            raise GatewayError("provider request failed")
        if isinstance(raw, bytes):
            if len(raw) > _MAX_RESPONSE_BYTES:
                raise GatewayError("provider response exceeded the size limit")
            try:
                raw = json.loads(raw)
            except (UnicodeDecodeError, json.JSONDecodeError):
                raise GatewayError("provider returned a malformed response") from None
        if not isinstance(raw, Mapping):
            raise GatewayError("provider returned a malformed response")
        return normalize_response(raw, estimated_cost=estimated_cost)


@dataclass(frozen=True)
class LedgerReservation:
    call_id: str
    maximum_cost: Decimal
    admitted: bool
    created: bool
    reason: str


@dataclass(frozen=True)
class LedgerSnapshot:
    limit: Decimal
    measured_cost: Decimal
    estimated_cost: Decimal
    unresolved_cost: Decimal
    committed_cost: Decimal
    available: Decimal
    exhausted: bool
    record_count: int
    started_at: float


class BudgetLedger:
    """SQLite-backed conservative admission and idempotent cost settlement."""

    def __init__(
        self,
        path: str | os.PathLike[str],
        limit: Decimal | str | int,
        *,
        max_records: int = 100_000,
    ):
        self.path = Path(path)
        self.limit = self._amount(limit, "limit")
        if self.limit <= 0:
            raise ValueError("limit must be positive")
        if type(max_records) is not int or max_records <= 0:
            raise ValueError("max_records must be positive")
        self.max_records = max_records
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialise_lock = threading.Lock()
        self._initialise()

    @staticmethod
    def _amount(value: Decimal | str | int, name: str) -> Decimal:
        amount = _money(value)
        if amount is None:
            raise ValueError(f"{name} must be a finite nonnegative decimal")
        return amount

    @staticmethod
    def _call_id(call_id: str) -> str:
        if not isinstance(call_id, str) or not call_id or len(call_id) > _MAX_IDENTIFIER:
            raise ValueError("call_id must be bounded and nonempty")
        return call_id

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA busy_timeout = 30000")
        return connection

    def _initialise(self) -> None:
        with self._initialise_lock, closing(self._connect()) as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS model_budget_calls (
                    call_id TEXT PRIMARY KEY,
                    reserved_cost TEXT NOT NULL,
                    state TEXT NOT NULL CHECK(state IN ('reserved','estimated','measured','released')),
                    settled_cost TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL
                )
                """
            )
            connection.execute(
                """CREATE TABLE IF NOT EXISTS model_budget_meta (
                       key TEXT PRIMARY KEY,
                       value TEXT NOT NULL
                   )"""
            )
            connection.execute("BEGIN IMMEDIATE")
            try:
                prior = connection.execute(
                    "SELECT value FROM model_budget_meta WHERE key = 'limit'"
                ).fetchone()
                if prior is None:
                    connection.execute(
                        "INSERT INTO model_budget_meta(key, value) VALUES('limit', ?)",
                        (str(self.limit),),
                    )
                else:
                    previous = Decimal(prior["value"])
                    if self.limit > previous:
                        raise ValueError("budget limit differs from the durable ledger")
                    if self.limit < previous:
                        connection.execute(
                            "UPDATE model_budget_meta SET value = ? WHERE key = 'limit'",
                            (str(self.limit),),
                        )
                started = connection.execute(
                    "SELECT value FROM model_budget_meta WHERE key = 'started_at'"
                ).fetchone()
                if started is None:
                    first_call = connection.execute(
                        "SELECT MIN(created_at) AS value FROM model_budget_calls"
                    ).fetchone()["value"]
                    connection.execute(
                        "INSERT INTO model_budget_meta(key, value) VALUES('started_at', ?)",
                        (str(time.time() if first_call is None else first_call),),
                    )
            except Exception:
                connection.execute("ROLLBACK")
                raise
            connection.execute("COMMIT")

    def _effective_limit(self, connection: sqlite3.Connection) -> Decimal:
        row = connection.execute(
            "SELECT value FROM model_budget_meta WHERE key = 'limit'"
        ).fetchone()
        try:
            stored = Decimal(row["value"])
        except (KeyError, TypeError, ValueError, InvalidOperation):
            raise ValueError("budget ledger limit is invalid") from None
        if not stored.is_finite() or stored <= 0:
            raise ValueError("budget ledger limit is invalid")
        return min(self.limit, stored)

    @staticmethod
    def _totals(connection: sqlite3.Connection) -> tuple[Decimal, Decimal, Decimal, int]:
        measured = estimated = unresolved = Decimal(0)
        rows = connection.execute(
            "SELECT state, reserved_cost, settled_cost FROM model_budget_calls"
        ).fetchall()
        for row in rows:
            state = row["state"]
            if state == "reserved":
                unresolved += Decimal(row["reserved_cost"])
            elif state == "measured":
                measured += Decimal(row["settled_cost"])
            elif state == "estimated":
                estimated += Decimal(row["settled_cost"])
        return measured, estimated, unresolved, len(rows)

    def reserve(
        self, call_id: str, maximum_cost: Decimal | str | int
    ) -> LedgerReservation:
        call_id = self._call_id(call_id)
        maximum = self._amount(maximum_cost, "maximum_cost")
        if maximum <= 0:
            raise ValueError("maximum_cost must be positive")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            prior = connection.execute(
                "SELECT * FROM model_budget_calls WHERE call_id = ?", (call_id,)
            ).fetchone()
            if prior is not None:
                connection.execute("COMMIT")
                if Decimal(prior["reserved_cost"]) != maximum:
                    raise ValueError("call identity replayed with a different reservation")
                return LedgerReservation(
                    call_id, maximum, prior["state"] == "reserved", False, "existing_call"
                )
            measured, estimated, unresolved, count = self._totals(connection)
            if count >= self.max_records:
                connection.execute("ROLLBACK")
                raise LedgerCapacityError("budget ledger capacity reached")
            if measured + estimated + unresolved + maximum > self._effective_limit(connection):
                connection.execute("COMMIT")
                return LedgerReservation(call_id, maximum, False, False, "budget_exhausted")
            now = time.time()
            connection.execute(
                """INSERT INTO model_budget_calls(
                       call_id, reserved_cost, state, settled_cost, created_at, updated_at
                   ) VALUES(?, ?, 'reserved', NULL, ?, ?)""",
                (call_id, str(maximum), now, now),
            )
            connection.execute("COMMIT")
        return LedgerReservation(call_id, maximum, True, True, "reserved")

    def settle(self, call_id: str, usage: UsageMetadata) -> LedgerSnapshot:
        call_id = self._call_id(call_id)
        if not isinstance(usage, UsageMetadata):
            raise ValueError("UsageMetadata required")
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM model_budget_calls WHERE call_id = ?", (call_id,)
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise KeyError(call_id)
            if usage.cost_provenance is CostProvenance.UNKNOWN or usage.cost is None:
                # Unknown cost is deliberately not settlement: retain the full
                # reservation until authoritative or conservative estimated data arrives.
                connection.execute("COMMIT")
                return self.snapshot()
            cost = self._amount(usage.cost, "usage cost")
            target = usage.cost_provenance.value
            state = row["state"]
            prior_cost = _money(row["settled_cost"])
            if state == "measured":
                connection.execute("COMMIT")
                if target != "measured" or prior_cost != cost:
                    raise ValueError("measured settlement cannot be contradicted")
                return self.snapshot()
            if state == "estimated" and target == "estimated":
                connection.execute("COMMIT")
                if prior_cost != cost:
                    raise ValueError("estimated settlement cannot be contradicted")
                return self.snapshot()
            if state == "released":
                connection.execute("ROLLBACK")
                raise ValueError("released call cannot be settled")
            # A measured late reconciliation may replace an estimate.
            connection.execute(
                "UPDATE model_budget_calls SET state = ?, settled_cost = ?, updated_at = ? "
                "WHERE call_id = ?",
                (target, str(cost), time.time(), call_id),
            )
            connection.execute("COMMIT")
        return self.snapshot()

    def release_unstarted(self, call_id: str) -> bool:
        """Release only a reservation that the caller proves was never dispatched."""
        call_id = self._call_id(call_id)
        with closing(self._connect()) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM model_budget_calls WHERE call_id = ?", (call_id,)
            ).fetchone()
            if row is None:
                connection.execute("ROLLBACK")
                raise KeyError(call_id)
            if row["state"] != "reserved":
                connection.execute("COMMIT")
                return False
            connection.execute(
                "UPDATE model_budget_calls SET state = 'released', updated_at = ? WHERE call_id = ?",
                (time.time(), call_id),
            )
            connection.execute("COMMIT")
            return True

    def snapshot(self) -> LedgerSnapshot:
        with closing(self._connect()) as connection:
            connection.execute("BEGIN")
            measured, estimated, unresolved, count = self._totals(connection)
            limit = self._effective_limit(connection)
            started_row = connection.execute(
                "SELECT value FROM model_budget_meta WHERE key = 'started_at'"
            ).fetchone()
            connection.execute("COMMIT")
        try:
            started_at = float(started_row["value"])
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ValueError("budget ledger start is invalid") from None
        if not math.isfinite(started_at):
            raise ValueError("budget ledger start is invalid")
        committed = measured + estimated + unresolved
        available = max(Decimal(0), limit - committed)
        return LedgerSnapshot(
            limit,
            measured,
            estimated,
            unresolved,
            committed,
            available,
            available == 0,
            count,
            started_at,
        )

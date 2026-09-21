import json
import tempfile
import threading
import time
import unittest
from decimal import Decimal
from pathlib import Path

from agent_ext.model_gateway import (
    BudgetLedger,
    CostProvenance,
    GatewayError,
    GatewayTimeout,
    ModelGateway,
    ProviderCapabilities,
    ProviderIdentity,
    RequestOptions,
    UsageMetadata,
    build_request,
    normalize_response,
)


def usage(cost=None, provenance=CostProvenance.UNKNOWN):
    return UsageMetadata(None, None, None, cost, provenance)


class RequestTests(unittest.TestCase):
    def setUp(self):
        self.identity = ProviderIdentity("https://provider.invalid/chat", "secret", "injected/model")
        self.messages = [{"role": "user", "content": "hello"}]

    def test_supported_openrouter_reasoning_and_unsupported_temperature(self):
        payload = build_request(
            self.identity,
            self.messages,
            ProviderCapabilities(frozenset({"reasoning"})),
            RequestOptions(temperature=0.2, reasoning_effort="high"),
        )
        self.assertEqual(payload["model"], "injected/model")
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertNotIn("temperature", payload)

    def test_scalar_reasoning_and_supported_temperature(self):
        payload = build_request(
            self.identity,
            self.messages,
            ProviderCapabilities(frozenset({"reasoning_effort", "temperature"})),
            RequestOptions(temperature=0.3, reasoning_effort="high"),
        )
        self.assertEqual(payload["reasoning_effort"], "high")
        self.assertEqual(payload["temperature"], 0.3)
        self.assertNotIn("reasoning", payload)

    def test_temperature_rejects_bool_nan_and_infinity(self):
        for value in (True, False, float("nan"), float("inf"), float("-inf")):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                RequestOptions(temperature=value)

    def test_no_capability_means_no_optional_parameters_or_substitution(self):
        payload = build_request(
            self.identity,
            self.messages,
            ProviderCapabilities(),
            RequestOptions(temperature=0.1, max_tokens=999, reasoning_effort="high"),
        )
        self.assertEqual(payload, {"model": "injected/model", "messages": self.messages})

    def test_normalizes_measured_estimated_missing_and_malformed_usage(self):
        base = {"model": "observed", "choices": [{"message": {"role": "assistant", "content": "ok"}}]}
        measured = normalize_response({**base, "usage": {
            "prompt_tokens": 2,
            "cost": "0.12",
            "prompt_tokens_details": {"cached_tokens": 1},
            "completion_tokens_details": {"reasoning_tokens": 4},
        }})
        self.assertEqual(measured.usage.cost, Decimal("0.12"))
        self.assertEqual(measured.usage.cost_provenance, CostProvenance.MEASURED)
        self.assertEqual(measured.usage.cached_prompt_tokens, 1)
        self.assertEqual(measured.usage.reasoning_tokens, 4)
        estimated = normalize_response(base, estimated_cost="0.2")
        self.assertEqual(estimated.usage.cost_provenance, CostProvenance.ESTIMATED)
        malformed = normalize_response({**base, "usage": {"cost": "not-money", "total_tokens": -1}})
        self.assertIsNone(malformed.usage.cost)
        self.assertIsNone(malformed.usage.total_tokens)
        self.assertEqual(malformed.usage.cost_provenance, CostProvenance.UNKNOWN)

    def test_gateway_is_one_shot_and_redacts_provider_failures(self):
        calls = []

        def fail(*args):
            calls.append(args)
            raise RuntimeError("remote body contains secret-token")

        gateway = ModelGateway(fail, timeout_seconds=3)
        with self.assertRaisesRegex(GatewayError, "provider request failed") as caught:
            gateway.complete(self.identity, self.messages, ProviderCapabilities())
        self.assertEqual(len(calls), 1)
        self.assertNotIn("secret-token", str(caught.exception))
        self.assertNotIn("secret", repr(self.identity))

    def test_gateway_sends_exact_identity_and_normalizes_message(self):
        def transport(endpoint, headers, body, timeout):
            self.assertEqual(endpoint, self.identity.endpoint)
            self.assertEqual(headers["Authorization"], "Bearer secret")
            self.assertEqual(json.loads(body)["model"], "injected/model")
            self.assertEqual(timeout, 4)
            return {"model": "actual/model", "choices": [{"message": {"role": "assistant", "content": "done"}}]}

        response = ModelGateway(transport, timeout_seconds=4).complete(
            self.identity, self.messages, ProviderCapabilities()
        )
        self.assertEqual(response.message["content"], "done")
        self.assertEqual(response.observed_model, "actual/model")

    def test_gateway_json_serialization_rejects_nested_nonfinite_values(self):
        called = False

        def transport(*args):
            nonlocal called
            called = True
            return {}

        with self.assertRaisesRegex(ValueError, "finite JSON"):
            ModelGateway(transport).complete(
                self.identity,
                [{"role": "user", "content": float("nan")}],
                ProviderCapabilities(),
            )
        self.assertFalse(called)

    def test_gateway_enforces_deadline_and_blocks_repeat_while_worker_lives(self):
        release = threading.Event()
        calls = []

        def blocked(*args):
            calls.append(args)
            release.wait()
            return {"choices": [{"message": {"role": "assistant", "content": "late"}}]}

        gateway = ModelGateway(blocked, timeout_seconds=0.02)
        started = time.monotonic()
        with self.assertRaises(GatewayTimeout) as caught:
            gateway.complete(self.identity, self.messages, ProviderCapabilities())
        self.assertLess(time.monotonic() - started, 0.5)
        self.assertTrue(caught.exception.dispatch_unresolved)
        self.assertTrue(gateway.dispatch_active)
        with self.assertRaisesRegex(GatewayError, "already in flight"):
            gateway.complete(self.identity, self.messages, ProviderCapabilities())
        self.assertEqual(len(calls), 1)
        release.set()
        deadline = time.monotonic() + 1
        while gateway.dispatch_active and time.monotonic() < deadline:
            time.sleep(0.005)
        self.assertFalse(gateway.dispatch_active)


class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.path = Path(self.temporary.name) / "budget.sqlite3"
        self.ledger = BudgetLedger(self.path, "10")

    def test_concurrent_reservations_admit_only_within_limit(self):
        barrier = threading.Barrier(8)
        results = []
        errors = []

        def reserve(index):
            try:
                barrier.wait()
                results.append(self.ledger.reserve(f"call-{index}", "2"))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=reserve, args=(index,)) for index in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        self.assertEqual(sum(item.admitted for item in results), 5)
        self.assertEqual(self.ledger.snapshot().unresolved_cost, Decimal("10"))

    def test_duplicate_reservation_and_settlement_are_idempotent(self):
        first = self.ledger.reserve("same", "3")
        duplicate = self.ledger.reserve("same", "3")
        self.assertTrue(first.created)
        self.assertFalse(duplicate.created)
        self.ledger.settle("same", usage(Decimal("1.25"), CostProvenance.MEASURED))
        snapshot = self.ledger.settle("same", usage(Decimal("1.25"), CostProvenance.MEASURED))
        self.assertEqual(snapshot.measured_cost, Decimal("1.25"))
        self.assertEqual(snapshot.unresolved_cost, Decimal(0))

    def test_missing_usage_stays_reserved_across_restart_then_reconciles_late(self):
        self.ledger.reserve("late", "4")
        self.ledger.settle("late", usage())
        restarted = BudgetLedger(self.path, "10")
        self.assertEqual(restarted.snapshot().unresolved_cost, Decimal("4"))
        snapshot = restarted.settle(
            "late", usage(Decimal("2.5"), CostProvenance.MEASURED)
        )
        self.assertEqual(snapshot.unresolved_cost, Decimal(0))
        self.assertEqual(snapshot.measured_cost, Decimal("2.5"))

    def test_restart_cannot_change_the_durable_limit(self):
        self.ledger.reserve("held", "4")
        with self.assertRaisesRegex(ValueError, "budget limit differs"):
            BudgetLedger(self.path, "20")
        self.assertEqual(BudgetLedger(self.path, "10").snapshot().unresolved_cost, Decimal("4"))

    def test_decimal_precision_exponent_and_serialized_length_are_bounded(self):
        invalid = (
            "0.12345678901234567890123456789",
            "1e-19",
            "1e19",
            "1" * 65,
        )
        for index, value in enumerate(invalid):
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "finite"):
                self.ledger.reserve(f"invalid-{index}", value)

        self.assertTrue(
            self.ledger.reserve("bounded", Decimal("0.123456789012345678")).admitted
        )

    def test_malformed_overprecision_response_cost_is_unknown(self):
        response = normalize_response({
            "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            "usage": {"cost": "0.12345678901234567890123456789"},
        })
        self.assertIsNone(response.usage.cost)
        self.assertEqual(response.usage.cost_provenance, CostProvenance.UNKNOWN)

    def test_estimate_can_be_replaced_by_late_measurement(self):
        self.ledger.reserve("estimated", "5")
        self.ledger.settle(
            "estimated", usage(Decimal("3"), CostProvenance.ESTIMATED)
        )
        snapshot = self.ledger.settle(
            "estimated", usage(Decimal("2"), CostProvenance.MEASURED)
        )
        self.assertEqual(snapshot.estimated_cost, Decimal(0))
        self.assertEqual(snapshot.measured_cost, Decimal("2"))

    def test_near_exhaustion_is_conservative(self):
        self.assertTrue(self.ledger.reserve("one", "9.5").admitted)
        refused = self.ledger.reserve("two", "0.51")
        self.assertFalse(refused.admitted)
        self.assertEqual(refused.reason, "budget_exhausted")
        self.assertEqual(self.ledger.snapshot().available, Decimal("0.5"))

    def test_unstarted_release_is_explicit(self):
        self.ledger.reserve("not-sent", "4")
        self.assertTrue(self.ledger.release_unstarted("not-sent"))
        self.assertFalse(self.ledger.release_unstarted("not-sent"))
        self.assertEqual(self.ledger.snapshot().committed_cost, Decimal(0))


if __name__ == "__main__":
    unittest.main()

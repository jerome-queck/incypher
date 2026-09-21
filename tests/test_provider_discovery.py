import unittest
from decimal import Decimal

from agent_ext.model_gateway import ProviderIdentity
from agent_ext.provider_discovery import (
    DiscoveryCache,
    ModelPricing,
    discover_provider,
    discover_served_model,
    estimate_max_cost,
)


CHAT = "https://openrouter.ai/api/v1/chat/completions"


def identity(endpoint=CHAT, key="top-secret", model="openai/test-model"):
    return ProviderIdentity(endpoint, key, model)


def fixture(model="openai/test-model", parameters=None, pricing=None):
    return {
        "data": [{
            "id": model,
            "canonical_slug": model + "-20260901",
            "supported_parameters": parameters
            if parameters is not None
            else [
                "reasoning",
                "temperature",
                "tools",
                "tool_choice",
                "max_completion_tokens",
                "unsupported_field",
            ],
            "pricing": pricing
            if pricing is not None
            else {"prompt": "0.000001", "completion": "0.000003"},
            "top_provider": {"max_completion_tokens": 128000},
        }]
    }


class ProviderDiscoveryTests(unittest.TestCase):
    def test_served_model_discovery_prefers_configured_default_when_available(self):
        document = {"data": [
            {"id": "other/model", "supported_parameters": ["tools"]},
            {"id": "openai/test-model", "supported_parameters": [
                "reasoning_effort", "tools", "tool_choice",
            ]},
        ]}
        resolved, result = discover_served_model(identity(), lambda *_: document)
        self.assertEqual(resolved.model, "openai/test-model")
        self.assertEqual(result.provenance, "compatible_catalogue")
        self.assertIn("reasoning_effort", result.capabilities.optional_parameters)

    def test_served_model_discovery_selects_first_tool_model_when_default_absent(self):
        document = {"data": [
            {"id": "text-only", "supported_parameters": ["temperature"]},
            {"id": "served/tool", "supported_parameters": [
                "tools", "tool_choice", "reasoning",
            ]},
            {"id": "served/other", "supported_parameters": ["tools"]},
        ]}
        resolved, result = discover_served_model(identity(), lambda *_: document)
        self.assertEqual(resolved.model, "served/tool")
        self.assertEqual(result.source, "compatible_catalogue")
        self.assertIn("reasoning", result.capabilities.optional_parameters)

    def test_served_model_discovery_falls_back_without_substitution_on_failure(self):
        for endpoint, fetch in (
            (CHAT, lambda *_: {"data": []}),
            ("https://user@provider.test/v1/chat/completions", lambda *_: fixture()),
        ):
            with self.subTest(endpoint=endpoint):
                original = identity(endpoint=endpoint)
                resolved, result = discover_served_model(original, fetch)
                self.assertEqual(resolved, original)
                self.assertEqual(result.provenance, "unknown")

    def test_exact_openrouter_model_maps_only_gateway_parameters_and_pricing(self):
        calls = []

        def fetch(url, timeout, max_bytes):
            calls.append((url, timeout, max_bytes))
            return fixture()

        result = discover_provider(identity(), fetch)
        self.assertEqual(
            result.capabilities.optional_parameters,
            {
                "reasoning",
                "temperature",
                "tools",
                "tool_choice",
                "max_completion_tokens",
            },
        )
        self.assertEqual(result.pricing.prompt_per_token, Decimal("0.000001"))
        self.assertEqual(result.pricing.completion_per_token, Decimal("0.000003"))
        self.assertEqual(result.source, "openrouter_catalogue")
        self.assertEqual(result.provenance, "openrouter_catalogue")
        self.assertEqual(result.canonical_model, "openai/test-model-20260901")
        self.assertEqual(result.max_completion_tokens, 128000)
        self.assertEqual(calls[0][0], "https://openrouter.ai/api/v1/models")
        self.assertLessEqual(calls[0][1], 5)
        self.assertLessEqual(calls[0][2], 2 * 1024 * 1024)

    def test_spoofed_hosts_and_paths_are_opaque_without_fetch(self):
        endpoints = (
            "https://openrouter.ai.evil.invalid/api/v1/chat/completions",
            "https://evil.invalid/?next=https://openrouter.ai/api/v1/chat/completions",
            "http://openrouter.ai/api/v1/chat/completions",
            "https://openrouter.ai/api/v1/chat/completions/",
            "https://openrouter.ai/api/v1/chat/completions?x=1",
            "https://user@openrouter.ai/api/v1/chat/completions",
            "https://openrouter.ai:444/api/v1/chat/completions",
        )
        for endpoint in endpoints:
            with self.subTest(endpoint=endpoint):
                called = False

                def fetch(*args):
                    nonlocal called
                    called = True
                    return fixture()

                result = discover_provider(identity(endpoint=endpoint), fetch)
                self.assertFalse(called)
                self.assertEqual(result.capabilities.optional_parameters, frozenset())
                self.assertIsNone(result.pricing)
                self.assertEqual(result.provenance, "unknown")

    def test_wrong_or_missing_exact_model_never_substitutes(self):
        for document in (fixture(model="other/model"), {"data": []}):
            with self.subTest(document=document):
                result = discover_provider(identity(), lambda *_: document)
                self.assertEqual(result.capabilities.optional_parameters, frozenset())
                self.assertIsNone(result.pricing)
                self.assertEqual(result.provenance, "unknown")

    def test_malformed_parameters_do_not_hide_valid_pricing(self):
        document = fixture(parameters="reasoning")
        result = discover_provider(identity(), lambda *_: document)
        self.assertEqual(result.capabilities.optional_parameters, frozenset())
        self.assertIsNotNone(result.pricing)

    def test_malformed_canonical_model_is_not_trusted(self):
        document = fixture()
        document["data"][0]["canonical_slug"] = ["openai/test-model"]
        result = discover_provider(identity(), lambda *_: document)
        self.assertIsNone(result.canonical_model)

    def test_unverified_completion_ceiling_cannot_raise_request_capacity(self):
        for value in (None, True, "8192", 0, -1, 1_000_001):
            with self.subTest(value=value):
                document = fixture()
                document["data"][0]["top_provider"] = {"max_completion_tokens": value}
                result = discover_provider(identity(), lambda *_: document)
                self.assertIsNone(result.max_completion_tokens)
        document = fixture(parameters=["reasoning", "tools"])
        self.assertIsNone(
            discover_provider(identity(), lambda *_: document).max_completion_tokens
        )

    def test_malformed_pricing_does_not_invent_cost(self):
        malformed = (
            {"prompt": "bad", "completion": "0.1"},
            {"prompt": "0.1"},
            {"prompt": "1e-19", "completion": "0.1"},
            {"prompt": 10**5000, "completion": "0.1"},
        )
        for pricing in malformed:
            with self.subTest(pricing=type(pricing["prompt"]).__name__):
                result = discover_provider(
                    identity(), lambda *_args, pricing=pricing: fixture(pricing=pricing)
                )
                self.assertIsNone(result.pricing)
                self.assertEqual(
                    result.capabilities.optional_parameters,
                    {
                        "reasoning",
                        "temperature",
                        "tools",
                        "tool_choice",
                        "max_completion_tokens",
                    },
                )

    def test_unavailable_or_malformed_catalogue_is_explicit_unknown(self):
        def unavailable(*_):
            raise RuntimeError("raw remote body with top-secret")

        for fetch in (unavailable, lambda *_: b"not-json", lambda *_: {"data": "bad"}):
            with self.subTest(fetch=fetch):
                result = discover_provider(identity(), fetch)
                self.assertEqual(result.provenance, "unknown")
                self.assertIsNone(result.pricing)
                self.assertEqual(result.capabilities.optional_parameters, frozenset())
                self.assertNotIn("top-secret", repr(result))

    def test_unavailable_result_is_not_cached_over_later_recovery(self):
        cache = DiscoveryCache()
        calls = 0

        def fetch(*_):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise TimeoutError("synthetic")
            return fixture()

        self.assertEqual(discover_provider(identity(), fetch, cache).provenance, "unknown")
        self.assertEqual(
            discover_provider(identity(), fetch, cache).provenance,
            "openrouter_catalogue",
        )
        self.assertEqual(calls, 2)

    def test_cache_avoids_fetch_and_never_contains_key(self):
        cache = DiscoveryCache()
        calls = 0

        def fetch(*_):
            nonlocal calls
            calls += 1
            return fixture()

        first = discover_provider(identity(key="first-secret"), fetch, cache)
        second = discover_provider(identity(key="second-secret"), fetch, cache)
        self.assertEqual(first, second)
        self.assertEqual(calls, 1)
        self.assertNotIn("secret", repr(cache))
        self.assertNotIn("secret", repr(cache._entries))

    def test_estimate_uses_uncached_bounds_and_fixed_request_cost(self):
        pricing = ModelPricing(Decimal("0.001"), Decimal("0.003"), Decimal("0.25"))
        self.assertEqual(estimate_max_cost(pricing, 100, 20), Decimal("0.410"))
        self.assertIsNone(estimate_max_cost(None, 100, 20))
        self.assertIsNone(estimate_max_cost(pricing, -1, 20))
        self.assertIsNone(estimate_max_cost(pricing, 100, 10_000_001))


if __name__ == "__main__":
    unittest.main()

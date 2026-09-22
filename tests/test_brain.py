import contextlib
import io
import json
import os
import sqlite3
import tempfile
import threading
import time
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import Mock, patch

import brain
import agent_ext.runtime_context as runtime_context
from agent_ext.provider_discovery import DiscoveryResult, ModelPricing
from agent_ext.model_gateway import CostProvenance, LedgerReservation, UsageMetadata
from agent_ext.runtime_context import trusted_attempt
from agent_ext.runtime_context import Finding, FindingDisposition, FindingKind


class ScriptedBrain(brain.Brain):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = iter(replies)

    def _chat(self, messages):
        return next(self.replies)


class CapturingBrain(ScriptedBrain):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(replies, *args, **kwargs)
        self.requests = []

    def _chat(self, messages):
        self.requests.append(json.loads(json.dumps(messages)))
        return super()._chat(messages)


class FailingBrain(brain.Brain):
    def _chat(self, messages):
        raise TimeoutError("synthetic timeout")


class SupervisedShell:
    supports_async = True

    def __init__(self):
        self.calls = []
        self.closed = False

    def __call__(self, command):
        self.calls.append(("run", command))
        return "sync"

    def start(self, command):
        self.calls.append(("start", command))
        return "job-synthetic"

    def poll(self, handle, wait_seconds=0):
        self.calls.append(("poll", handle, wait_seconds))
        return "async evidence"

    def cancel(self, handle):
        self.calls.append(("cancel", handle))
        return "cancelled"

    def close(self):
        self.closed = True


class FindingShell:
    def __init__(self, disposition=FindingDisposition.SAVED):
        self.disposition = disposition
        self.findings = []

    def __call__(self, command):
        return "unused"

    def checkpoint_finding(self, finding):
        self.findings.append(finding)
        return self.disposition


class SubmissionShell:
    def __init__(self):
        self.reservations = []
        self.reconciliations = []
        self.dispatch_marks = []
        self.admit = True
        self.reconciled = True

    def __call__(self, command):
        return "unused"

    def reserve_submission(self, candidate):
        self.reservations.append(candidate)
        return "reserved" if self.admit else "blocked"

    def submission_reconciled(self):
        return self.reconciled

    def mark_submission_dispatch_possible(self, candidate):
        self.dispatch_marks.append(candidate)
        return self.admit

    def reconcile_submission(self, candidate, status):
        self.reconciliations.append((candidate, status))


class BrainTests(unittest.TestCase):
    def test_prompt_clipping_preserves_scope_head_and_connection_tail(self):
        prompt = "HEAD-SCOPE\n" + ("x" * 30000) + "\nTAIL-CONNECTION"
        clipped = brain._clip_prompt(prompt, 24000)
        self.assertLessEqual(len(clipped.encode()), 24000)
        self.assertIn("HEAD-SCOPE", clipped)
        self.assertIn("TAIL-CONNECTION", clipped)
        self.assertIn("[middle truncated]", clipped)

    def test_trusted_points_do_not_override_runtime_step_budget(self):
        for points in (100, 250, 500):
            challenge = {
                "id": points, "name": "step budget", "category": "crypto",
                "type": "standard", "points": points, "files": [],
            }
            with trusted_attempt(challenge):
                agent = brain.Brain(Mock(), Mock(), max_steps=17, verbose=False)
            self.assertEqual(agent.max_steps, 17)

    def test_step_budget_is_strictly_bounded(self):
        for invalid in (True, "40", 0, -1, 151):
            with self.subTest(invalid=invalid), self.assertRaisesRegex(ValueError, "max_steps"):
                brain.Brain(Mock(), Mock(), max_steps=invalid, verbose=False)
        self.assertEqual(brain.Brain(Mock(), Mock(), max_steps=150, verbose=False).max_steps, 150)

    def test_each_model_turn_sees_remaining_budget_and_final_turn_instruction(self):
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "run_bash", "arguments": json.dumps({"command": f"inspect-{index}"}),
        }}]} for index in range(1, 4)]
        with patch.dict(os.environ, {"MAX_TOOL_CALLS": "12"}):
            agent = CapturingBrain(
                replies, run_bash=Mock(return_value="new evidence"), submit_flag=Mock(),
                max_steps=3, verbose=False,
            )
            result = agent.solve("synthetic")

        self.assertEqual(result["final"], "step budget exhausted")
        self.assertIn("model turn 1/3", agent.requests[0][-1]["content"])
        self.assertIn("model turn 3/3", agent.requests[2][-1]["content"])
        self.assertIn("Final model turn", agent.requests[2][-1]["content"])
        self.assertIn("10 shell/checkpoint calls remain", agent.requests[2][-1]["content"])

    def test_production_chat_discovers_high_reasoning_and_settles_budget(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def __init__(self):
                self.posts = []

            def get(self, url, timeout, stream, headers=None):
                return Response({"data": [{
                    "id": "openai/test-model",
                    "canonical_slug": "openai/test-model-20260901",
                    "supported_parameters": [
                        "reasoning", "tools", "tool_choice", "max_completion_tokens",
                    ],
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                }]})

            def post(self, endpoint, headers, data, timeout, stream):
                self.posts.append((endpoint, headers, json.loads(data), timeout))
                return Response({
                    "model": "openai/test-model",
                    "choices": [{"message": {"role": "assistant", "content": "done"}}],
                    "usage": {"prompt_tokens": 10, "completion_tokens": 2, "cost": "0.01"},
                })

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://openrouter.ai/api/v1",
            "LLM_MODEL": "openai/test-model",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            "MODEL_BUDGET_USD": "85",
        }, clear=True):
            agent = brain.Brain(Mock(), Mock(), verbose=False)
            agent.s = Session()
            message = agent._chat([{"role": "user", "content": "test"}])
            snapshot = agent._ledger.snapshot()

        self.assertEqual(message["content"], "done")
        request = agent.s.posts[0][2]
        self.assertEqual(request["model"], "openai/test-model")
        self.assertEqual(request["reasoning"], {"effort": "high"})
        self.assertIn("tools", request)
        self.assertEqual(request["tool_choice"], "auto")
        self.assertEqual(request["max_completion_tokens"], 4096)
        self.assertNotIn("temperature", request)
        self.assertEqual(snapshot.measured_cost, brain.Decimal("0.01"))
        self.assertEqual(snapshot.unresolved_cost, brain.Decimal(0))

    def test_opaque_provider_does_not_receive_inferred_reasoning(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def __init__(self):
                self.posts = []

            def post(self, endpoint, headers, data, timeout, stream):
                self.posts.append(json.loads(data))
                return Response({
                    "model": "injected/model",
                    "choices": [{"message": {"role": "assistant", "content": "done"}}],
                    "usage": {"cost": "0.01"},
                })

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://opaque.invalid/v1",
            "LLM_MODEL": "injected/model",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            "MODEL_SPEND_PACING": "adaptive",
        }, clear=True):
            agent = brain.Brain(Mock(), Mock(), verbose=False)
            agent.s = Session()
            agent._chat([{"role": "user", "content": "test"}])

        request = agent.s.posts[0]
        self.assertNotIn("reasoning", request)
        self.assertNotIn("reasoning_effort", request)
        self.assertEqual(request["max_tokens"], 4096)

    def test_image_owned_openrouter_route_uses_luna_then_priced_sol(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def __init__(self, hard_priced=True, hard_price="0.00001"):
                self.posts = []
                self.hard_priced = hard_priced
                self.hard_price = hard_price

            def get(self, url, timeout, stream, headers=None):
                entries = []
                for model, price in (("openai/gpt-5.6-luna", "0.000001"),
                                     ("openai/gpt-5.6-sol", self.hard_price)):
                    entry = {
                        "id": model,
                        "supported_parameters": [
                            "reasoning", "tools", "tool_choice", "max_completion_tokens"
                        ],
                        "top_provider": {"max_completion_tokens": 128000},
                    }
                    if model.endswith("luna") or self.hard_priced:
                        entry["pricing"] = {"prompt": "0.000001", "completion": price}
                    entries.append(entry)
                return Response({"data": entries})

            def post(self, endpoint, headers, data, timeout, stream):
                request = json.loads(data)
                self.posts.append(request)
                return Response({
                    "model": request["model"],
                    "choices": [{"message": {"role": "assistant", "content": "done"}}],
                    "usage": {"cost": "0.001"},
                })

        challenge = {"id": 7, "name": "Synthetic", "category": "crypto",
                     "type": "standard", "points": 200, "files": []}
        for attempts, routing, sol_first, hard_priced, hard_price, denied, ahead, expected_model, expected_effort in (
            (0, "1", False, True, "0.00001", False, False, "openai/gpt-5.6-luna", "xhigh"),
            (0, "1", True, True, "0.00001", False, False, "openai/gpt-5.6-sol", "xhigh"),
            (0, "1", True, True, "0.00001", False, True, "openai/gpt-5.6-sol", "xhigh"),
            (0, "1", True, False, "0.00001", False, False, "openai/gpt-5.6-luna", "xhigh"),
            (1, "1", False, True, "0.00001", False, False, "openai/gpt-5.6-sol", "xhigh"),
            (1, "1", False, False, "0.00001", False, False, "openai/gpt-5.6-luna", "xhigh"),
            (2, "1", False, True, "0.00001", False, False, "openai/gpt-5.6-sol", "xhigh"),
            (2, "1", False, False, "0.00001", False, False, "openai/gpt-5.6-luna", "xhigh"),
            (2, "1", False, True, "0.01", False, False, "openai/gpt-5.6-luna", "xhigh"),
            (2, "1", False, True, "0.00001", True, False, "openai/gpt-5.6-luna", "xhigh"),
            (2, "0", True, True, "0.00001", False, False, "openai/gpt-5.6-luna", "high"),
        ):
            with self.subTest(attempts=attempts, routing=routing,
                              sol_first=sol_first, hard_priced=hard_priced, hard_price=hard_price,
                              denied=denied, ahead=ahead), tempfile.TemporaryDirectory() as directory:
                environment = {
                    "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                    "LLM_MODEL": "openai/gpt-5.6-luna", "LLM_API_KEY": "synthetic",
                    "LLM_ROUTING_ENABLED": routing,
                    "LLM_SOL_FIRST": "1" if sol_first else "0",
                    "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
                    "MODEL_BUDGET_USD": "2", "MODEL_SPEND_PACING": "adaptive",
                }
                with patch.dict(os.environ, environment, clear=True), patch.object(
                    brain, "_DISCOVERY_CACHE", brain.DiscoveryCache()
                ), trusted_attempt(challenge, prior_attempts=attempts):
                    agent = brain.Brain(Mock(), Mock(), verbose=False)
                    agent.s = Session(hard_priced, hard_price)
                    if ahead:
                        ledger = agent._ensure_ledger()
                        ledger.reserve("prior", brain.Decimal("0.5"))
                        ledger.settle("prior", UsageMetadata(
                            0, 0, 0, brain.Decimal("0.5"), CostProvenance.MEASURED
                        ))
                        with sqlite3.connect(environment["MODEL_BUDGET_PATH"]) as connection:
                            connection.execute(
                                "UPDATE model_budget_meta SET value = ? WHERE key = 'started_at'",
                                (str(time.time() - 3600),),
                            )
                    if denied:
                        ledger = agent._ensure_ledger()
                        reserve = ledger.reserve
                        calls = []

                        def competing_reserve(call_id, maximum):
                            calls.append(maximum)
                            if len(calls) == 1:
                                return LedgerReservation(
                                    call_id, maximum, False, False, "budget_exhausted"
                                )
                            return reserve(call_id, maximum)

                        ledger.reserve = competing_reserve
                    agent._chat([{"role": "user", "content": "synthetic"}])
                    self.assertEqual(agent.s.posts[0]["model"], expected_model)
                    self.assertEqual(agent.s.posts[0]["reasoning"], {"effort": expected_effort})
                    if denied:
                        self.assertEqual(len(calls), 2)
                        self.assertLess(calls[1], calls[0])
                    self.assertEqual(agent._ledger.snapshot().measured_cost,
                                     brain.Decimal("0.501" if ahead else "0.001"))

    def test_image_owned_first_turn_availability_failover_is_priced_and_bounded(self):
        class Response:
            def __init__(self, payload, status=200):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}
                self.status_code = status

            def raise_for_status(self):
                if self.status_code != 200:
                    raise brain.requests.HTTPError("secret provider error body")

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def __init__(self, status=503, fallback_priced=True, fail_on=1,
                         tool_reply=False):
                self.posts = []
                self.status = status
                self.fallback_priced = fallback_priced
                self.fail_on = fail_on
                self.tool_reply = tool_reply

            def get(self, url, timeout, stream, headers=None):
                entries = []
                for model, price in (
                    ("openai/gpt-5.6-luna", "0.000001"),
                    ("openai/gpt-5.6-sol", "0.000010"),
                    ("google/gemini-3.1-pro-preview-customtools", "0.000012"),
                ):
                    entry = {
                        "id": model,
                        "supported_parameters": [
                            "reasoning", "tools", "tool_choice", "max_tokens",
                        ],
                        "top_provider": {"max_completion_tokens": 65536},
                    }
                    if model != "google/gemini-3.1-pro-preview-customtools" or self.fallback_priced:
                        entry["pricing"] = {
                            "prompt": "0.000002", "completion": price,
                        }
                    entries.append(entry)
                return Response({"data": entries})

            def post(self, endpoint, headers, data, timeout, stream):
                request = json.loads(data)
                self.posts.append(request)
                if len(self.posts) == self.fail_on and self.status == "refusal":
                    return Response({
                        "model": request["model"],
                        "choices": [{"message": {
                            "role": "assistant", "content": "",
                            "refusal": "synthetic refusal",
                        }}],
                        "usage": {"cost": "0.001"},
                    })
                if len(self.posts) == self.fail_on:
                    return Response({"error": "secret provider error body"}, self.status)
                if self.tool_reply:
                    return Response({
                        "model": request["model"],
                        "choices": [{"message": {
                            "role": "assistant", "content": "",
                            "tool_calls": [{
                                "id": "tool-1", "type": "function",
                                "function": {"name": "run_bash", "arguments":
                                             json.dumps({"command": "inspect"})},
                            }],
                        }}],
                        "usage": {"cost": "0.001"},
                    })
                return Response({
                    "model": request["model"],
                    "choices": [{"message": {"role": "assistant", "content": "done"}}],
                    "usage": {"cost": "0.001"},
                })

        challenge = {"id": 7, "name": "Synthetic", "category": "crypto",
                     "type": "standard", "points": 200, "files": []}
        for status, priced, max_steps, expect_fallback in (
            (404, True, 4, True),
            (429, True, 4, True),
            (503, True, 4, True),
            (500, True, 4, False),
            (403, True, 4, False),
            (503, False, 4, False),
            (503, True, 1, False),
            (503, True, 2, False),
        ):
            with self.subTest(status=status, priced=priced, max_steps=max_steps), \
                    tempfile.TemporaryDirectory() as directory:
                environment = {
                    "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                    "LLM_MODEL": "openai/gpt-5.6-luna", "LLM_API_KEY": "synthetic",
                    "LLM_MODEL_AUTO_DISCOVER": "1", "LLM_ROUTING_ENABLED": "1",
                    "LLM_SOL_FIRST": "1", "MODEL_BUDGET_USD": "2",
                    "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
                }
                with patch.dict(os.environ, environment, clear=True), patch.object(
                    brain, "_DISCOVERY_CACHE", brain.DiscoveryCache()
                ), trusted_attempt(challenge):
                    agent = brain.Brain(Mock(), Mock(), max_steps=max_steps, verbose=False)
                    agent.s = Session(status, priced)
                    if expect_fallback:
                        message = agent._chat([{"role": "user", "content": "synthetic"}])
                        self.assertEqual(message["content"], "done")
                        self.assertEqual(agent.model_calls, 2)
                        self.assertEqual(agent.s.posts[1]["model"],
                                         "google/gemini-3.1-pro-preview-customtools")
                        self.assertEqual(agent._identity.model,
                                         "google/gemini-3.1-pro-preview-customtools")
                        self.assertEqual(agent._ledger.snapshot().measured_cost,
                                         brain.Decimal("0.001"))
                    else:
                        with self.assertRaises(brain.GatewayError):
                            agent._chat([{"role": "user", "content": "synthetic"}])
                        self.assertEqual(agent.model_calls, 1)
                    self.assertEqual(len(agent.s.posts), 2 if expect_fallback else 1)
                    self.assertEqual(agent.s.posts[0]["model"], "openai/gpt-5.6-sol")
                    self.assertGreater(agent._ledger.snapshot().unresolved_cost, 0)

        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_MODEL": "openai/gpt-5.6-luna", "LLM_API_KEY": "synthetic",
                "LLM_MODEL_AUTO_DISCOVER": "1", "LLM_ROUTING_ENABLED": "1",
                "LLM_SOL_FIRST": "1", "MODEL_BUDGET_USD": "2",
                "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            }
            with patch.dict(os.environ, environment, clear=True), patch.object(
                brain, "_DISCOVERY_CACHE", brain.DiscoveryCache()
            ), trusted_attempt(challenge):
                agent = brain.Brain(Mock(), Mock(), max_steps=4, verbose=False)
                agent.s = Session(503, fail_on=2)
                agent._chat([{"role": "user", "content": "first turn"}])
                with self.assertRaises(brain.GatewayAvailabilityError):
                    agent._chat([{"role": "user", "content": "later turn"}])
                self.assertEqual(len(agent.s.posts), 2)
                self.assertEqual(agent._identity.model, "openai/gpt-5.6-sol")

        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_MODEL": "openai/gpt-5.6-sol", "LLM_API_KEY": "synthetic",
                "MODEL_BUDGET_USD": "2",
                "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            }
            with patch.dict(os.environ, environment, clear=True), patch.object(
                brain, "_DISCOVERY_CACHE", brain.DiscoveryCache()
            ), trusted_attempt(challenge):
                agent = brain.Brain(Mock(), Mock(), max_steps=4, verbose=False)
                agent.s = Session(503)
                with self.assertRaises(brain.GatewayAvailabilityError):
                    agent._chat([{"role": "user", "content": "explicit model"}])
                self.assertEqual(len(agent.s.posts), 1)

        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_MODEL": "openai/gpt-5.6-luna", "LLM_API_KEY": "synthetic",
                "LLM_MODEL_AUTO_DISCOVER": "1", "LLM_ROUTING_ENABLED": "1",
                "LLM_SOL_FIRST": "1", "MODEL_BUDGET_USD": "2",
                "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            }
            with patch.dict(os.environ, environment, clear=True), patch.object(
                brain, "_DISCOVERY_CACHE", brain.DiscoveryCache()
            ), trusted_attempt(challenge):
                agent = brain.Brain(FindingShell(), Mock(), max_steps=3, verbose=False)
                agent.s = Session(503, tool_reply=True)
                result = agent.solve("synthetic")
                self.assertEqual(result["model_calls"], 3)
                self.assertEqual(len(agent.s.posts), 3)
                final_request = agent.s.posts[2]
                self.assertIn("model turn 3/3", final_request["messages"][-1]["content"])
                self.assertIn("Final model turn", final_request["messages"][-1]["content"])
                self.assertEqual({tool["function"]["name"] for tool in final_request["tools"]},
                                 {"submit_flag", "checkpoint_finding"})

        with tempfile.TemporaryDirectory() as directory:
            environment = {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_MODEL": "openai/gpt-5.6-luna", "LLM_API_KEY": "synthetic",
                "LLM_MODEL_AUTO_DISCOVER": "1", "LLM_ROUTING_ENABLED": "1",
                "LLM_SOL_FIRST": "1", "MODEL_BUDGET_USD": "2",
                "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            }
            with patch.dict(os.environ, environment, clear=True), patch.object(
                brain, "_DISCOVERY_CACHE", brain.DiscoveryCache()
            ), trusted_attempt(challenge):
                agent = brain.Brain(Mock(), Mock(), max_steps=4, verbose=False)
                agent.s = Session("refusal")
                self.assertEqual(agent._chat([{"role": "user", "content": "synthetic"}])
                                 ["refusal"], "synthetic refusal")
                self.assertEqual(len(agent.s.posts), 1)

    def test_verified_behind_pace_request_uses_extended_completion_cap(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def __init__(self):
                self.posts = []

            def get(self, url, timeout, stream, headers=None):
                return Response({"data": [{
                    "id": "openai/test-extended",
                    "supported_parameters": ["max_completion_tokens", "reasoning", "tools"],
                    "top_provider": {"max_completion_tokens": 128000},
                    "pricing": {"prompt": "0.000001", "completion": "0.0001"},
                }]})

            def post(self, endpoint, headers, data, timeout, stream):
                self.posts.append(json.loads(data))
                return Response({
                    "model": "openai/test-extended",
                    "choices": [{"message": {"role": "assistant", "content": "done"}}],
                    "usage": {"cost": "0.01"},
                })

        with tempfile.TemporaryDirectory() as directory:
            budget_path = os.path.join(directory, "budget.sqlite3")
            with patch.dict(os.environ, {
                "LLM_BASE_URL": "https://openrouter.ai/api/v1",
                "LLM_MODEL": "openai/test-extended", "LLM_API_KEY": "synthetic",
                "MODEL_BUDGET_PATH": budget_path, "MODEL_BUDGET_USD": "20",
                "MODEL_SPEND_PACING": "adaptive",
                "MODEL_BUDGET_WINDOW_SECONDS": "23400",
            }, clear=True):
                agent = brain.Brain(Mock(), Mock(), verbose=False)
                agent.s = Session()
                agent._ensure_ledger()
                with sqlite3.connect(budget_path) as connection:
                    connection.execute(
                        "UPDATE model_budget_meta SET value = ? WHERE key = 'started_at'",
                        (str(time.time() - 3900),),
                    )
                agent._chat([{"role": "user", "content": "test"}])
                self.assertEqual(
                    agent._ledger.snapshot().measured_cost, brain.Decimal("0.01")
                )
        self.assertEqual(agent.s.posts[0]["max_completion_tokens"], 8192)
        self.assertEqual(agent.s.posts[0]["reasoning"], {"effort": "high"})

    def test_image_default_discovers_served_tool_model_and_capabilities(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def __init__(self):
                self.posts = []
                self.gets = []

            def get(self, url, timeout, stream, headers=None):
                self.gets.append((url, dict(headers or {})))
                return Response({"data": [
                    {"id": "text-only", "supported_parameters": ["temperature"]},
                    {"id": "served/tool-model", "supported_parameters": [
                        "tools", "tool_choice", "reasoning_effort",
                        "max_completion_tokens",
                    ]},
                ]})

            def post(self, endpoint, headers, data, timeout, stream):
                self.posts.append(json.loads(data))
                return Response({
                    "model": "served/tool-model",
                    "choices": [{"message": {"role": "assistant", "content": "done"}}],
                    "usage": {"cost": "0.01"},
                })

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://organizer.example/v1",
            "LLM_MODEL": "openai/gpt-5.6-luna",
            "LLM_MODEL_AUTO_DISCOVER": "1",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
        }, clear=True):
            agent = brain.Brain(Mock(), Mock(), verbose=False)
            agent.s = Session()
            message = agent._chat([{"role": "user", "content": "test"}])

        self.assertEqual(message["content"], "done")
        self.assertEqual(agent.s.gets[0][0], "https://organizer.example/v1/models")
        self.assertEqual(agent.s.gets[0][1]["Authorization"], "Bearer secret")
        self.assertEqual(agent.s.posts[0]["model"], "served/tool-model")
        self.assertEqual(agent.s.posts[0]["reasoning_effort"], "high")
        self.assertEqual(agent.s.posts[0]["max_completion_tokens"], 4096)

    def test_image_default_never_dispatches_an_unadvertised_model(self):
        session = Mock()
        session.get.return_value = Mock(
            headers={"Content-Length": "11"},
            raise_for_status=Mock(),
            iter_content=Mock(return_value=iter([b'{"data":[]}'])),
            close=Mock(),
        )
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://organizer.example/v1",
            "LLM_MODEL": "openai/gpt-5.6-luna",
            "LLM_MODEL_AUTO_DISCOVER": "1",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
        }, clear=True):
            agent = brain.Brain(Mock(), Mock(), verbose=False)
            agent.s = session
            with self.assertRaisesRegex(brain.GatewayError, "discovery unavailable"):
                agent._chat([{"role": "user", "content": "test"}])
        session.post.assert_not_called()

    def test_observed_model_substitution_is_terminal_after_accounting(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()
                self.headers = {"Content-Length": str(len(self.content))}

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield self.content

            def close(self):
                return None

        class Session:
            def get(self, url, timeout, stream, headers=None):
                return Response({"data": []})

            def post(self, endpoint, headers, data, timeout, stream):
                return Response({
                    "model": "other/model",
                    "choices": [{"message": {"role": "assistant", "content": "wrong"}}],
                    "usage": {"cost": "0.02"},
                })

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://opaque.invalid/v1",
            "LLM_MODEL": "required/model",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
        }, clear=True):
            agent = brain.Brain(Mock(), Mock(), verbose=False)
            agent.s = Session()
            with self.assertRaisesRegex(Exception, "unexpected model identity"):
                agent._chat([{"role": "user", "content": "test"}])
            self.assertEqual(agent._ledger.snapshot().measured_cost, brain.Decimal("0.02"))

    def test_only_catalogue_canonical_model_is_accepted_as_observed_identity(self):
        discovery = DiscoveryResult(
            brain.ProviderCapabilities(), None, "openrouter_catalogue",
            "openrouter_catalogue", "openai/model-20260901",
        )
        self.assertTrue(brain._observed_identity_matches(
            "openai/model", "openai/model-20260901", discovery
        ))
        self.assertFalse(brain._observed_identity_matches(
            "openai/model", "openai/model-20260902", discovery
        ))
        compatible = DiscoveryResult(
            brain.ProviderCapabilities(), None, "compatible_catalogue",
            "compatible_catalogue", "served/model-20260901",
        )
        self.assertTrue(brain._observed_identity_matches(
            "served/model", "served/model-20260901", compatible
        ))
        opaque = DiscoveryResult(
            brain.ProviderCapabilities(), None, "opaque", "unknown", None
        )
        self.assertFalse(brain._observed_identity_matches(
            "openai/model", "openai/model-20260901", opaque
        ))

    def test_budget_policy_rejects_ceiling_and_tiny_opaque_reserve(self):
        with patch.dict(os.environ, {"MODEL_BUDGET_USD": "85.01"}, clear=True):
            with self.assertRaisesRegex(ValueError, "outside"):
                brain._budget_policy()

    def test_budget_pacing_defaults_fixed_high_and_adapts_to_projected_spend(self):
        snapshot = SimpleNamespace(
            limit=brain.Decimal("85"),
            committed_cost=brain.Decimal("80"),
            started_at=1_000.0,
        )
        with patch.dict(os.environ, {}, clear=True):
            fixed = brain._budget_pace(snapshot, now=4_900.0)
        self.assertEqual((fixed.posture, fixed.reasoning_effort, fixed.max_tokens), (
            "fixed-high", "high", 4096,
        ))

        environment = {
            "MODEL_SPEND_PACING": "adaptive",
            "MODEL_BUDGET_WINDOW_SECONDS": "23400",
        }
        with patch.dict(os.environ, environment, clear=True):
            behind = brain._budget_pace(
                SimpleNamespace(**{**snapshot.__dict__, "committed_cost": brain.Decimal("1")}),
                projected_cost=brain.Decimal("1"),
                now=4_900.0,
            )
            on_target = brain._budget_pace(
                SimpleNamespace(**{
                    **snapshot.__dict__, "committed_cost": brain.Decimal("13"),
                }),
                projected_cost=brain.Decimal("1"),
                now=4_900.0,
            )
            ahead = brain._budget_pace(
                SimpleNamespace(**{
                    **snapshot.__dict__, "committed_cost": brain.Decimal("20"),
                }),
                projected_cost=brain.Decimal("1"),
                now=4_900.0,
            )
        self.assertEqual((behind.posture, behind.reasoning_effort), (
            "behind-target", "high",
        ))
        self.assertEqual((on_target.posture, on_target.reasoning_effort), (
            "on-target", "high",
        ))
        self.assertEqual((ahead.posture, ahead.reasoning_effort), (
            "ahead-of-target", "medium",
        ))
        self.assertEqual({behind.max_tokens, on_target.max_tokens, ahead.max_tokens}, {4096})
        self.assertEqual(on_target.observed_per_minute, brain.Decimal("0.2"))

    def test_verified_openrouter_behind_pace_prices_extended_completion(self):
        discovery = DiscoveryResult(
            brain.ProviderCapabilities(frozenset({"max_completion_tokens", "reasoning"})),
            ModelPricing(brain.Decimal("0.000001"), brain.Decimal("0.0001")),
            "openrouter_catalogue", "openrouter_catalogue", None, 128000,
        )
        snapshot = SimpleNamespace(
            limit=brain.Decimal("40"), committed_cost=brain.Decimal("1"),
            started_at=1000.0,
        )
        environment = {"MODEL_SPEND_PACING": "adaptive",
                       "MODEL_BUDGET_WINDOW_SECONDS": "23400"}
        with patch.dict(os.environ, environment, clear=True):
            pace, estimate, reservation = brain._budget_request(
                snapshot, discovery, 100, brain.Decimal("1"), now=4900.0
            )
            self.assertEqual((pace.posture, pace.reasoning_effort, pace.max_tokens),
                             ("behind-target", "high", 8192))
            self.assertEqual(estimate, brain.Decimal("0.8193"))
            self.assertEqual(reservation, brain.Decimal("2.4579"))

            for altered in (
                replace(discovery, max_completion_tokens=None),
                replace(discovery, pricing=None),
                replace(discovery, provenance="compatible_catalogue"),
            ):
                self.assertEqual(
                    brain._budget_request(snapshot, altered, 100, brain.Decimal("1"),
                                          now=4900.0)[0].max_tokens, 4096
                )
            self.assertEqual(
                brain._budget_request(SimpleNamespace(**{**snapshot.__dict__,
                    "committed_cost": brain.Decimal("3")}),
                                      discovery, 100, brain.Decimal("1"), now=4900.0
                                      )[0].max_tokens, 4096
            )
            self.assertEqual(
                brain._budget_request(snapshot, discovery, 100, brain.Decimal("1"),
                                      now=1050.0)[0].max_tokens, 4096
            )
        with patch.dict(os.environ, {"MODEL_SPEND_PACING": "fixed_high"}, clear=True):
            self.assertEqual(
                brain._budget_request(snapshot, discovery, 100, brain.Decimal("1"),
                                      now=4900.0)[0].max_tokens, 4096
            )

    def test_budget_pacing_validates_clock_window_and_projected_cost(self):
        snapshot = SimpleNamespace(
            limit=brain.Decimal("1"),
            committed_cost=brain.Decimal(0),
            started_at=1.0,
        )
        with patch.dict(os.environ, {"MODEL_BUDGET_WINDOW_SECONDS": "59"}, clear=True):
            with self.assertRaisesRegex(ValueError, "allowed range"):
                brain._budget_pace(snapshot, now=2.0)
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "time must be finite"):
                brain._budget_pace(snapshot, now=float("nan"))
            with self.assertRaisesRegex(ValueError, "projected model cost"):
                brain._budget_pace(snapshot, projected_cost=brain.Decimal("NaN"), now=2.0)
        with patch.dict(os.environ, {"MODEL_CALL_RESERVE_USD": "0.0001"}, clear=True):
            with self.assertRaisesRegex(ValueError, "outside"):
                brain._budget_policy()

    def test_stream_reader_rejects_declared_incremental_and_slow_oversize(self):
        class Response:
            def __init__(self, chunks, declared=None):
                self.chunks = chunks
                self.headers = {} if declared is None else {"Content-Length": declared}
                self.closed = False

            def raise_for_status(self):
                return None

            def iter_content(self, chunk_size):
                yield from self.chunks

            def close(self):
                self.closed = True

        declared = Response([], "5")
        with self.assertRaisesRegex(ValueError, "size limit"):
            brain._read_bounded_response(declared, 4, brain.time.monotonic() + 1)
        self.assertTrue(declared.closed)

        incremental = Response([b"abc", b"de"])
        with self.assertRaisesRegex(ValueError, "size limit"):
            brain._read_bounded_response(incremental, 4, brain.time.monotonic() + 1)
        self.assertTrue(incremental.closed)

        slow = Response([b"a"])
        with patch("brain.time.monotonic", return_value=10):
            with self.assertRaisesRegex(TimeoutError, "deadline"):
                brain._read_bounded_response(slow, 4, 9)
        self.assertTrue(slow.closed)

    def test_full_lifecycle_runs_command_then_submits(self):
        candidate = "INCYPHER" + "{synthetic-lifecycle}"
        replies = [
            {"content": "", "tool_calls": [{"id": "inspect", "function": {
                "name": "run_bash",
                "arguments": json.dumps({"command": "inspect synthetic material"}),
            }}]},
            {"content": "", "tool_calls": [{"id": "submit", "function": {
                "name": "submit_flag",
                "arguments": json.dumps({"flag": candidate}),
            }}]},
        ]
        commands = []
        submitted = []
        agent = ScriptedBrain(
            replies,
            run_bash=lambda command: commands.append(command) or "synthetic evidence",
            submit_flag=lambda flag: submitted.append(flag) or {"status": "correct"},
            verbose=False,
        )

        result = agent.solve("synthetic challenge")

        self.assertTrue(result["solved"])
        self.assertEqual(result["steps"], 2)
        self.assertEqual(commands, ["inspect synthetic material"])
        self.assertEqual(submitted, [candidate])

    def test_supervised_async_tools_dispatch_and_cleanup(self):
        shell = SupervisedShell()
        replies = [
            {"content": "", "tool_calls": [{"id": "1", "function": {
                "name": "start_bash", "arguments": json.dumps({"command": "inspect"}),
            }}]},
            {"content": "", "tool_calls": [{"id": "2", "function": {
                "name": "poll_bash", "arguments": json.dumps({
                    "handle": "job-synthetic", "wait_seconds": 1,
                }),
            }}]},
            {"content": "done"},
        ]
        agent = ScriptedBrain(replies, run_bash=shell, submit_flag=Mock(), verbose=False)

        result = agent.solve("synthetic")

        self.assertFalse(result["solved"])
        self.assertEqual(result["tool_calls"], 2)
        self.assertEqual(shell.calls, [
            ("start", "inspect"), ("poll", "job-synthetic", 1),
        ])
        self.assertTrue(shell.closed)
        self.assertEqual({tool["function"]["name"] for tool in agent._tools}, {
            "run_bash", "submit_flag", "start_bash", "poll_bash", "cancel_bash",
        })

    def test_checkpoint_finding_is_capability_gated_typed_and_budgeted(self):
        shell = FindingShell()
        summary = "The verifier decodes fixed-size blocks before comparison."
        replies = [
            {"content": "", "tool_calls": [{"id": "finding", "function": {
                "name": "checkpoint_finding",
                "arguments": json.dumps({"kind": "observed", "summary": summary}),
            }}]},
            {"content": "done"},
        ]
        agent = CapturingBrain(
            replies, run_bash=shell, submit_flag=Mock(), verbose=False
        )

        result = agent.solve("synthetic")

        self.assertFalse(result["solved"])
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(shell.findings, [Finding(FindingKind.OBSERVED, summary)])
        self.assertIn(
            "checkpoint_finding",
            {tool["function"]["name"] for tool in agent._tools},
        )
        self.assertIn(
            "Finding saved for this exact scope.",
            [message.get("content") for message in agent.requests[1]],
        )

    def test_saved_output_tool_returns_prior_capture_without_rerunning(self):
        class SavedShell:
            def __init__(self):
                self.handles = []

            def __call__(self, command):
                raise AssertionError("saved output must not dispatch a command")

            def read_saved_output(self, handle):
                self.handles.append(handle)
                return "[shell status=ok]\nprevious exact observation"

        shell = SavedShell()
        handle = "capture-" + "a" * 24
        replies = [
            {"content": "", "tool_calls": [{"id": "saved", "function": {
                "name": "read_saved_output", "arguments": json.dumps({"handle": handle}),
            }}]},
            {"content": "done"},
        ]
        agent = CapturingBrain(replies, run_bash=shell, submit_flag=Mock(), verbose=False)
        result = agent.solve("synthetic")
        self.assertFalse(result["solved"])
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(shell.handles, [handle])
        self.assertIn("read_saved_output", {
            tool["function"]["name"] for tool in agent._tools
        })
        self.assertTrue(any("previous exact observation" in str(message.get("content"))
                            for message in agent.requests[1]))

    def test_final_turn_reserves_semantic_checkpoint_after_shell_evidence(self):
        class BudgetAwareBrain(brain.Brain):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                self.offered = []

            def _chat(self, messages):
                offered = {tool["function"]["name"] for tool in self._tools}
                self.offered.append(offered)
                if len(self.offered) == 1:
                    name, args = "run_bash", {"command": "inspect"}
                elif "run_bash" in offered:
                    name, args = "run_bash", {"command": "inspect more"}
                else:
                    name, args = "checkpoint_finding", {
                        "kind": "next_step", "summary": "Test the block transform inverse.",
                    }
                return {"content": "", "tool_calls": [{"id": str(len(self.offered)),
                    "function": {"name": name, "arguments": json.dumps(args)}}]}

        shell = FindingShell()
        with patch.dict(os.environ, {"MAX_TOOL_CALLS": "3"}):
            agent = BudgetAwareBrain(
                shell, Mock(), max_steps=2, verbose=False,
            )
            result = agent.solve("synthetic")

        self.assertFalse(result["solved"])
        self.assertIn("run_bash", agent.offered[0])
        self.assertNotIn("run_bash", agent.offered[1])
        self.assertEqual(shell.findings, [Finding(
            FindingKind.NEXT_STEP, "Test the block transform inverse.",
        )])

    def test_unoffered_final_shell_call_cannot_dispatch(self):
        shell = Mock(return_value="new evidence")
        shell.checkpoint_finding.return_value = FindingDisposition.SAVED
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "run_bash", "arguments": json.dumps({"command": f"inspect-{index}"}),
        }}]} for index in (1, 2)]
        agent = ScriptedBrain(
            replies, run_bash=shell, submit_flag=Mock(), max_steps=2, verbose=False,
        )

        result = agent.solve("synthetic")

        self.assertEqual(result["final"], "step budget exhausted")
        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(shell.call_count, 1)
        shell.checkpoint_finding.assert_not_called()
        self.assertIn("run_bash", {tool["function"]["name"] for tool in agent._tools})

    def test_single_turn_slice_keeps_inspection_available(self):
        shell = FindingShell()
        replies = [{"content": "", "tool_calls": [{"id": "inspect", "function": {
            "name": "run_bash", "arguments": json.dumps({"command": "inspect"}),
        }}]}]
        agent = ScriptedBrain(
            replies, run_bash=shell, submit_flag=Mock(), max_steps=1, verbose=False,
        )

        result = agent.solve("synthetic")

        self.assertEqual(result["tool_calls"], 1)
        self.assertEqual(result["final"], "step budget exhausted")

    def test_rejected_or_duplicate_findings_are_quiet(self):
        for disposition, summary, expected_calls in (
            (FindingDisposition.REJECTED, "Recovered token synthetic-value", 0),
            (FindingDisposition.DUPLICATE, "The decoder reverses input blocks.", 3),
        ):
            with self.subTest(disposition=disposition):
                shell = FindingShell(disposition)
                replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
                    "name": "checkpoint_finding",
                    "arguments": json.dumps({"kind": "hypothesis", "summary": summary}),
                }}]} for index in range(3)]
                agent = ScriptedBrain(
                    replies, run_bash=shell, submit_flag=Mock(), max_steps=4, verbose=False
                )

                result = agent.solve("synthetic")

                self.assertEqual(result["error"], "quiet stall: no new tool evidence")
                self.assertEqual(result["tool_calls"], 3)
                self.assertEqual(len(shell.findings), expected_calls)

    def test_malformed_checkpoint_findings_are_budgeted_and_quiet(self):
        shell = FindingShell()
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "checkpoint_finding", "arguments": "{}",
        }}]} for index in range(3)]
        agent = ScriptedBrain(
            replies, run_bash=shell, submit_flag=Mock(), max_steps=4, verbose=False
        )

        result = agent.solve("synthetic")

        self.assertEqual(result["error"], "quiet stall: no new tool evidence")
        self.assertEqual(result["tool_calls"], 3)
        self.assertEqual(shell.findings, [])

    def test_reasoning_details_round_trip_unchanged_after_tool_call(self):
        details = [{"type": "reasoning.summary", "id": "synthetic", "data": "opaque"}]
        replies = [
            {"content": "", "reasoning_details": details, "tool_calls": [{
                "id": "inspect", "function": {
                    "name": "run_bash", "arguments": json.dumps({"command": "inspect"}),
                },
            }]},
            {"content": "done"},
        ]
        agent = CapturingBrain(
            replies, run_bash=Mock(return_value="evidence"), submit_flag=Mock(), verbose=False
        )

        agent.solve("synthetic challenge")

        assistant_turn = next(
            message for message in agent.requests[1]
            if message.get("role") == "assistant" and "reasoning_details" in message
        )
        self.assertEqual(assistant_turn["reasoning_details"], details)
        self.assertEqual(assistant_turn["tool_calls"], replies[0]["tool_calls"])

    def test_oversized_reasoning_details_are_rejected(self):
        replies = [{
            "content": "",
            "reasoning_details": [{"data": "x" * (brain._MAX_REASONING_DETAILS_BYTES + 1)}],
            "tool_calls": [{"id": "inspect", "function": {
                "name": "run_bash", "arguments": json.dumps({"command": "inspect"}),
            }}],
        }]
        agent = ScriptedBrain(
            replies, run_bash=Mock(), submit_flag=Mock(), verbose=False
        )

        result = agent.solve("synthetic challenge")

        self.assertEqual(result["error"], "malformed model message")
        agent.run_bash.assert_not_called()

    def test_submits_flag_returned_as_text(self):
        candidate = "INCYPHER" + "{unit-test-only}"
        submitted = []
        agent = ScriptedBrain(
            [{"content": "Recovered " + candidate}],
            run_bash=lambda command: "unused",
            submit_flag=lambda flag: submitted.append(flag) or {"status": "correct"},
        )

        result = agent.solve("sample")

        self.assertTrue(result["solved"])
        self.assertEqual(submitted, [candidate])

    def test_already_solved_is_terminal(self):
        candidate = "INCYPHER" + "{already-solved-test}"
        replies = [{"content": "", "tool_calls": [{"id": "1", "function": {
            "name": "submit_flag", "arguments": json.dumps({"flag": candidate})}}]}]
        submitted = []
        agent = ScriptedBrain(
            replies,
            run_bash=lambda command: "unused",
            submit_flag=lambda flag: submitted.append(flag) or {"status": "already_solved"},
        )

        result = agent.solve("sample")

        self.assertTrue(result["solved"])
        self.assertEqual(result["verdict"]["status"], "already_solved")
        self.assertEqual(submitted, [candidate])

    def test_submission_budget_is_terminal(self):
        submitted = []
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "submit_flag",
            "arguments": json.dumps({"flag": "INCYPHER{candidate-%d}" % index})}}]}
                   for index in range(1, 5)]
        agent = ScriptedBrain(
            replies,
            run_bash=lambda command: "unused",
            submit_flag=lambda flag: submitted.append(flag) or {"status": "incorrect"},
        )

        result = agent.solve("sample")

        self.assertFalse(result["solved"])
        self.assertEqual(result["error"], "submission budget exhausted")
        self.assertEqual(len(submitted), 3)

    def test_one_submission_per_assistant_evidence_turn(self):
        candidates = ["INCYPHER" + "{first}", "INCYPHER" + "{second}"]
        replies = [
            {"content": "", "tool_calls": [
                {"id": str(index), "function": {
                    "name": "submit_flag", "arguments": json.dumps({"flag": candidate}),
                }} for index, candidate in enumerate(candidates)
            ]},
            {"content": "stop"},
        ]
        submitted = []
        agent = ScriptedBrain(
            replies,
            run_bash=Mock(),
            submit_flag=lambda flag: submitted.append(flag) or {"status": "incorrect"},
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertFalse(result["solved"])
        self.assertEqual(submitted, [candidates[0]])

    def test_tool_call_budget_is_terminal(self):
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "run_bash", "arguments": json.dumps({"command": f"echo {index}"})
        }}]} for index in range(2)]
        agent = ScriptedBrain(
            replies, run_bash=Mock(return_value="ok"), submit_flag=Mock(), verbose=False
        )
        agent.max_tool_calls = 1
        result = agent.solve("sample")
        self.assertEqual(result["error"], "tool call budget exhausted")
        self.assertEqual(agent.run_bash.call_count, 1)

    def test_quiet_stall_replans_once_then_stops_without_extra_model_call(self):
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "run_bash", "arguments": json.dumps({"command": "same"})
        }}]} for index in range(3)]
        agent = CapturingBrain(
            replies,
            run_bash=Mock(return_value="duplicate:no new evidence"),
            submit_flag=Mock(),
            max_steps=6,
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertEqual(result["error"], "quiet stall: no new tool evidence")
        self.assertEqual(result["model_calls"], 0)
        self.assertEqual(agent.run_bash.call_count, 3)
        notices = [message for message in agent.requests[2]
                   if "Replan once" in str(message.get("content", ""))]
        self.assertEqual(len(notices), 1)

    def test_quiet_stall_counts_assistant_turns_not_parallel_tool_calls(self):
        first_calls = [{"id": str(index), "function": {
            "name": "run_bash", "arguments": json.dumps({"command": f"same-{index}"})
        }} for index in range(3)]
        replies = [
            {"content": "", "tool_calls": first_calls},
            {"content": "", "tool_calls": [first_calls[0]]},
            {"content": "", "tool_calls": [first_calls[1]]},
        ]
        agent = ScriptedBrain(
            replies,
            run_bash=Mock(return_value="duplicate:no new evidence"),
            submit_flag=Mock(),
            max_steps=6,
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertEqual(result["error"], "quiet stall: no new tool evidence")
        self.assertEqual(agent.run_bash.call_count, 5)

    def test_status_only_tool_failures_trigger_quiet_stall(self):
        replies = [{"content": "", "tool_calls": [{"id": str(index), "function": {
            "name": "run_bash", "arguments": json.dumps({"command": f"slow-{index}"})
        }}]} for index in range(4)]
        agent = ScriptedBrain(
            replies,
            run_bash=Mock(return_value=(
                "[shell status=timeout exit=-9 elapsed=45.000s truncated=false]"
            )),
            submit_flag=Mock(),
            max_steps=4,
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertEqual(result["error"], "quiet stall: no new tool evidence")
        self.assertEqual(agent.run_bash.call_count, 3)

    def test_rate_limit_is_terminal_and_not_retried(self):
        candidate = "INCYPHER" + "{rate-limit-test}"
        replies = [{"content": candidate}, {"content": candidate}]
        submitted = []
        agent = ScriptedBrain(
            replies,
            run_bash=lambda command: "unused",
            submit_flag=lambda flag: submitted.append(flag) or {"status": "ratelimited"},
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertFalse(result["solved"])
        self.assertEqual(result["error"], "submission unavailable: ratelimited")
        self.assertEqual(submitted, [candidate])

    def test_model_timeout_is_reported_as_failure(self):
        agent = FailingBrain(
            run_bash=lambda command: "unused",
            submit_flag=lambda flag: {"status": "correct"},
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertFalse(result["solved"])
        self.assertEqual(result["steps"], 1)
        self.assertIn("TimeoutError", result["error"])

    def test_expired_attempt_stops_before_provider_dispatch(self):
        challenge = {
            "id": 1, "name": "small", "category": "crypto", "type": "static",
            "points": 100, "files": [],
        }
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://opaque.invalid/v1",
            "LLM_MODEL": "required/model",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
        }, clear=True), trusted_attempt(challenge):
            current = runtime_context.current_attempt(required=True)
            token = runtime_context._CURRENT.set(
                replace(current, deadline_monotonic=time.monotonic() - 1)
            )
            try:
                agent = brain.Brain(Mock(), Mock(), verbose=False)
                agent.s.post = Mock(side_effect=AssertionError("must not dispatch"))
                result = agent.solve("synthetic")
            finally:
                runtime_context._CURRENT.reset(token)
        self.assertFalse(result["solved"])
        self.assertIn("GatewayError", result["error"])
        agent.s.post.assert_not_called()
        self.assertIsNone(agent._ledger)

    def test_timeout_after_dispatch_retains_durable_reservation(self):
        released = threading.Event()

        class Session:
            def post(self, endpoint, headers, data, timeout, stream):
                released.wait(0.2)
                raise TimeoutError("synthetic provider stall")

        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {
            "LLM_BASE_URL": "https://opaque.invalid/v1",
            "LLM_MODEL": "required/model",
            "LLM_API_KEY": "secret",
            "MODEL_BUDGET_PATH": os.path.join(directory, "budget.sqlite3"),
            "MODEL_BUDGET_USD": "1",
            "MODEL_TIMEOUT_SECONDS": "0.02",
        }, clear=True):
            agent = brain.Brain(Mock(), Mock(), verbose=False)
            agent.s = Session()
            result = agent.solve("synthetic")
            snapshot = agent._ledger.snapshot()
            released.set()

        self.assertFalse(result["solved"])
        self.assertIn("GatewayTimeout", result["error"])
        self.assertEqual(snapshot.unresolved_cost, brain.Decimal("1"))

    def test_partial_model_configuration_fails_before_network_or_submission(self):
        submitted = []
        agent = brain.Brain(
            run_bash=lambda command: "unused",
            submit_flag=lambda flag: submitted.append(flag) or {"status": "correct"},
            verbose=False,
        )
        agent.s.post = Mock(side_effect=AssertionError("network must not be called"))

        with patch.dict(os.environ, {"LLM_MODEL": "runtime-model"}, clear=True):
            result = agent.solve("sample")

        self.assertFalse(result["solved"])
        self.assertIn("ConfigurationError", result["error"])
        agent.s.post.assert_not_called()
        self.assertEqual(submitted, [])

    def test_model_exception_details_are_not_projected_to_results(self):
        agent = brain.Brain(Mock(), Mock(), verbose=False)
        with patch.object(agent, '_chat', side_effect=RuntimeError('synthetic-provider-secret')):
            result = agent.solve('sample')
        self.assertEqual(result['error'], 'RuntimeError: model request failed')
        self.assertNotIn('synthetic-provider-secret', str(result))

    def test_malformed_tool_arguments_do_not_crash_loop(self):
        commands = []
        replies = [
            {"content": "", "tool_calls": [{"id": "broken", "function": {
                "name": "run_bash", "arguments": "not-json",
            }}]},
            {"content": "No supported result."},
        ]
        agent = ScriptedBrain(
            replies,
            run_bash=lambda command: commands.append(command) or "empty command rejected",
            submit_flag=lambda flag: {"status": "correct"},
            verbose=False,
        )

        result = agent.solve("sample")

        self.assertFalse(result["solved"])
        self.assertEqual(commands, [])
        self.assertEqual(result["final"], "No supported result.")

    def test_redacts_flags_from_logs(self):
        candidate = "INCYPHER" + "{secret}"
        submitted = []
        replies = [
            {"content": "", "tool_calls": [{"id": "1", "function": {
                "name": "run_bash",
                "arguments": json.dumps({"command": "echo " + candidate})}}]},
            {"content": "", "tool_calls": [{"id": "2", "function": {
                "name": "submit_flag",
                "arguments": json.dumps({"flag": candidate})}}]},
        ]
        agent = ScriptedBrain(
            replies,
            run_bash=lambda command: candidate,
            submit_flag=lambda flag: submitted.append(flag) or {"status": "correct"},
        )

        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = agent.solve("sample")

        self.assertTrue(result["solved"])
        self.assertNotIn(candidate, output.getvalue())
        self.assertIn("[flag redacted]", output.getvalue())
        self.assertEqual(submitted, [candidate])

    def test_nonobject_arguments_and_wrong_field_types_never_dispatch(self):
        for name, field in (("run_bash", "command"), ("submit_flag", "flag")):
            for args in ([], None, 42, "text", {field: []}, {field: ""}):
                with self.subTest(name=name, args=args):
                    command, submit = Mock(), Mock()
                    agent = ScriptedBrain([
                        {"tool_calls": [{"id": "bad", "function": {
                            "name": name, "arguments": json.dumps(args)}}]},
                        {"content": "No supported result."},
                    ], run_bash=command, submit_flag=submit, verbose=False)
                    self.assertFalse(agent.solve("sample")["solved"])
                    command.assert_not_called()
                    submit.assert_not_called()

    def test_submit_tool_rejects_noncompetition_candidate_format(self):
        submit = Mock()
        agent = ScriptedBrain([
            {"tool_calls": [{"id": "bad", "function": {
                "name": "submit_flag", "arguments": json.dumps({"flag": "swordfish"}),
            }}]},
            {"content": "No supported result."},
        ], run_bash=Mock(), submit_flag=submit, verbose=False)
        result = agent.solve("sample")
        self.assertFalse(result["solved"])
        submit.assert_not_called()

    def test_duplicate_tool_candidate_does_not_spend_submission_budget(self):
        candidate = "INCYPHER" + "{duplicate-test}"
        reply = {"tool_calls": [{"id": "submit", "function": {
            "name": "submit_flag", "arguments": json.dumps({"flag": candidate})}}]}
        submit = Mock(return_value={"status": "incorrect"})
        agent = ScriptedBrain([reply, reply, {"content": candidate}],
                              run_bash=Mock(), submit_flag=submit, verbose=False)
        self.assertFalse(agent.solve("sample")["solved"])
        submit.assert_called_once_with(candidate)
        self.assertEqual(agent.submissions, 1)

    def test_duplicate_text_candidates_submit_once(self):
        candidate = "INCYPHER" + "{duplicate-text}"
        submit = Mock(return_value={"status": "incorrect"})
        agent = ScriptedBrain([{"content": candidate + " " + candidate}],
                              run_bash=Mock(), submit_flag=submit, verbose=False)
        self.assertFalse(agent.solve("sample")["solved"])
        submit.assert_called_once_with(candidate)

    def test_unknown_or_malformed_verdict_stops_before_second_candidate(self):
        for verdict in (None, [], "correct", {}, {"status": []}, {"status": "unexpected"}):
            with self.subTest(verdict=verdict):
                submit = Mock(return_value=verdict)
                agent = ScriptedBrain([{
                    "content": "INCYPHER{synthetic-one} INCYPHER{synthetic-two}",
                }], run_bash=Mock(), submit_flag=submit, verbose=False)
                result = agent.solve("sample")
                self.assertFalse(result["solved"])
                self.assertEqual(result["error"], "submission unavailable: uncertain")
                submit.assert_called_once_with("INCYPHER{synthetic-one}")

    def test_submission_callback_exception_becomes_terminal_uncertainty(self):
        replies = [{"content": "", "tool_calls": [{"id": "submit", "function": {
            "name": "submit_flag",
            "arguments": json.dumps({"flag": "INCYPHER{synthetic}"}),
        }}]}]
        submit = Mock(side_effect=RuntimeError("transport failed after possible delivery"))
        result = ScriptedBrain(
            replies, run_bash=Mock(), submit_flag=submit, verbose=False
        ).solve("synthetic")

        self.assertFalse(result["solved"])
        self.assertEqual(result["verdict"], {"status": "uncertain"})
        self.assertEqual(result["error"], "submission unavailable: uncertain")
        self.assertEqual(submit.call_count, 1)

    def test_uncertain_submission_is_reserved_and_replay_is_blocked(self):
        candidate = "INCYPHER{uncertain-reservation}"
        reply = {"content": candidate}
        shell = SubmissionShell()
        submit = Mock(side_effect=RuntimeError("delivery unknown"))

        first = ScriptedBrain(
            [reply], run_bash=shell, submit_flag=submit, verbose=False
        ).solve("synthetic")
        shell.reconciled = False
        second = ScriptedBrain(
            [reply], run_bash=shell, submit_flag=submit, verbose=False
        ).solve("synthetic")

        self.assertEqual(first["error"], "submission unavailable: uncertain")
        self.assertEqual(
            second["error"], "submission unresolved: reconciliation required"
        )
        self.assertEqual(submit.call_count, 1)
        self.assertEqual(shell.reservations, [candidate])
        self.assertEqual(shell.dispatch_marks, [candidate])
        self.assertEqual(shell.reconciliations, [(candidate, "uncertain")])

    def test_dispatch_marker_failure_prevents_callback(self):
        class FailingMarkerShell(SubmissionShell):
            def mark_submission_dispatch_possible(self, candidate):
                raise RuntimeError("marker commit failed")

        candidate = "INCYPHER{not-dispatched}"
        submit = Mock()
        with self.assertRaisesRegex(RuntimeError, "marker commit failed"):
            ScriptedBrain(
                [{"content": candidate}],
                run_bash=FailingMarkerShell(),
                submit_flag=submit,
                verbose=False,
            ).solve("synthetic")
        submit.assert_not_called()

    def test_partial_submission_state_callbacks_are_rejected(self):
        class PartialShell:
            def __call__(self, command):
                return "unused"

            def reserve_submission(self, candidate):
                return "reserved"

        with self.assertRaisesRegex(ValueError, "supplied together"):
            brain.Brain(PartialShell(), Mock(), verbose=False)

    def test_durable_rejected_candidate_is_not_dispatched(self):
        class RejectedShell(SubmissionShell):
            def reserve_submission(self, candidate):
                self.reservations.append(candidate)
                return "rejected"

        candidate = "INCYPHER{durably-wrong}"
        submit = Mock()
        result = ScriptedBrain(
            [{"content": candidate}],
            run_bash=RejectedShell(),
            submit_flag=submit,
            verbose=False,
        ).solve("synthetic")

        self.assertFalse(result["solved"])
        submit.assert_not_called()

    def test_malformed_model_messages_return_failure_without_dispatch(self):
        for reply in ([], None, {"content": []}, {"tool_calls": {}},
                      {"tool_calls": [None]}, {"tool_calls": [{"function": []}]},
                      {"tool_calls": [{"function": {"name": []}}]}):
            with self.subTest(reply=reply):
                command, submit = Mock(), Mock()
                agent = ScriptedBrain([reply], run_bash=command, submit_flag=submit,
                                      verbose=False)
                self.assertEqual(agent.solve("sample")["error"], "malformed model message")
                command.assert_not_called()
                submit.assert_not_called()

    def test_structured_model_refusal_is_classified_without_text_leak(self):
        command, submit = Mock(), Mock()
        result = ScriptedBrain(
            [{"role": "assistant", "content": None,
              "refusal": "Synthetic refusal with INCYPHER{do-not-copy}"}],
            run_bash=command, submit_flag=submit, verbose=False,
        ).solve("sample")
        self.assertEqual(result["error"], "model refusal")
        self.assertNotIn("do-not-copy", str(result))
        command.assert_not_called()
        submit.assert_not_called()


if __name__ == "__main__":
    unittest.main()

import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

import brain
from agent_ext.runtime_context import trusted_attempt


class ScriptedBrain(brain.Brain):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = iter(replies)

    def _chat(self, messages):
        return next(self.replies)


class FailingBrain(brain.Brain):
    def _chat(self, messages):
        raise TimeoutError("synthetic timeout")


class BrainTests(unittest.TestCase):
    def test_trusted_points_bound_model_steps(self):
        challenge = {
            "id": 1, "name": "small", "category": "crypto", "type": "standard",
            "points": 100, "files": [],
        }
        with trusted_attempt(challenge):
            agent = brain.Brain(Mock(), Mock(), max_steps=40, verbose=False)
        self.assertEqual(agent.max_steps, 4)

    def test_production_chat_discovers_high_reasoning_and_settles_budget(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()

            def raise_for_status(self):
                return None

        class Session:
            def __init__(self):
                self.posts = []

            def get(self, url, timeout):
                return Response({"data": [{
                    "id": "openai/test-model",
                    "supported_parameters": [
                        "reasoning", "tools", "tool_choice", "max_completion_tokens",
                    ],
                    "pricing": {"prompt": "0.000001", "completion": "0.000002"},
                }]})

            def post(self, endpoint, headers, data, timeout):
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

    def test_observed_model_substitution_is_terminal_after_accounting(self):
        class Response:
            def __init__(self, payload):
                self.content = json.dumps(payload).encode()

            def raise_for_status(self):
                return None

        class Session:
            def get(self, url, timeout):
                return Response({"data": []})

            def post(self, endpoint, headers, data, timeout):
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
            "arguments": json.dumps({"flag": "candidate-%d" % index})}}]}
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


if __name__ == "__main__":
    unittest.main()

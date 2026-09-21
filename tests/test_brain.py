import contextlib
import io
import json
import unittest

import brain


class ScriptedBrain(brain.Brain):
    def __init__(self, replies, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.replies = iter(replies)

    def _chat(self, messages):
        return next(self.replies)


class BrainTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()

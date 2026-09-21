import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from agent_ext.contracts import Budget, ChallengeScope, FailureCategory, NextAction, ToolResult
from agent_ext.resources import Admission, Capacity
from agent_ext.tools import Limits, ToolExecutor
from agent_ext.tools.executor import _run_worker, clean_environment


class ExecutorPortableTests(unittest.TestCase):
    def executor(self):
        return ToolExecutor(ChallengeScope(1, "synthetic", "fixture", "material", "a"),
                            "/tmp", Admission(Capacity(256 * 1024 * 1024, 2)),
                            lambda *args: "private:example")

    def test_unknown_operation_does_not_launch(self):
        with patch("subprocess.Popen") as launch:
            result = self.executor().execute("a1", "run_bash", "anything")
            self.assertEqual(result.error, FailureCategory.CONFIGURATION)
            launch.assert_not_called()

    def test_shared_action_extra_arguments_cannot_override_trusted_configuration(self):
        action = NextAction("text", {"path": "sample", "root": "/etc"}, "synthetic")
        with patch("subprocess.Popen") as launch:
            result = self.executor().execute_action("a1", action, Budget(1, 0))
            self.assertEqual(result.error, FailureCategory.MALFORMED_RESPONSE)
            launch.assert_not_called()

    def test_unsupported_platform_fails_closed(self):
        with patch("agent_ext.tools.executor.sys.platform", "unsupported"), patch("subprocess.Popen") as launch:
            result = self.executor().execute("a1", "identify", "data")
            self.assertIn("confinement_unavailable", result.excerpt)
            launch.assert_not_called()

    def test_environment_does_not_inherit_secrets(self):
        with patch.dict(os.environ, {"CTF_TOKEN": "sentinel-platform", "LLM_API_KEY": "sentinel-model",
                                     "PYTHONPATH": "sentinel-hook", "LD_PRELOAD": "sentinel-loader"}):
            value = clean_environment("/tmp/fixture")
            self.assertNotIn("sentinel", repr(value))
            self.assertEqual(set(value), {"PATH", "LANG", "LC_ALL", "TMPDIR", "PYTHONDONTWRITEBYTECODE"})

    def test_invalid_deadlines_and_action_ids_are_configuration_errors(self):
        for value in (0, -1, float("nan"), float("inf"), True, 121):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.executor().execute("a1", "identify", "data", timeout_seconds=value)
        with self.assertRaises(ValueError):
            self.executor().execute("unsafe\nidentifier", "identify", "data")
        with patch("subprocess.Popen") as launch:
            result = self.executor().execute("a1", "text", "data", offset=10**10000)
            self.assertEqual(result.error, FailureCategory.MALFORMED_RESPONSE)
            launch.assert_not_called()


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux fd/rlimit/process-group checks require Linux")
class ExecutorLinuxTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aidan-test-", dir="/tmp")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.material = self.root / "material"
        self.material.mkdir()
        self.scratch = self.root / "scratch"
        self.scratch.mkdir()
        (self.material / "sample").write_bytes(b"hello synthetic data\x00")
        self.pool = Admission(Capacity(256 * 1024 * 1024, 2))
        self.evidence = []
        self.scope = ChallengeScope(1, "synthetic", "fixture", "material", "a", "g1")

        def sink(scope, key, observation):
            self.evidence.append((scope, key, observation))
            return "private:fixture-observation"

        self.executor = ToolExecutor(self.scope, str(self.material), self.pool, sink,
                                     scratch_root=str(self.scratch))
        blocker = patch.object(socket, "socket", side_effect=AssertionError("unexpected network"))
        blocker.start()
        self.addCleanup(blocker.stop)

    def assert_clean(self):
        self.assertEqual(list(self.scratch.iterdir()), [])
        self.assertEqual(self.pool.snapshot()["active"], 0)

    def test_real_worker_returns_shared_contract_private_evidence_and_metrics(self):
        result = self.executor.execute("a1", "text", "sample")
        self.assertIsInstance(result, ToolResult)
        self.assertIsNone(result.error, result.excerpt)
        observation = json.loads(result.excerpt)
        self.assertEqual(observation["text"], "hello synthetic data\x00")
        self.assertEqual(observation["material_sha256"], hashlib.sha256((self.material / "sample").read_bytes()).hexdigest())
        self.assertGreater(observation["worker_peak_rss_bytes"], 0)
        self.assertIsNone(observation["container_peak_memory_bytes"])
        self.assertEqual(result.observation_ref, "private:fixture-observation")
        self.assertEqual(result.provenance_refs, (self.evidence[0][1],))
        self.assert_clean()

    def test_shared_action_and_budget_match_merged_strategy_failure_classification(self):
        from agent_ext.strategy_bridge import failure_from_tool
        from agent_ext.retry_policy import FailureKind
        action = NextAction("text", {"path": "sample", "offset": 0}, "synthetic")
        result = self.executor.execute_action("a1", action, Budget(1, 0, time.monotonic() + 5))
        self.assertIsNone(result.error, result.excerpt)
        self.assertIsNone(failure_from_tool(result))
        expired = self.executor.execute_action("a2", action, Budget(1, 0, time.monotonic() - 1))
        self.assertEqual(failure_from_tool(expired).kind, FailureKind.TOOL_TIMEOUT)
        self.assert_clean()

    def test_mutated_source_changes_observation_identity(self):
        first = self.executor.execute("a1", "identify", "sample")
        (self.material / "sample").write_bytes(b"different synthetic bytes")
        second = self.executor.execute("a2", "identify", "sample")
        self.assertIsNone(first.error, first.excerpt)
        self.assertIsNone(second.error, second.excerpt)
        self.assertNotEqual(first.provenance_refs, second.provenance_refs)
        self.assert_clean()

    def test_mutation_during_snapshot_is_rejected(self):
        from agent_ext.tools.worker import read_snapshot
        from agent_ext.tools.inspection import InspectionError
        original = os.read
        changed = False

        def changing_read(fd, count):
            nonlocal changed
            chunk = original(fd, count)
            if not changed:
                changed = True
                (self.material / "sample").write_bytes(b"changed while reading")
            return chunk

        with patch("agent_ext.tools.worker.os.read", side_effect=changing_read):
            with self.assertRaisesRegex(InspectionError, "source_changed"):
                read_snapshot(str(self.material), "sample", 1024)

    def test_traversal_symlinks_fifo_and_missing_file_are_contained(self):
        (self.material / "link").symlink_to(self.material / "sample")
        (self.material / "dirlink").symlink_to(self.material, target_is_directory=True)
        os.mkfifo(self.material / "pipe")
        for path in ("../sample", "/etc/passwd", "link", "dirlink/sample", "pipe", "missing"):
            with self.subTest(path=path):
                result = self.executor.execute("a1", "text", path)
                self.assertIsNotNone(result.error)
                self.assertNotIn(str(self.material), result.excerpt)
                self.assert_clean()

    def test_weird_filename_is_data_not_shell_syntax(self):
        name = "spaces ' ; $(echo surprise) unicode-\u03bb"
        (self.material / name).write_bytes(b"fixture")
        result = self.executor.execute("a1", "text", name)
        self.assertIsNone(result.error, result.excerpt)
        self.assertEqual(json.loads(result.excerpt)["text"], "fixture")

    def test_symlink_root_is_rejected(self):
        link = self.root / "rootlink"
        link.symlink_to(self.material, target_is_directory=True)
        self.executor.root = str(link)
        result = self.executor.execute("a1", "text", "sample")
        self.assertIsNotNone(result.error)
        self.assert_clean()

    def test_large_source_is_refused_before_unbounded_read(self):
        self.executor.limits = Limits(input_bytes=4)
        result = self.executor.execute("a1", "text", "sample")
        self.assertEqual(result.error, FailureCategory.RESOURCE_LIMIT)
        self.assert_clean()

    def test_malformed_worker_output_failure_and_missing_executable(self):
        for output in (b"not-json", b"[]", b'{"observation":{}}'):
            with patch("agent_ext.tools.executor._run_worker", return_value=(output, 0, None, False)):
                result = self.executor.execute("a1", "text", "sample")
                self.assertEqual(result.error, FailureCategory.MALFORMED_RESPONSE)
                self.assert_clean()
        with patch("agent_ext.tools.executor._run_worker", side_effect=FileNotFoundError):
            self.assertEqual(self.executor.execute("a1", "text", "sample").error, FailureCategory.CONFIGURATION)
        self.assert_clean()

    def test_evidence_failure_is_sanitised_and_releases_slot(self):
        def bad_sink(*args):
            raise ValueError("sensitive fixture text must not escape")
        self.executor.sink = bad_sink
        result = self.executor.execute("a1", "text", "sample")
        self.assertEqual(result.error, FailureCategory.CONFIGURATION)
        self.assertNotIn("sensitive", result.excerpt)
        self.assert_clean()

    def test_pre_cancelled_call_does_not_launch(self):
        cancellation = threading.Event()
        cancellation.set()
        with patch("subprocess.Popen") as launch:
            result = self.executor.execute("a1", "text", "sample", cancellation=cancellation)
            self.assertEqual(result.error, FailureCategory.CANCELLED)
            launch.assert_not_called()
        self.assert_clean()

    def test_real_timeout_reaps_worker_and_cleans_scratch(self):
        children = []
        original = subprocess.Popen

        def launch(*args, **kwargs):
            child = original(*args, **kwargs)
            children.append(child)
            return child

        with patch("agent_ext.tools.executor.subprocess.Popen", side_effect=launch):
            result = self.executor.execute("a1", "text", "sample", timeout_seconds=0.005)
        self.assertEqual(result.error, FailureCategory.TIMEOUT)
        self.assertTrue(children)
        self.assertTrue(all(child.returncode is not None for child in children))
        self.assert_clean()

    def test_expired_caller_deadline_prevents_launch(self):
        with patch("subprocess.Popen") as launch:
            result = self.executor.execute("a1", "text", "sample", deadline_monotonic=time.monotonic() - 1)
            self.assertEqual(result.error, FailureCategory.TIMEOUT)
            launch.assert_not_called()
        self.assert_clean()

    def test_queue_wait_respects_caller_deadline(self):
        from agent_ext.resources import Cost
        with self.pool.acquire(Cost(256 * 1024 * 1024), deadline=time.monotonic() + 1):
            with patch("subprocess.Popen") as launch:
                result = self.executor.execute("a1", "text", "sample", deadline_monotonic=time.monotonic() + 0.02)
                self.assertEqual(result.error, FailureCategory.TIMEOUT)
                launch.assert_not_called()
        self.assert_clean()

    def run_fixture(self, script, *, cancellation=None, duration=1, cap=2048):
        return _run_worker([sys.executable, "-I", "-B", "-c", script], b"{}", str(self.scratch),
                           deadline=time.monotonic() + duration, cancellation=cancellation,
                           output_bytes=cap)

    def test_large_stdout_stderr_are_stopped_at_combined_cap(self):
        for descriptor in (1, 2):
            with self.subTest(descriptor=descriptor):
                output, _, reason, truncated = self.run_fixture(
                    f"import os; os.write({descriptor},b'x'*1000000)")
                self.assertEqual(reason, "output_limit")
                self.assertTrue(truncated)
                self.assertLessEqual(len(output), 2048)

    def test_both_streams_and_hanging_worker_are_bounded(self):
        output, _, reason, _ = self.run_fixture(
            "import os,time; os.write(1,b'out'); os.write(2,b'err'); time.sleep(10)", duration=0.3)
        self.assertEqual(reason, "timeout")
        self.assertIn(b"out", output)
        self.assertIn(b"err", output)

    def test_running_cancellation(self):
        cancellation = threading.Event()
        timer = threading.Timer(0.1, cancellation.set)
        timer.start()
        try:
            _, _, reason, _ = self.run_fixture("import time; time.sleep(10)", cancellation=cancellation)
            self.assertEqual(reason, "cancelled")
        finally:
            timer.cancel()
            timer.join()

    def test_running_cancellation_releases_admission_and_scratch(self):
        cancellation = threading.Event()
        original = _run_worker

        def slow_fixture(argv, request, scratch, **kwargs):
            cancellation.set()
            return original([sys.executable, "-I", "-c", "import time; time.sleep(10)"],
                            request, scratch, **kwargs)

        with patch("agent_ext.tools.executor._run_worker", side_effect=slow_fixture):
            result = self.executor.execute("a1", "text", "sample", cancellation=cancellation)
        self.assertEqual(result.error, FailureCategory.CANCELLED)
        self.assert_clean()

    def test_real_subprocess_environment_and_working_directory(self):
        script = "import os,json; print(json.dumps(dict(cwd=os.getcwd(),env=dict(os.environ))))"
        with patch.dict(os.environ, {"CTF_TOKEN": "sentinel-platform", "LLM_API_KEY": "sentinel-model"}):
            output, code, reason, _ = self.run_fixture(script, cap=4096)
        self.assertEqual(code, 0)
        self.assertIsNone(reason)
        self.assertNotIn(b"sentinel", output)
        self.assertEqual(json.loads(output)["cwd"], str(self.scratch))


if __name__ == "__main__":
    unittest.main()

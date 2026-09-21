import os
import sys
import time
import unittest

from agent_ext.managed_shell import ManagedShell


@unittest.skipUnless(sys.platform.startswith("linux"), "Linux confinement required")
class ManagedShellTests(unittest.TestCase):
    def shell(self, **kwargs):
        return ManagedShell("scope", time.monotonic() + 10, ordinary_seconds=1,
                            heavy_seconds=1, output_bytes=1024, cwd="/tmp", **kwargs)

    def test_sync_output_and_environment_are_bounded(self):
        shell = self.shell()
        try:
            result = shell("printf ok; test -z \"$LLM_API_KEY\"")
        finally:
            shell.close()
        self.assertIn("status=ok", result)
        self.assertIn("ok", result)
        self.assertEqual(shell.snapshot()["handles"], 0)

    def test_output_limit_kills_before_unbounded_capture(self):
        shell = self.shell()
        try:
            result = shell("yes x")
        finally:
            shell.close()
        self.assertIn("status=output_limit", result)
        self.assertIn("truncated=true", result)
        self.assertLess(len(result.encode()), 1400)

    def test_timeout_kills_descendant_process_group(self):
        shell = ManagedShell("scope", time.monotonic() + 10, ordinary_seconds=0.15,
                             heavy_seconds=0.15, output_bytes=1024, cwd="/tmp")
        try:
            result = shell("sleep 30 & echo $!; wait")
        finally:
            shell.close()
        self.assertIn("status=timeout", result)
        self.assertEqual(shell.snapshot()["active"], 0)

    def test_async_handle_poll_cancel_and_cleanup(self):
        shell = self.shell()
        handle = shell.start("sleep 30")
        self.assertTrue(handle.startswith("job-"))
        self.assertEqual(shell.poll(handle), "running:" + handle)
        self.assertIn("status=cancelled", shell.cancel(handle))
        second = shell.start("sleep 30")
        shell.close()
        self.assertTrue(second.startswith("job-"))
        self.assertEqual(shell.snapshot()["handles"], 0)

    def test_two_handle_limit_and_scope_local_unknown_handle(self):
        shell = self.shell()
        try:
            one = shell.start("sleep 1")
            two = shell.start("sleep 1")
            three = shell.start("sleep 1")
            self.assertTrue(one.startswith("job-"))
            self.assertTrue(two.startswith("job-"))
            self.assertEqual(three, "error:shell handle limit reached")
            self.assertEqual(shell.poll("job-other"), "error:unknown shell handle")
        finally:
            shell.close()

    def test_confinement_unavailable_fails_closed(self):
        shell = self.shell()
        try:
            original = os.path.exists
            os.path.exists = lambda path: False if path == "/usr/bin/prlimit" else original(path)
            try:
                result = shell("echo unsafe")
            finally:
                os.path.exists = original
        finally:
            shell.close()
        self.assertIn("status=confinement_unavailable", result)


if __name__ == "__main__":
    unittest.main()

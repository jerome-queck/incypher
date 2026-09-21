import json
import tempfile
import threading
import unittest
from pathlib import Path

from agent_ext.results import InternalResultEntry, InternalResultProjector


class InternalResultProjectionTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.database = root / "state.sqlite3"
        self.output = root / "internal-results.json"
        self.projector = InternalResultProjector(self.database, self.output)

    def entry(self, number, *, synthetic=False):
        return InternalResultEntry(
            f"entry-{number}",
            number,
            f"intent:{number}",
            "accepted",
            synthetic,
            {"evidence_completeness": "partial" if number == 1 else "complete"},
        )

    def test_r15_failure_preserves_prior_valid_output(self):
        self.projector.commit_and_project(self.entry(1))
        original = self.output.read_bytes()
        self.projector.commit_entry(self.entry(2))
        self.projector.before_replace = lambda *_: (_ for _ in ()).throw(
            OSError("synthetic replacement failure")
        )
        with self.assertRaises(OSError):
            self.projector.project()
        self.assertEqual(self.output.read_bytes(), original)
        self.projector.before_replace = None
        status = self.projector.reconcile()
        self.assertTrue(status.current)
        self.assertEqual(len(json.loads(self.output.read_text())["entries"]), 2)

    def test_r15_concurrent_completions_do_not_overwrite_entries(self):
        errors = []

        def worker(number):
            try:
                self.projector.commit_and_project(self.entry(number))
            except Exception as exc:  # pragma: no cover - asserted below
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(number,)) for number in range(1, 9)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(errors, [])
        packet = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(len(packet["entries"]), 8)
        self.assertEqual(packet["live_successes"], 8)

    def test_r16_restart_rebuilds_missing_projection(self):
        self.projector.commit_entry(self.entry(1, synthetic=True))
        restarted = InternalResultProjector(self.database, self.output)
        self.assertTrue(restarted.reconcile().current)
        packet = json.loads(self.output.read_text(encoding="utf-8"))
        self.assertEqual(packet["live_successes"], 0)
        self.assertEqual(packet["entries"][0]["details"]["evidence_completeness"], "partial")

    def test_r16_replacement_before_bookkeeping_reconciles_without_new_entry(self):
        calls = []

        def interrupt(_):
            calls.append("replaced")
            raise RuntimeError("synthetic interruption")

        projector = InternalResultProjector(
            self.database, self.output, after_replace=interrupt
        )
        projector.commit_entry(self.entry(1))
        with self.assertRaises(RuntimeError):
            projector.project()
        self.assertFalse(projector.publication_status().current)
        projector.after_replace = None
        self.assertTrue(projector.reconcile().current)
        self.assertEqual(calls, ["replaced"])
        self.assertEqual(len(json.loads(self.output.read_text())["entries"]), 1)


if __name__ == "__main__":
    unittest.main()

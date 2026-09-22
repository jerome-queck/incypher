import json
import os
from pathlib import Path
import stat
import tempfile
import unittest

from agent_ext.output_vault import MAX_OUTPUT_BYTES, OutputVault


class OutputVaultTests(unittest.TestCase):
    def test_private_capture_survives_reopen_and_stays_in_exact_scope(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "captures.sqlite3"
            first, other = "a" * 64, "b" * 64
            vault = OutputVault(path)
            handle = vault.save(first, "xxd artifact", "binary bytes and result")
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            self.assertEqual(OutputVault(path).read(first, handle), "binary bytes and result")
            self.assertIsNone(vault.read(other, handle))
            self.assertIsNone(vault.read(first, "capture-invalid"))
            projected = json.loads(vault.project(first))
            self.assertEqual(projected["handle"], handle)
            self.assertIn("binary bytes", projected["output_preview"])
            self.assertEqual(vault.project(other), "")

    def test_bounded_records_and_full_output_access(self):
        with tempfile.TemporaryDirectory() as directory:
            vault = OutputVault(Path(directory) / "captures.sqlite3")
            scope = "c" * 64
            first = vault.save(scope, "first", "a" * 12000)
            self.assertEqual(len(vault.read(scope, first)), 12000)
            self.assertEqual(len(json.loads(vault.project(scope))["output_preview"]), 600)
            for index in range(16):
                vault.save(scope, f"command {index}", f"output {index}")
            self.assertIsNone(vault.read(scope, first))
            self.assertEqual(len(vault.project(scope).splitlines()), 4)
            long_handle = vault.save(scope, "oversized output", "x" * (MAX_OUTPUT_BYTES * 2))
            saved = vault.read(scope, long_handle)
            self.assertLessEqual(len(saved.encode()), MAX_OUTPUT_BYTES)
            self.assertIn("[private capture truncated", saved)
            with self.assertRaisesRegex(ValueError, "bound"):
                vault.save(scope, "x" * 20000, "short")

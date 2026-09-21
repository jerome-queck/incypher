import os
import tempfile
import unittest

from agent_ext.runtime_context import (
    bind_prepared_material,
    current_attempt,
    trusted_attempt,
)


class RuntimeContextTests(unittest.TestCase):
    def setUp(self):
        self.challenge = {
            "id": 7, "name": "Synthetic", "category": "(Practice) web",
            "type": "dynamic_iac", "points": 250, "files": ["/files/a.bin"],
        }

    def test_trusted_scope_is_bound_enriched_and_restored(self):
        secret_connection = "https://private.invalid/token-value"
        with tempfile.TemporaryDirectory() as directory:
            with open(os.path.join(directory, "a.bin"), "wb") as stream:
                stream.write(b"material")
            with trusted_attempt(self.challenge) as initial:
                self.assertEqual(current_attempt(), initial)
                enriched = bind_prepared_material(
                    self.challenge, directory, ["a.bin"], secret_connection
                )
                self.assertEqual(enriched.challenge_id, 7)
                self.assertEqual(enriched.file_count, 1)
                self.assertNotEqual(enriched.material_ref, initial.material_ref)
                self.assertNotIn(secret_connection, repr(enriched))
                self.assertNotIn("token-value", repr(enriched))
                self.assertEqual(enriched.call_id(2), f"{enriched.attempt_id}:model:2")
                self.assertGreater(enriched.deadline_monotonic, 0)
        self.assertIsNone(current_attempt())

    def test_prose_cannot_replace_trusted_identity(self):
        with trusted_attempt(self.challenge):
            changed = dict(self.challenge, id=99)
            with self.assertRaisesRegex(RuntimeError, "identity changed"):
                bind_prepared_material(changed, "/tmp", [], None)

    def test_nested_or_malformed_context_is_rejected(self):
        with self.assertRaises(ValueError):
            with trusted_attempt({"id": "7"}):
                pass
        with trusted_attempt(self.challenge):
            with self.assertRaisesRegex(RuntimeError, "nested"):
                with trusted_attempt(self.challenge):
                    pass


if __name__ == "__main__":
    unittest.main()

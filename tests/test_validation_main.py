import tempfile
import unittest
from pathlib import Path

from validation_main import validation_id


class ValidationIdTests(unittest.TestCase):
    def test_reads_positive_challenge_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation-id"
            path.write_text("94\n", encoding="utf-8")
            self.assertEqual(validation_id(path), 94)

    def test_rejects_nonpositive_challenge_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "validation-id"
            path.write_text("0\n", encoding="utf-8")
            with self.assertRaises(ValueError):
                validation_id(path)

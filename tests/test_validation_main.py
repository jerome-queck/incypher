import tempfile
import unittest
import sys
from types import ModuleType
from pathlib import Path
from unittest.mock import patch

import validation_main
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

    def test_delegates_to_official_main_with_one_selected_id(self):
        called = []
        official_main = ModuleType("main")
        official_main.is_practice = lambda challenge: True
        official_main.main = lambda: called.append(True) or 0
        solver = ModuleType("validation_solver")
        solver.build_prompt = lambda ch, cdir, filenames, conn: "synthetic"

        def solve_challenge(client, ch, max_steps):
            return {"solved": False}

        solve_challenge.__module__ = "validation_solver"
        official_main.solve_challenge = solve_challenge

        with (
            patch("validation_main.validation_id", return_value=94),
            patch.dict(sys.modules, {"main": official_main, "validation_solver": solver}),
            patch.dict("os.environ", {}, clear=True),
        ):
            result = validation_main.main()

            self.assertEqual(result, 0)
            self.assertEqual(validation_main.os.environ["ONLY_IDS"], "94")
            self.assertFalse(official_main.is_practice({"category": "(Practice)"}))
            self.assertEqual(called, [True])

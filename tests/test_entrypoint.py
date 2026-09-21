import os
import itertools
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "entrypoint.sh"


class EntrypointEnvironmentTests(unittest.TestCase):
    def run_entrypoint(self, runtime=None):
        runtime = runtime or {}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            env_file = root / "day1.env"
            env_file.write_text(
                "LLM_BASE_URL=https://fallback.example/v1\n"
                "LLM_MODEL=fallback-model\n"
                "LLM_API_KEY=fallback-key\n",
                encoding="utf-8",
            )
            bin_dir = root / "bin"
            bin_dir.mkdir()
            fake_python = bin_dir / "python"
            fake_python.write_text(
                "#!/bin/sh\n"
                "printf '%s|%s|%s\\n' \"${LLM_BASE_URL-}\" \"${LLM_MODEL-}\" \"${LLM_API_KEY-}\"\n",
                encoding="utf-8",
            )
            fake_python.chmod(0o755)

            environment = {
                "PATH": str(bin_dir),
                "DAY1_LLM_ENV_FILE": str(env_file),
                **runtime,
            }
            result = subprocess.run(
                [str(ENTRYPOINT)],
                env=environment,
                check=True,
                capture_output=True,
                text=True,
            )
            return result.stdout.strip()

    def test_day1_file_is_fallback_when_runtime_is_absent(self):
        self.assertEqual(
            self.run_entrypoint(),
            "https://fallback.example/v1|fallback-model|fallback-key",
        )

    def test_complete_runtime_configuration_wins(self):
        self.assertEqual(
            self.run_entrypoint({
                "LLM_BASE_URL": "https://runtime.example/v1",
                "LLM_MODEL": "runtime-model",
                "LLM_API_KEY": "runtime-key",
            }),
            "https://runtime.example/v1|runtime-model|runtime-key",
        )

    def test_every_partial_runtime_configuration_is_not_mixed_with_fallback(self):
        values = {
            "LLM_BASE_URL": "https://runtime.example/v1",
            "LLM_MODEL": "runtime-model",
            "LLM_API_KEY": "runtime-key",
        }
        names = tuple(values)

        for count in (1, 2):
            for present in itertools.combinations(names, count):
                runtime = {name: values[name] for name in present}
                expected = "|".join(runtime.get(name, "") for name in names)
                with self.subTest(present=present):
                    self.assertEqual(self.run_entrypoint(runtime), expected)


if __name__ == "__main__":
    unittest.main()

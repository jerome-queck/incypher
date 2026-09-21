"""Opt-in synthetic benchmark: python3 -B -m tests.fixtures.aidan.benchmark_tools.

No model, Board, network, credentials or real challenge data. Not an arena benchmark.
"""
import io
import json
from pathlib import Path
import platform
import statistics
import tempfile
import zipfile

from agent_ext.contracts import ChallengeScope
from agent_ext.resources import Admission, Capacity
from agent_ext.tools import ToolExecutor


def main():
    with tempfile.TemporaryDirectory(prefix="aidan-bench-", dir="/tmp") as directory:
        root = Path(directory)
        (root / "sample").write_bytes((b"synthetic fixture text\x00" * 3000))
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as archive:
            for number in range(10):
                archive.writestr(f"member-{number}.txt", "synthetic fixture\n" * 100)
        (root / "archive.zip").write_bytes(stream.getvalue())
        pool = Admission(Capacity(256 * 1024 * 1024, 2))
        executor = ToolExecutor(ChallengeScope(1, "synthetic", "fixture", "material", "a"),
                                str(root), pool, lambda *args: "private:benchmark")
        rows = []
        for operation in ("identify", "text", "hex", "strings", "zip_list"):
            results = [executor.execute(f"bench-{i}", operation,
                                       "archive.zip" if operation == "zip_list" else "sample")
                       for i in range(5)]
            if any(result.error for result in results):
                raise RuntimeError("benchmark operation failed: " + operation)
            observations = [json.loads(result.excerpt) for result in results]
            rows.append(dict(operation=operation, samples=len(results),
                             median_seconds=round(statistics.median(r.duration_seconds for r in results), 4),
                             max_worker_rss_bytes=max(o["worker_peak_rss_bytes"] for o in observations),
                             max_excerpt_bytes=max(len(r.excerpt.encode()) for r in results)))
        print(json.dumps(dict(python=platform.python_version(), platform=platform.system(),
                              measurements=rows, container_peak_memory_bytes=None,
                              container_peak_pids=None, admission_after=pool.snapshot()), indent=2))


if __name__ == "__main__":
    main()

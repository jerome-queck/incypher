"""Private fixed-function Linux worker. Never accepts shell commands or extracts files."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import sys

# -I deliberately removes the script directory from imports. This location is
# trusted installed code, not the material root or per-call working directory.
if __name__ == "__main__":
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from agent_ext.tools.inspection import InspectionError, Limits, encode, inspect


def open_root(root: str) -> int:
    """Walk every component using directory descriptors; never follow a symlink."""
    if not root.startswith(("/work/", "/tmp/")) and root not in {"/work", "/tmp"}:
        raise InspectionError("unapproved_root")
    components = root.split("/")[1:]
    if any(p in {"", ".", ".."} for p in components):
        raise InspectionError("unsafe_path")
    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
    fd = os.open("/", flags)
    try:
        for part in components:
            next_fd = os.open(part, flags, dir_fd=fd)
            os.close(fd)
            fd = next_fd
        return fd
    except BaseException:
        os.close(fd)
        raise


def read_snapshot(root: str, relative: str, limit: int):
    if (not relative or relative.startswith(("/", "\\")) or "\\" in relative
            or ":" in relative or "\x00" in relative
            or any(p in {"", ".", ".."} for p in relative.split("/"))):
        raise InspectionError("unsafe_path")
    directory = open_root(root)
    fd = None
    try:
        parts = relative.split("/")
        for part in parts[:-1]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
                              | os.O_CLOEXEC, dir_fd=directory)
            os.close(directory)
            directory = next_fd
        fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
                     | os.O_CLOEXEC, dir_fd=directory)
        before = os.fstat(fd)
        if not stat.S_ISREG(before.st_mode):
            raise InspectionError("not_regular_file")
        if before.st_size > limit:
            raise InspectionError("input_limit")
        data = bytearray()
        while len(data) <= limit:
            chunk = os.read(fd, min(65536, limit + 1 - len(data)))
            if not chunk:
                break
            data.extend(chunk)
        after = os.fstat(fd)
        identity = lambda s: (s.st_dev, s.st_ino, s.st_size, s.st_mtime_ns, s.st_ctime_ns)
        if identity(before) != identity(after) or len(data) != after.st_size:
            raise InspectionError("source_changed")
        if len(data) > limit:
            raise InspectionError("input_limit")
        return bytes(data)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(directory)


def main():
    try:
        if not sys.platform.startswith("linux"):
            raise InspectionError("confinement_unavailable")
        import resource
        request = json.loads(sys.stdin.buffer.read(8193))
        try:
            resource.setrlimit(resource.RLIMIT_AS, (request["memory_bytes"],) * 2)
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
            resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))
            resource.setrlimit(resource.RLIMIT_NOFILE, (32, 32))
        except (OSError, ValueError):
            raise InspectionError("confinement_unavailable") from None
        limits = Limits(**request["limits"])
        data = read_snapshot(request["root"], request["path"], limits.input_bytes)
        observation = inspect(data, request["operation"], request["offset"], limits)
        result = dict(observation=observation, sha256=hashlib.sha256(data).hexdigest(),
                      worker_peak_rss_bytes=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * 1024)
    except InspectionError as exc:
        result = dict(error=str(exc))
    except MemoryError:
        result = dict(error="worker_memory_limit")
    except OSError:
        result = dict(error="file_access_failed")
    except (ValueError, KeyError, TypeError):
        result = dict(error="malformed_input")
    except Exception:
        # No paths, material content, exception messages or tracebacks on stderr.
        result = dict(error="malformed_material")
    sys.stdout.buffer.write(encode(result))


if __name__ == "__main__":
    main()

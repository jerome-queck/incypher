#!/usr/bin/env python3
"""Run exactly one explicitly configured challenge through the official harness."""

import os
from pathlib import Path


VALIDATION_ID_FILE = Path("/opt/agent/.validation-id")


def validation_id(path=VALIDATION_ID_FILE):
    challenge_id = int(path.read_text(encoding="utf-8").strip())
    if challenge_id <= 0:
        raise ValueError("validation challenge ID must be positive")
    return challenge_id


def main():
    import main as official_main

    challenge_id = validation_id()
    os.environ["ONLY_IDS"] = str(challenge_id)
    official_main.is_practice = lambda challenge: False
    print(
        f"=== validation mode: challenge {challenge_id} via official harness ===",
        flush=True,
    )
    return official_main.main()


if __name__ == "__main__":
    raise SystemExit(main())

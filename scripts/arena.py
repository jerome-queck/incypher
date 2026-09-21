#!/usr/bin/env python3
"""Local setup, bounded practice and deliberate arena release commands."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "registry.in-cypher.com:5001"
MODEL_KEYS = ("LLM_BASE_URL", "LLM_MODEL", "LLM_API_KEY")
DAY1_POLICY_KEYS = (
    "MODEL_BUDGET_USD", "MODEL_CALL_RESERVE_USD", "MODEL_BUDGET_WINDOW_SECONDS",
    "MODEL_SPEND_PACING",
)
RUNTIME_KEYS = (
    "CTF_BASE", "CTF_TOKEN", *MODEL_KEYS,
    "MAX_STEPS", "MAX_TOOL_CALLS", "MAX_SUBMISSIONS",
    "MODEL_BUDGET_USD", "MODEL_CALL_RESERVE_USD", "MODEL_BUDGET_WINDOW_SECONDS",
)


def read_environment(path=ROOT / ".env", environ=None):
    values = {}
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, value = line.partition("=")
            key, value = key.strip(), value.strip()
            if not separator or not re.fullmatch(r"[A-Z][A-Z0-9_]*", key):
                raise ValueError("Invalid .env line; use plain KEY=value")
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                value = value[1:-1]
            values[key] = value
    values.update(os.environ if environ is None else environ)
    return values


def require(values, names):
    missing = [name for name in names if not values.get(name, "").strip()]
    if missing:
        raise ValueError("Set required values in .env: " + ", ".join(missing))


def day1_environment(values):
    require(values, (*MODEL_KEYS, "MODEL_BUDGET_USD"))
    names = [*MODEL_KEYS, *(
        key for key in DAY1_POLICY_KEYS if values.get(key, "").strip()
    )]
    return "".join(f"{key}={shlex.quote(values[key])}\n" for key in names)


def run(args, **kwargs):
    return subprocess.run(args, cwd=ROOT, check=True, **kwargs)


def image_name(values):
    team = values.get("TEAM_ID", "")
    if not re.fullmatch(r"[1-9][0-9]*", team):
        raise ValueError("TEAM_ID must be a positive integer")
    return f"{REGISTRY}/team-{team}/agent:latest"


def build_args(image, phase, secret=None):
    args = ["docker", "build", "--pull", "--platform", "linux/amd64", "--provenance=false"]
    if phase == "day1":
        args += ["--no-cache", "--build-arg", "INCLUDE_DAY1_LLM=1",
                 "--secret", f"id=day1_llm,src={secret}"]
    return args + ["-t", image, "."]


def practice_args(image, challenge, work, values):
    require(values, ("CTF_BASE", "CTF_TOKEN", *MODEL_KEYS))
    args = ["docker", "run", "--rm", "--platform", "linux/amd64", "--read-only",
            "--cpus", "2", "--memory", "2g", "--pids-limit", "256",
            "--cap-drop", "ALL", "--security-opt", "no-new-privileges",
            "--mount", f"type=bind,src={work},dst=/work",
            "--tmpfs", "/tmp:rw,nosuid,size=256m", "-e", f"ONLY_IDS={challenge}",
            "-e", "MODEL_SPEND_PACING=fixed_high"]
    for key in RUNTIME_KEYS:
        if key in values:
            args += ["-e", key]
    return args + [image]


def check(image):
    run(["sh", str(ROOT / "scripts/check_image.sh"), image])
    with tempfile.TemporaryDirectory(prefix="incypher-check-") as directory:
        container = run(["docker", "create", image], capture_output=True, text=True).stdout.strip()
        checker = Path(directory) / "check_agent.sh"
        try:
            run(["docker", "cp", f"{container}:/opt/agent/check_agent.sh", str(checker)])
        finally:
            run(["docker", "rm", container], stdout=subprocess.DEVNULL)
        run(["bash", str(checker), image])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("init", help="create a private .env without overwriting it")
    sub.add_parser("doctor", help="report prerequisites and presence of config; no secret values")
    sub.add_parser("login", help="log in to official registry using CTF_TOKEN via stdin")
    for name in ("build", "check", "practice", "push"):
        p = sub.add_parser(name)
        p.add_argument("--image", default="incypher-agent:local")
        if name in ("build", "push"):
            p.add_argument("--phase", required=True, choices=("day1", "day2"))
        if name == "practice":
            p.add_argument("--challenge", required=True, type=int)
    args = parser.parse_args(argv)
    if args.command == "init":
        target = ROOT / ".env"
        try:
            fd = os.open(target, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            print(".env already exists; preserved")
        else:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                stream.write((ROOT / ".env.example").read_text(encoding="utf-8"))
            print("Created .env; fill missing keys locally")
        return
    values = read_environment()
    if args.command == "doctor":
        for tool in ("docker", "codex"):
            print(f"{tool}: {'found' if shutil.which(tool) else 'missing'}")
        for key in ("TEAM_ID", "CTF_BASE", "CTF_TOKEN", *MODEL_KEYS, "MODEL_BUDGET_USD"):
            print(f"{key}: {'set' if values.get(key, '').strip() else 'missing'}")
        print("For subscription login: codex login status. Offline tests need no credentials.")
    elif args.command == "login":
        require(values, ("CTF_TOKEN",))
        image_name(values)
        run(["docker", "login", REGISTRY, "-u", "team-" + values["TEAM_ID"],
             "--password-stdin"], input=values["CTF_TOKEN"] + "\n", text=True)
    elif args.command == "build":
        if args.phase == "day1":
            with tempfile.TemporaryDirectory(prefix="incypher-build-") as directory:
                secret = Path(directory) / "model.env"
                secret.touch(mode=0o600)
                secret.write_text(day1_environment(values), encoding="utf-8")
                run(build_args(args.image, args.phase, secret))
        else:
            run(build_args(args.image, args.phase))
    elif args.command == "check":
        check(args.image)
    elif args.command == "practice":
        if args.challenge <= 0:
            raise ValueError("--challenge must be positive")
        require(values, ("CTF_BASE", "CTF_TOKEN", *MODEL_KEYS))
        work = ROOT / "private" / "practice"
        work.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Preserve private results after exit; each attempt gets its own directory.
        destination = Path(tempfile.mkdtemp(prefix=f"{args.challenge}-", dir=work))
        print(f"Practice submits to challenge {args.challenge}; private results: {destination}")
        run(practice_args(args.image, args.challenge, destination, values), env=values)
    elif args.command == "push":
        # This command is deliberate publication. Build/check the exact local image first.
        # Verify the selected execution mode before mutating the registry tag.
        if args.phase == "day1":
            preflight = (
                "set -a && test -r /opt/agent/.day1-llm.env && "
                ". /opt/agent/.day1-llm.env && set +a && "
                "test -n \"$LLM_BASE_URL\" && test -n \"$LLM_MODEL\" && "
                "test -n \"$LLM_API_KEY\" && "
                "python -c 'import os; from decimal import Decimal; "
                "value=Decimal(os.environ[\"MODEL_BUDGET_USD\"]); "
                "assert value.is_finite() and Decimal(\"0.05\") <= value <= Decimal(\"85\")' && "
                "test ! -e /opt/agent/.validation-id"
            )
        else:
            preflight = (
                "test ! -e /opt/agent/.day1-llm.env && "
                "test ! -e /opt/agent/.validation-id"
            )
        run(["docker", "run", "--rm", "--network", "none", "--entrypoint", "sh",
             args.image, "-c", preflight])
        target = image_name(values)
        run(["docker", "tag", args.image, target])
        run(["docker", "push", target])
        print("Submitted. Check https://hackathonlive.in-cypher.com/status and /scores")


if __name__ == "__main__":
    try:
        main()
    except ValueError as exc:
        import sys
        print(str(exc), file=sys.stderr)
        raise SystemExit(1)
    except (FileNotFoundError, subprocess.CalledProcessError):
        import sys
        print("Command failed. Check required .env fields, Docker/login, and preceding diagnostics.", file=sys.stderr)
        raise SystemExit(1)

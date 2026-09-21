#!/usr/bin/env python3
"""Narrow wrappers around the inspected organiser harness."""

import importlib
import inspect

from agent_ext.runtime_context import bind_prepared_material, trusted_attempt


def _require_signature(function, names, label):
    if not callable(function) or tuple(inspect.signature(function).parameters) != tuple(names):
        raise RuntimeError(f"Official {label} hook changed; inspect base contract")


def main():
    import main as official_main

    if not callable(getattr(official_main, "is_practice", None)):
        raise RuntimeError("Official practice-selection hook changed; inspect base contract")
    inherited_solve = getattr(official_main, "solve_challenge", None)
    _require_signature(inherited_solve, ("client", "ch", "max_steps"), "solve-challenge")
    solver_module = importlib.import_module(inherited_solve.__module__)
    inherited_build_prompt = getattr(solver_module, "build_prompt", None)
    _require_signature(
        inherited_build_prompt,
        ("ch", "cdir", "filenames", "conn"),
        "prompt-construction",
    )

    def scoped_build_prompt(ch, cdir, filenames, conn):
        bind_prepared_material(ch, cdir, filenames, conn)
        return inherited_build_prompt(ch, cdir, filenames, conn)

    def scoped_solve(client, ch, max_steps):
        with trusted_attempt(ch):
            return inherited_solve(client, ch, max_steps)

    # Practice is useful evaluation material. Keep ONLY_IDS, solver, lifecycle,
    # submission and results ownership with the inherited harness.
    official_main.is_practice = lambda challenge: False
    official_main.solve_challenge = scoped_solve
    solver_module.build_prompt = scoped_build_prompt
    try:
        return official_main.main()
    finally:
        official_main.solve_challenge = inherited_solve
        solver_module.build_prompt = inherited_build_prompt


if __name__ == "__main__":
    raise SystemExit(main())

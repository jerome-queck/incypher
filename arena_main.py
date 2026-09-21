#!/usr/bin/env python3
"""Include practice challenges while retaining the organiser's harness."""


def main():
    import main as official_main

    if not callable(getattr(official_main, "is_practice", None)):
        raise RuntimeError("Official practice-selection hook changed; inspect base contract")
    # Practice is useful evaluation material. Keep ONLY_IDS, solver, lifecycle,
    # submission and results ownership with the inherited harness.
    official_main.is_practice = lambda challenge: False
    return official_main.main()


if __name__ == "__main__":
    raise SystemExit(main())

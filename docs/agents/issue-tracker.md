# Review spec lookup

Use the user-supplied per-PR spec path when present. For the overnight solver build,
the overall scope is [brief.md](../solver-build/brief.md); the main agent freezes a
bounded spec under ignored `private/solver-build-20260921/specs/` before implementation.
Pass that exact spec and resolved review base/head SHAs to both reviewers.

If commits reference a GitHub issue, inspect it with `gh issue view <number>` in this
repository and record the URL and relevant acceptance criteria. Read linked scope
before asserting a requirement. Resolve conflicts against current user authorization.
This repository uses GitHub PRs; creating an issue is not a prerequisite to a review.

Review standards start at `AGENTS.md` and the component docs reached through
[interfaces.md](../interfaces.md). The code-review skill adds its heuristic baseline.
Keep Standards and Spec findings separate; the integrating agent records disposition
and validation. Public PRs contain sanitized descriptions, never private solve traces.

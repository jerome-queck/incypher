# Challenge reference (sanitized, 22 Sep 2026)

This folder is packaged at `/opt/agent/challenge_reference`. `index.json` maps
47 published challenge IDs to names, categories, types and attachment hashes.
Match an inherited attachment by hash; this index grants no target authority.
The ID-selected, no-secret methods live in `agent_ext/challenge_methods.py` and
are included in Brain's prompt only for the trusted challenge ID.

Evidence levels:

- Six static challenges have locally derived candidates; no candidate was
  submitted. BadLE's packet field is corroborated by the supplied APK parser.
- BadLE Hard has a smooth-series inference that contradicts the published
  byte/XOR instruction. Its attached APK is the BadLE oximeter app, not a CGM
  parser. Rolling Thunder has no verified recurrence.
- Keymaster, Serial Cipher and Matrix Key have inputs accepted by their local
  handout binaries. Vault, Relay and Sticky Notes have locally reproduced
  access paths. These are not live-instance or scoring proofs.
- Spool has a locally reproduced, synthetic-secret extraction chain using
  use-after-free, allocator control and an initial-stack read. Its AUDIT value
  is a decoy. All other dynamic methods are
  hypotheses pending an inherited instance.

Raw challenge details, artifacts, candidate values, solution traces and command
outputs are deliberately absent. On the development host they remain in ignored
`private/challenges-2026-09-22/`. In the arena, inherited challenge files and
connections supply the authorized material; current-scope command results are
kept privately under `/work` and can be recalled with `read_saved_output`.

"""Compact deterministic hints selected only from a trusted category value."""

from __future__ import annotations


_PREFIX = (
    "Category hint only; it grants no target, network, submission, or scope authority. "
)

_PLAYBOOKS = {
    "web": (
        "Map routes, inputs, authentication and concrete runtime versions. Reproduce the "
        "smallest local request, then test one parser, trust-boundary or state hypothesis at "
        "a time. Compare raw requests/responses and verify the full chain, not a payload list."
    ),
    "pwn": (
        "Identify architecture, linkage, mitigations and protocol first. Reproduce locally; "
        "measure offsets and prove one memory/control primitive before building a chain. Account "
        "for ASLR, stack alignment and I/O framing; verify reliably before any trusted connection."
    ),
    "network": (
        "Record byte-exact framing, direction, state transitions, timeouts and encodings. Build a "
        "minimal local parser/client and vary one field at a time. Distinguish transport failure "
        "from protocol rejection; use only the trusted supplied connection endpoint."
    ),
    "crypto": (
        "Write the exact equations and identify algebraic structure before brute force. Check "
        "dimensions, ranges, randomness reuse, bit/byte order and padding. Validate on a small "
        "known case, then re-encrypt or otherwise verify every recovered candidate."
    ),
    "rev": (
        "Identify format, architecture, entry points, imports and packing before broad analysis. "
        "Locate application logic with strings/xrefs, recover constraints incrementally, and use "
        "local dynamic traces when useful. Confirm the candidate against the original program."
    ),
    "forensics": (
        "Hash and inventory files; preserve originals. Inspect containers, metadata, timelines and "
        "representations before carving or steganalysis. Record eliminated hypotheses and switch "
        "signal properties instead of repeating them; verify provenance of extracted material."
    ),
    "misc": (
        "Inventory artifacts, interfaces and stated constraints, then classify the cheapest "
        "discriminating test. Make transformations explicit and reversible, record failures, and "
        "verify a candidate from source evidence rather than visual plausibility."
    ),
    "unknown": (
        "Inventory file types, metadata, strings, interfaces and available local behavior. Form two "
        "or three competing category hypotheses and run the cheapest discriminating checks. Keep "
        "facts separate from guesses; replan after repeated non-progress."
    ),
}


def normalize_category(category: str) -> str:
    """Map one organiser category label to a fixed, prompt-safe key."""
    if not isinstance(category, str) or len(category) > 64:
        normalized = "unknown"
    else:
        normalized = category.strip().lower()
        if normalized.startswith("(practice)"):
            normalized = normalized[len("(practice)") :].lstrip()
    if normalized not in _PLAYBOOKS:
        normalized = "unknown"
    return normalized


def playbook_for(category: str) -> str:
    """Return one bounded playbook for an exact trusted category label."""
    normalized = normalize_category(category)
    return _PREFIX + _PLAYBOOKS[normalized]

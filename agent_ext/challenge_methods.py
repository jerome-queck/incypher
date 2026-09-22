"""No-secret method hypotheses for the 22 Sep challenge catalogue.

These are local analysis routes, not flags, inputs, credentials or target authority.
Only trusted numeric challenge metadata selects one. Validate every hypothesis against
the provided file or inherited live instance; challenge prose may be incomplete.
"""

METHODS = {
    3: "Supplied APK parser locally corroborates the sole FE status notification: validate declared length and additive checksum, dispatch type 0x55, then read zero-based byte 5 directly as SpO2. Derive candidate from the actual log; local derivation is not accepted-score proof.",
    4: "Isolate the 17-byte nondeprecated f003 frames. Published frame[6] XOR 0x7c yields implausible values; frame[4] XOR 0x41 instead yields an exact descending 94..81 mg/dL across 14 frames, but is an unaccepted structural inference. The attached APK is byte-identical to #3's oximeter app, not a CGM parser; do not claim APK corroboration or submit the literal inconsistent arithmetic.",
    13: "Eight challenge/response pairs and a sealed frame are published without firmware or recurrence. The 512 observed XOR-mask bits have about 256-bit linear complexity, not a simple 64-bit LFSR; fixed XOR/rotation, 64-bit LCG/xorshift, basic byte rolling, common hash chains and CRC64 did not validate. A proposed recurrence must predict held-out pairs before deriving the ninth response or frame key. Treat this as unresolved; do not guess a candidate.",
    55: "Inspect all 128 DICOM preamble bytes separately from the DICM metadata. The polyglot executable header is evidence, not a reason to execute the file.",
    56: "Parse both DICOM tag sets and compare by tag and original value; identical flag-shaped strings are decoys. Preserve VR and byte-level provenance.",
    57: "Locate the daemon's OBFDATA record, account for its leading NUL and length byte, then apply the configuration's repeating XOR key to exactly that many bytes.",
    58: "Follow the TCP application payloads in the PCAP, including HTTP form data and HL7 NTE segments. Corroborate the same leak across conversations.",
    59: "Invert the source's per-byte license transform, then verify the recovered key against the supplied stripped binary locally before trusting its decrypted output.",
    66: "Build an IHE ITI-18 FindDocuments SOAP request for the supplied patient identifier, parse DocumentEntry repository/unique IDs, then form ITI-43 RetrieveDocumentSet. Verify no consent or relationship check in the assigned instance.",
    74: "Use the issued patient credential on its own resource as a baseline, then vary only the FHIR object identifier in the assigned service. Compare authorization behavior and retrieve the target resource only within that service.",
    78: "Inspect health/banner, test the stated factory service-account hypothesis on login, then request the drug library with the returned bearer token. No generic credential spray.",
    81: "Obtain the ordinary JWT, inspect header/claims and signature handling, then test one concrete role-verification weakness against /admin. A changed claim alone is not proof of a valid token.",
    83: "Construct one byte stream parsed differently as Explicit and Implicit VR Little Endian: place the renderer trigger in implicit interpretation while explicit parser sees innocuous values. Model both element walks locally before upload.",
    64: "Build a minimal ORU^R01 with correct CR-delimited segments. Test whether an OBX value can cross the normalizer's segment boundary into a privileged ZAU segment; compare archive response precisely.",
    82: "Read public metadata, compare QIDO authorization with WADO retrieval for one restricted study, then inspect retrieved pixel LSBs in documented order. Do not assume QIDO denial means WADO denial.",
    86: "Fetch the genuine signed firmware from the assigned service. Identify signature-covered bytes versus unsigned metadata, mutate only the latter and verify signature still passes before testing the update path.",
    87: "Compare WAF and origin URL-decoding order with one harmless marker. If a double-encoding discrepancy exists, use a bounded UNION probe to identify columns and extract only the challenge record.",
    67: "Frame ADT^A01 exactly as MLLP (VT, payload, FS, CR). Vary PID-3 assigning-authority components and compare ACK/NTE translation; malformed framing is not authorization evidence.",
    95: "Supplied ELF local proof: SET decodes up to 2048 bytes into a 64-byte note without a destination bound. Copy 60 bytes: 56 zero bytes, then little-endian 32-bit token for eight zero bytes starting at offset 48. Token starts 0x811c9dc5; per byte XOR, rotate-left 3, add 0x1000193 modulo 2^32. This overwrites the adjacent check at offset 56 and reaches access granted locally. Recompute from the provided binary if it differs; placeholder output is not a live flag.",
    104: "The provided ELF checks four little-endian 32-bit words with modular arithmetic and rotations. Lift all constraints into 32-bit bit-vectors, solve, and verify on the local binary; its placeholder output is not the live flag.",
    105: "Invert the 24-byte validator's multiply/add, byte rotation and position XOR against its .rodata target. Verify the input on the supplied binary; do not use its placeholder output as a flag.",
    116: "Extract the 16x16 signed coefficient matrix and target vector from .rodata; solve the linear system modulo 251 and locally verify the 16-character input.",
    29: "Supplied ELF and glibc 2.31 local proof: shred frees without clearing pointer/size. Allocate a large chunk plus top guard, shred and view it to leak an unsorted-bin libc pointer. Allocate and shred an 0x80 chunk, then edit through its stale slot to poison tcache toward aligned __free_hook-8; allocate twice, write system at the hook, then shred a chunk containing /bin/sh. The matching local loader/libc reached a shell in a network-isolated test. Recompute libc base from the assigned instance leak; no live flag proof.",
    96: "Supplied ELF local proof: calloc(56) note has random guard at offsets 40..47 and open bit at 48. SHOW x emits 8 bytes XOR a per-process 56-byte keystream; SHOW 0 reveals its first 8 because note prefix is zero. Reconstruct the keystream by enumerating byte steps 1..255 (increment mod 256, skip 00/0a/0d), then SHOW 40 reveals guard by XOR. PUT hex of 40 zero bytes + recovered guard + 01 preserves guard and sets open bit. Locally reaches relay open; do not treat the placeholder as live flag.",
    123: "Supplied ELF/glibc local proof: DROP leaves stale pointer/size, so GET/PUT disclose and rewrite freed chunks. Leak libc from an unsorted chunk; for each arbitrary read, use a fresh tcache size class and two freed chunks, infer the safe-linking key, poison next to an aligned target, then allocate twice. Read libc environ to locate the initial stack; parse auxiliary vector AT_EXECFN and read nearby argument/environment strings to recover a removed FLAG value. Five network-isolated local runs with a synthetic value passed. AUDIT is a DECOY, not the secret. No live-instance proof.",
    98: "Inspect RSA parameters for shared factors or close primes; validate factorization by recomposition before decrypting the instance ciphertext.",
    100: "Classify block mode and oracle response, measure prefix alignment and controlled-block behavior, then recover the appended bytes with a verified chosen-plaintext comparison.",
    70: "For ChaCha20 nonce reuse, separate keystream reuse from Poly1305 key reuse; derive a valid tag only after reproducing the oracle's exact message framing.",
    32: "Map distinct token-verification errors, then test a CBC padding oracle one byte at a time. Reconstruct a valid admin payload and authentication field; avoid blind token guesses.",
    30: "Inspect the kiosk's note echo and maintenance dispatch; measure the input boundary and any format-string or overwrite primitive before claiming a path to the secret.",
    73: "Use the first format-string primitive for a bounded address leak, then the second for a measured write. Account for PIE/libc and exact print counts.",
    35: "Automate the twenty short protocol rounds in one connection with strict deadlines; derive each transformation from observed prompts instead of manually answering.",
    34: "Record sparse beacon bytes and timings over one bounded connection; classify framing and state before sending a minimal response.",
    36: "Read the in-band Vaultlang instruction set, then model withdrawal callback ordering and ledger updates. Test a minimal reentry sequence before scaling the payout.",
    27: "Analyze the SSO redirect/link flow and same-origin administrator visit. Show a concrete session-confusion chain locally; do not assume arbitrary external exfiltration is in scope.",
    44: "Compare note sanitizer output with reviewer rendering and the provided /px collector; test one inert parser discrepancy before attempting a same-site session readback.",
    102: "Collect enough issued tokens to identify RNG/state or timestamp dependence; validate prediction against a held-out token before requesting privilege.",
    120: "Inspect nonce reuse or stream correlations from the service transcript; validate the candidate cryptanalytic relation on multiple samples.",
    119: "Determine the effective key/search space from the service's advertised parameters before a bounded search; verify on an independent sample.",
    110: "Capture exact byte framing, checksums and state transitions from the custom protocol; build a minimal client and vary one field at a time.",
    118: "Identify multiplexed channel framing and privileged command state; retain each channel's sequencing and compare structured responses.",
    111: "Read the emulated contract's accounting commands, model integer widths and withdrawal checks, then test one overdraft invariant break.",
    112: "Map ownership initialization and transfer checks in the emulated contract; test authorization state transitions rather than brute force.",
    114: "Only a generic remote memory-bug description is published and no binary is attached. Once the inherited instance supplies a connection, discover protocol and mitigations with bounded non-destructive probes, then establish the bug and a reliable local model. No exploit is established offline.",
    124: "No protocol, artifact or exploit detail is published. Wait for the inherited instance connection; inspect its banner and enumerate bounded commands before forming a concrete Tallygate hypothesis. No offline solve is established.",
    125: "No reversing artifact or protocol is published. Inspect only files provided by the inherited challenge runtime, identify the validation function and verify an inversion locally. No offline solve is established.",
    126: "No artifact or protocol is published. Wait for the inherited instance connection and record framing, state and one discriminating observation before attempting a Tideglass exploit. No offline solve is established.",
}

# Local source-derived candidate or supplied-binary proof. This is a scheduling
# hint, never platform acceptance and never authority to launch an instance.
LOCAL_PROOF_IDS = frozenset({3, 55, 56, 57, 58, 59, 29, 95, 96, 104, 105, 116, 123})


def has_local_proof(challenge_id: int) -> bool:
    return type(challenge_id) is int and challenge_id in LOCAL_PROOF_IDS


def method_for(challenge_id: int) -> str:
    if type(challenge_id) is not int or challenge_id <= 0:
        return ""
    return METHODS.get(challenge_id, "")

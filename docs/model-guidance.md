# Sol and Astra: agent-facing instructions

Verified 21 Sep 2026 against official OpenAI pages. Applies to Codex agents developing
this repository. It does **not** prescribe the arena model: Day 2 injects endpoint/key and
the image selects a compatible served model. These notes guide document/prompt authors;
remain short and branch-specific references carry details.

## GPT-5.6 Sol

The official model page identifies `gpt-5.6-sol` as a reasoning model; `gpt-5.6` routes to
Sol. Its supported API surfaces include Responses and Chat Completions.
[Model page](https://developers.openai.com/api/docs/models/gpt-5.6-sol)

OpenAI's GPT-5.6 guidance favors lean prompts, one statement per instruction, concise
tool descriptions, explicit action boundaries and measurable evaluations after pruning.
Short outputs should retain required evidence, caveats and next steps.
[GPT-5.6 prompting](https://developers.openai.com/api/docs/guides/latest-model/gpt-5.6#prompting-best-practices)

Repository application: start from one objective and completion criterion; load the
relevant doc, change owned paths, verify behavior and return evidence. Avoid repeated
“be concise” or “ask first” rules that hide necessary work. Retain a specific example
only when it resolves an observed ambiguity.

## GPT-6 Astra

Official guidance highlights strong instruction sensitivity, possible extra clarification
pauses, detailed output, reduced delegation unless specified, and potentially excessive
testing for small changes. It recommends explicit scope/autonomy, conflict audits of
skills and `AGENTS.md`, desired writing style and proportional verification.
[Astra guidance](https://developers.openai.com/api/docs/guides/latest-model/gpt-6-astra.md#prompting-best-practices)

Repository application: continue authorized work through completion; user decisions
supersede stale planning notes. Make pause reasons concrete. Delegate only when the
session permits it and provide owned paths, required evidence and a bounded handoff.
After relevant checks pass, move to the requested PR/merge instead of repeating them.

Astra tool calling requires Responses; it does not support custom `temperature` or
`top_p`, or `none` reasoning. Therefore changing this repo's Chat Completions model string
to Astra is not a supported migration. No API migration is included here.
[Astra compatibility](https://developers.openai.com/api/docs/guides/latest-model#gpt-6-astra-what-is-new)

## Shared context contract

This repo applies the user-supplied `writing-for-agents` skill's principles:
keep one authoritative rule, use explicit
trigger → document pointers, separate steps from reference, and require observable
completion. These are repository design choices, not measured Sol/Astra performance
claims. [Context handoff](context.md#context-management) is the reusable packet.

Document facts with source/date, hypotheses as hypotheses, and current implementation
separately from planned behavior. A future agent should never infer “active” from
“merged,” “works live” from “tested synthetically,” or “current image” from an old digest.

## Authentication

OpenAI supports ChatGPT subscription sign-in for local Codex CLI/app work and API-key
sign-in billed separately. General OpenAI API calls still use Platform keys; enterprise
Codex access tokens are for trusted Codex workflows, not generic API replacement.
[Authentication](https://learn.chatgpt.com/docs/auth)

`codex exec` reuses saved CLI authentication and can return schema-constrained output.
Official guidance favors API keys for automation and warns against moving account-auth
files into public/open-source repository CI. Our local path keeps login on each user's
machine; the arena path uses its own provider/runtime credentials.
[Non-interactive mode](https://learn.chatgpt.com/docs/non-interactive-mode)

On the audit machine: CLI `0.155.0-alpha.9.2`, `codex login status` reported ChatGPT login.
No credential contents were inspected, and no subscription-backed live solve was run.
See [setup](setup.md) for the exact separation and Day-1/Day-2 behavior.

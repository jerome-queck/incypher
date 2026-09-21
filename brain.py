"""OpenAI-compatible autonomous CTF brain.

This preserves the official Brain interface while redacting flags from logs and accepting
flags returned as either tool calls or assistant text.
"""
from __future__ import annotations

import json
import os
import re

import requests

from agent_ext.adapters import LLMConfig

FLAG_RE = re.compile(r"INCYPHER\{[^{}\r\n]{1,512}\}")

TOOLS = [
    {"type": "function", "function": {
        "name": "run_bash",
        "description": ("Run a shell command in the solver container and return stdout+stderr. "
                        "Available: curl, wget, nc, nmap, python3 (pwntools, pycryptodome, requests, "
                        "sympy), file, xxd, strings, objdump, gdb, binwalk. Challenge files are in "
                        "/work/<id>/. Commands time out after 120s."),
        "parameters": {"type": "object",
                       "properties": {"command": {"type": "string"}},
                       "required": ["command"]}}},
    {"type": "function", "function": {
        "name": "submit_flag",
        "description": "Submit a candidate flag. Only call this with evidence from the challenge.",
        "parameters": {"type": "object",
                       "properties": {"flag": {"type": "string"}},
                       "required": ["flag"]}}},
]

SYSTEM = """You are an autonomous CTF-solving agent in an authorized security-education
hackathon. All challenges are intentionally vulnerable practice targets.
You are given ONE challenge: name, category, points, description, any downloaded files
(under /work/<id>/), and connection info for a live instance if present (a URL for web, or
host:port for pwn/network).
Work methodically: recon (read description; inspect files with file/strings/xxd/cat; probe
services with curl -sv / nc), form a hypothesis for the category, exploit it with concrete
commands (write Python only under /tmp, then run it), and when you recover a flag call
submit_flag. Flag format is INCYPHER{...}. For web, try factory/default credentials,
auth-token/JWT flaws, and cleartext data. For files, always run file/strings/xxd first.
Be decisive; do not repeat identical commands; never fabricate a flag. Never attack the
platform, Agent API, registry, ingress, other teams, or anything outside the supplied
challenge files and instance. Submit only high-confidence candidates and never submit more
than three candidates for one challenge."""


def _redact(text: str) -> str:
    return FLAG_RE.sub("[flag redacted]", text)


class Brain:
    def __init__(self, run_bash, submit_flag, max_steps=40, verbose=True):
        self.run_bash = run_bash
        self.submit_flag = submit_flag
        self.max_steps = max_steps
        self.max_submissions = int(os.environ.get("MAX_SUBMISSIONS", "3"))
        self.submissions = 0
        self.verbose = verbose
        self.s = requests.Session()
        self.s.headers.update({
            "Content-Type": "application/json",
            "HTTP-Referer": "https://in-cypher.com",
            "X-Title": "IN-CYPHER Arena",
        })

    def _log(self, *parts):
        if self.verbose:
            print("   ", *(_redact(str(part)) for part in parts), flush=True)

    def _chat(self, messages):
        config = LLMConfig.from_environment(os.environ)
        body = {"model": config.model, "messages": messages, "tools": TOOLS,
                "tool_choice": "auto", "temperature": 0.2, "max_tokens": 4096}
        response = self.s.post(config.chat_url,
                               headers={"Authorization": "Bearer " + config.api_key},
                               data=json.dumps(body), timeout=180)
        response.raise_for_status()
        return response.json()["choices"][0]["message"]

    def _invalid_tool_arguments(self, name):
        """Allow admitted adapters to classify a rejected request before repair."""

    def _submit(self, flag: str, step: int):
        if self.submissions >= self.max_submissions:
            self._log("[step %d] submission budget exhausted" % step)
            return {"solved": False, "steps": step,
                    "error": "submission budget exhausted"}
        self.submissions += 1
        verdict = self.submit_flag(flag)
        status = verdict.get("status") if isinstance(verdict, dict) else None
        if not isinstance(status, str):
            status = "uncertain"
        if status not in ("correct", "incorrect", "already_solved", "ratelimited", "error"):
            status = "uncertain"
        self._log("[step %d] SUBMIT [flag redacted] -> %s" % (step, status))
        if status in ("correct", "already_solved"):
            return {"solved": True, "steps": step, "flag": flag, "verdict": verdict}
        if status in ("ratelimited", "error", "uncertain"):
            return {"solved": False, "steps": step, "verdict": {"status": status},
                    "error": "submission unavailable: %s" % status}
        return None

    def solve(self, prompt: str) -> dict:
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": prompt}]
        submitted = set()
        steps = 0

        for steps in range(1, self.max_steps + 1):
            try:
                message = self._chat(messages)
            except Exception as exc:  # noqa: BLE001 - failure is part of the result contract
                return {"solved": False, "steps": steps,
                        "error": "%s: model request failed" % type(exc).__name__}

            if not isinstance(message, dict):
                return {"solved": False, "steps": steps, "error": "malformed model message"}
            tool_calls = message.get("tool_calls")
            tool_calls = [] if tool_calls is None else tool_calls
            content = message.get("content")
            content = "" if content is None else content
            if (not isinstance(content, str) or not isinstance(tool_calls, list)
                    or any(not isinstance(call, dict)
                           or not isinstance(call.get("function"), dict)
                           or not isinstance(call["function"].get("name"), str)
                           for call in tool_calls)):
                return {"solved": False, "steps": steps, "error": "malformed model message"}
            assistant_turn = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_turn["tool_calls"] = tool_calls
            messages.append(assistant_turn)

            if not tool_calls:
                # Some compatible endpoints return the recovered flag as ordinary text even
                # when tools were requested. Treat that as a submission, not an unsolved stop.
                candidates = [flag for flag in FLAG_RE.findall(content) if flag not in submitted]
                for flag in candidates:
                    if flag in submitted:
                        continue
                    submitted.add(flag)
                    result = self._submit(flag, steps)
                    if result:
                        return result
                self._log("[step %d] model stopped: %s" % (steps, content[:180]))
                return {"solved": False, "steps": steps, "final": _redact(content)}

            for tool_call in tool_calls:
                function = tool_call.get("function", {}) or {}
                name = function.get("name")
                try:
                    arguments = json.loads(function.get("arguments") or "{}")
                except Exception:  # noqa: BLE001 - malformed tool arguments go back to model
                    arguments = None

                argument_name = {"run_bash": "command", "submit_flag": "flag"}.get(name)
                if (not isinstance(arguments, dict)
                        or (argument_name is not None
                            and (not isinstance(arguments.get(argument_name), str)
                                 or not arguments[argument_name].strip()))):
                    self._invalid_tool_arguments(name)
                    messages.append({"role": "tool", "tool_call_id": tool_call.get("id"),
                                     "content": "Invalid tool arguments; supply a nonempty string field."})
                    continue

                if name == "run_bash":
                    command = arguments.get("command", "")
                    self._log("[step %d] $ %s" % (steps, command[:160]))
                    output = self.run_bash(command)
                    messages.append({"role": "tool", "tool_call_id": tool_call.get("id"),
                                     "content": (output or "")[:12000]})
                elif name == "submit_flag":
                    flag = arguments.get("flag", "")
                    if flag in submitted:
                        messages.append({"role": "tool", "tool_call_id": tool_call.get("id"),
                                         "content": "Candidate already submitted; use new evidence."})
                        continue
                    submitted.add(flag)
                    result = self._submit(flag, steps)
                    if result:
                        return result
                    messages.append({"role": "tool", "tool_call_id": tool_call.get("id"),
                                     "content": "Flag rejected."})
                else:
                    messages.append({"role": "tool", "tool_call_id": tool_call.get("id"),
                                     "content": "Unknown tool."})

        return {"solved": False, "steps": steps, "final": "step budget exhausted"}

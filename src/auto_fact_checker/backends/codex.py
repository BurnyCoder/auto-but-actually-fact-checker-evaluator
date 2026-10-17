"""Codex CLI agent backend: `codex exec` with JSONL events.

Local: builds the command (model, reasoning effort, live web search, approvals/sandbox bypass, isolation from the
user's ~/.codex config and desktop-control features, optional multi-agent) and parses the JSONL events.
Global context: used for steps with kind="agent", provider="openai" (OpenAI agents are preferred by the user).
Codex reports tokens only, so the cost is computed from catalog prices. Docs:
https://learn.chatgpt.com/docs/non-interactive-mode and https://learn.chatgpt.com/docs/config-file/config-reference
(flags verified against `codex exec --help`, v0.163.0; `codex exec --search` is rejected, so web search is enabled
with `-c web_search="live"`).
"""

import logging
from pathlib import Path

from .. import catalog
from ..config import get_settings
from .base import LLMRequest, LLMResult, dedupe
from .subprocess_jsonl import run_agent, urls_in

# Features switched off for fact-check agents: desktop/browser control, apps/plugins and hooks from the user's setup.
ISOLATION_FEATURES = ["computer_use", "browser_use", "browser_use_external", "in_app_browser", "apps", "plugins",
                      "hooks"]


def build_cmd(req: LLMRequest, exe: str, workdir: Path) -> list[str]:
    """Command line; the trailing '-' makes codex read the prompt from stdin."""
    cmd = [exe, "exec", "-m", req.model,
           "-c", f'web_search="{"live" if req.web_search else "disabled"}"',  # value parsed as TOML
           "-c", f"model_reasoning_effort={req.effort}",
           "--ignore-user-config", "--ignore-rules",  # do not inherit ~/.codex/config.toml or AGENTS.md rules
           "--skip-git-repo-check", "--ephemeral",  # temp dir is no git repo; keep no session files
           "--dangerously-bypass-approvals-and-sandbox",  # agents run free (user requirement)
           "--json", "--color", "never", "-C", str(workdir)]
    for feature in ISOLATION_FEATURES:
        cmd += ["--disable", feature]
    cmd += ["--enable" if req.allow_subagents else "--disable", "multi_agent"]  # Codex subagents
    return cmd + ["-"]


def parse_events(req: LLMRequest, events: list[dict], billed: bool) -> LLMResult:
    """Last agent_message is the answer; usage is summed over turn.completed events."""
    items = [e["item"] for e in events if e.get("type") == "item.completed" and isinstance(e.get("item"), dict)]
    messages = [i.get("text", "") for i in items if i.get("type") == "agent_message"]
    usage = [e.get("usage") or {} for e in events if e.get("type") == "turn.completed"]
    tin = sum(u.get("input_tokens", 0) for u in usage)
    cached = sum(u.get("cached_input_tokens", 0) for u in usage)
    tout = sum(u.get("output_tokens", 0) for u in usage)
    searches = sum(1 for i in items if i.get("type") == "web_search")
    errors = [str(e.get("message") or e.get("error")) for e in events if e.get("type") in ("error", "turn.failed")]
    return LLMResult(text=messages[-1] if messages else "", backend="codex", model=req.model, input_tokens=tin,
                     cached_input_tokens=cached, output_tokens=tout, web_searches=searches, billed=billed,
                     cost_usd=catalog.cost_usd(req.model, tin, tout, cached, searches),
                     error="; ".join(errors) or (None if messages else "no agent_message"),
                     sources=dedupe(urls_in("\n".join(str(i.get("text", "")) for i in items))))


def call(req: LLMRequest, log: logging.Logger | logging.LoggerAdapter) -> LLMResult:
    """Run `codex exec` and return the normalised result."""
    s = get_settings()
    key = s.openai_api_key.get_secret_value() if s.openai_api_key else None
    return run_agent(req, log, exe_name="codex", exe_override=s.codex_bin, keys={"CODEX_API_KEY": key},
                     build=build_cmd, parse=parse_events)

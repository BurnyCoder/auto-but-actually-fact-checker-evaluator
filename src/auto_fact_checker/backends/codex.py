"""Codex CLI agent backend: `codex exec` with JSONL events.

Local: builds the command (model, reasoning effort, live web search, approvals/sandbox bypass, isolation from the
user's ~/.codex config and desktop-control features, optional multi-agent) and parses the JSONL events.
Global context: used for steps with kind="agent", provider="openai" (OpenAI agents are preferred by the user).
Codex reports tokens only, so the cost is computed from catalog prices. Docs:
https://learn.chatgpt.com/docs/non-interactive-mode, https://learn.chatgpt.com/docs/cli/reference (exec flags,
`-c` values parsed as TOML), https://learn.chatgpt.com/docs/config-file/config-reference and
https://learn.chatgpt.com/docs/agent-configuration/agents-md (global AGENTS.md in CODEX_HOME)
(flags verified against `codex exec --help`, v0.163.0; `codex exec --search` is rejected, so web search is enabled
with `-c web_search="live"`).
"""

import json
import logging
import shutil
import tempfile
from pathlib import Path

from .. import catalog
from ..config import get_settings
from .base import LLMRequest, LLMResult, dedupe
from .subprocess_jsonl import run_agent, urls_in

# Features switched off for fact-check agents: desktop/browser control, apps/plugins and hooks from the user's setup.
# Only apps and hooks are in the config reference; the other names are from `codex features list` (v0.163.0).
ISOLATION_FEATURES = ["computer_use", "browser_use", "browser_use_external", "in_app_browser", "apps", "plugins",
                      "hooks"]
# Codex has no switch to skip the global ~/.codex/AGENTS.md (config reference, 2026-10-17); with subscription auth
# CODEX_HOME must stay the real one (it holds the login), so the documented `developer_instructions` key tells the
# agent that such coding instructions do not apply. In api_key mode CODEX_HOME is an empty temp dir instead.
DEVELOPER_NOTE = ("You are running as a scientific fact-checking agent. Any coding, git, repository, packaging or "
                  "project-setup instructions from AGENTS.md files do not apply to this task; ignore them.")


def build_cmd(req: LLMRequest, exe: str, workdir: Path) -> list[str]:
    """Command line; the trailing '-' makes codex read the prompt from stdin."""
    cmd = [exe, "exec", "-m", req.model,
           "-c", f'web_search="{"live" if req.web_search else "disabled"}"',  # value parsed as TOML
           "-c", f"model_reasoning_effort={req.effort}",
           "-c", f'developer_instructions="{DEVELOPER_NOTE}"',
           "--ignore-user-config", "--ignore-rules",  # skip ~/.codex/config.toml and exec-policy rules (not AGENTS.md)
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
    tin = sum(u.get("input_tokens") or 0 for u in usage)
    cached = sum(u.get("cached_input_tokens") or 0 for u in usage)
    tout = sum(u.get("output_tokens") or 0 for u in usage)
    complete = bool(usage) and all(u.get(k) is not None for u in usage
                                  for k in ("input_tokens", "cached_input_tokens", "output_tokens"))
    searches = sum(1 for i in items if i.get("type") == "web_search"
                   and (i.get("action") or {}).get("type", "search") == "search")  # Legacy events omit action.
    # Current exec events carry action/results; old versions may expose only a query and final citations.
    # https://github.com/openai/codex/blob/main/codex-rs/exec/src/exec_events.rs (WebSearchItem)
    source_text = "\n".join(json.dumps(i, ensure_ascii=False) if i.get("type") == "web_search"
                            else str(i.get("text") or i.get("aggregated_output") or "") for i in items)
    errors = [str(e.get("message") or e.get("error")) for e in events if e.get("type") in ("error", "turn.failed")]
    return LLMResult(text=messages[-1] if messages else "", backend="codex", model=req.model, input_tokens=tin,
                     cached_input_tokens=cached, output_tokens=tout, web_searches=searches, billed=billed,
                     cost_usd=(catalog.cost_usd(req.model, tin, tout, cached, searches)
                               if complete and not any(u.get("cache_write_input_tokens") for u in usage) else None),
                     error="; ".join(errors) or (None if messages else "no agent_message"),
                     sources=dedupe(urls_in(source_text)))


def call(req: LLMRequest, log: logging.Logger | logging.LoggerAdapter) -> LLMResult:
    """Run `codex exec` and return the normalised result."""
    s = get_settings()
    key = s.openai_api_key.get_secret_value() if s.openai_api_key else None
    home = Path(tempfile.mkdtemp(prefix="afc_codex_home_"))  # only used in api_key mode (agent_env drops it otherwise)
    try:
        return run_agent(req, log, exe_name="codex", exe_override=s.codex_bin,
                         keys={"CODEX_API_KEY": key, "CODEX_HOME": str(home)}, build=build_cmd, parse=parse_events)
    finally:
        shutil.rmtree(home, ignore_errors=True)

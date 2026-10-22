"""Claude Code agent backend: `claude -p` in headless mode with stream-json output.

Local: builds the CLI command (model, effort, permissions bypass, isolation from the user's global config,
optional --agents subagent file, web/subagent tool toggles, budget/turn caps) and parses the stream-json events.
Global context: used for steps with kind="agent", provider="anthropic"; with subagent strategies the check step
passes prompts.build_agents() definitions so the main agent can spawn claim-checker / scientist subagents.
Docs: headless mode https://code.claude.com/docs/en/headless ; CLI flags https://code.claude.com/docs/en/cli-reference ;
subagents https://code.claude.com/docs/en/sub-agents (verified against `claude --help`, v2.1.302).
"""

import json
import logging
from pathlib import Path

from ..config import get_settings
from .base import LLMRequest, LLMResult, dedupe
from .subprocess_jsonl import run_agent, urls_in

EFFORT = {"none": "low", "minimal": "low"}  # --effort accepts low|medium|high|xhigh|max


def build_cmd(req: LLMRequest, exe: str, agents_file: Path | None) -> list[str]:
    """Command line; the prompt itself is written to stdin (no Windows 32K command-line limit)."""
    cmd = [exe, "-p", "--output-format", "stream-json", "--verbose",  # stream-json in -p mode needs --verbose
           "--model", req.model, "--effort", EFFORT.get(req.effort, req.effort),
           "--dangerously-skip-permissions",  # agents run free (user requirement): no permission prompts
           "--no-session-persistence",
           "--setting-sources", "project",  # do not load the user's ~/.claude settings into fact-check agents
           "--strict-mcp-config", "--disable-slash-commands"]  # no MCP servers / skills from the user's setup
    deny = ([] if req.web_search else ["WebSearch", "WebFetch"]) + ([] if req.allow_subagents else ["Agent", "Task"])  # tool renamed Task->Agent in 2.1.63
    if deny:
        cmd += ["--disallowedTools", ",".join(deny)]  # one comma-separated value (flag is variadic)
    if agents_file:
        cmd += ["--agents", str(agents_file)]  # with -p, --agents accepts a file path
    if req.max_turns:
        cmd += ["--max-turns", str(req.max_turns)]
    if req.max_budget_usd:
        cmd += ["--max-budget-usd", str(req.max_budget_usd)]
    return cmd


def parse_events(req: LLMRequest, events: list[dict], billed: bool) -> LLMResult:
    """Final text/cost from the 'result' event; tokens and searches from modelUsage (includes subagents)."""
    result = next((e for e in reversed(events) if e.get("type") == "result"), None) or {}
    usage = result.get("modelUsage") or {}
    cached = sum(m.get("cacheReadInputTokens", 0) for m in usage.values())
    written = sum(m.get("cacheCreationInputTokens", 0) for m in usage.values())
    tin = sum(m.get("inputTokens", 0) for m in usage.values()) + cached + written
    tool_results = [json.dumps(b.get("content"), ensure_ascii=False) for e in events if e.get("type") == "user"
                    for b in (e.get("message") or {}).get("content", []) if isinstance(b, dict)
                    and b.get("type") == "tool_result"]  # WebSearch/WebFetch results carry the URLs
    error = None if result and not result.get("is_error") else (  # e.g. "refusal: API Error: ... can't help ..."
        f"{result.get('stop_reason') or result.get('subtype')}: {str(result.get('result', ''))[:300]}"
        if result else "no result event")
    return LLMResult(text=result.get("result") or "", backend="claude_code", model=req.model, input_tokens=tin,
                     cached_input_tokens=cached, cache_creation_input_tokens=written,
                     output_tokens=sum(m.get("outputTokens", 0) for m in usage.values()),
                     web_searches=sum(m.get("webSearchRequests", 0) for m in usage.values()),
                     cost_usd=result.get("total_cost_usd"), billed=billed, error=error,
                     sources=dedupe(urls_in("\n".join(tool_results + [result.get("result") or ""]))))


def isolation_settings() -> dict:
    """--settings content that keeps the user's memory files out of fact-check agents.

    `--setting-sources project` does not stop ~/.claude/CLAUDE.md from loading (our live canary test answered YES),
    but `claudeMdExcludes` applies at every settings layer incl. --settings:
    https://code.claude.com/docs/en/memory#exclude-specific-claude-md-files (patterns match absolute paths);
    --settings is the "Command line" layer: https://code.claude.com/docs/en/settings#settings-precedence.
    Managed (organization) CLAUDE.md files cannot be excluded this way.
    """
    home = Path.home() / ".claude"
    explicit = [str(home / "CLAUDE.md"), (home / "CLAUDE.md").as_posix(), str(home / "rules"), (home / "rules").as_posix()]
    return {"claudeMdExcludes": ["**/CLAUDE.md", "**/CLAUDE.local.md", "**/AGENTS.md", "**/.claude/rules/**",
                                 *explicit], "autoMemoryEnabled": False}


def _build(req: LLMRequest, exe: str, workdir: Path) -> list[str]:
    """Write the --agents and --settings files into the agent's temp working directory."""
    agents_file = None
    if req.agents:
        agents_file = workdir / "agents.json"
        agents_file.write_text(json.dumps(req.agents, ensure_ascii=False, indent=1), encoding="utf-8")
    settings_file = workdir / "afc_settings.json"
    settings_file.write_text(json.dumps(isolation_settings(), indent=1), encoding="utf-8")
    return build_cmd(req, exe, agents_file) + ["--settings", str(settings_file)]


def call(req: LLMRequest, log: logging.Logger | logging.LoggerAdapter) -> LLMResult:
    """Run `claude -p` and return the normalised result."""
    s = get_settings()
    key = s.anthropic_api_key.get_secret_value() if s.anthropic_api_key else None
    return run_agent(req, log, exe_name="claude", exe_override=s.claude_bin, keys={"ANTHROPIC_API_KEY": key},
                     build=_build, parse=parse_events)

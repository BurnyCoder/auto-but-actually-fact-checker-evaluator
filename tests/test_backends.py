"""Tests for backends/: request building and response parsing for all four backends, without network calls.

Global context: pipeline steps call backends.call_llm(LLMRequest) and only see LLMResult, so every backend must
map its own wire format (Responses API, Messages API, Claude Code stream-json, Codex JSONL) to the same fields:
text, tokens, web searches, sources and cost. Fakes stand in for the SDK clients and CLI processes.
"""

import json
import logging
import sys
import tomllib
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from auto_fact_checker.backends import anthropic_api, claude_code, codex, openai_api, subprocess_jsonl
from auto_fact_checker.backends.base import LLMRequest

FIX = Path(__file__).parent / "fixtures"
LOG = logging.getLogger("afc.test")


def req(**kw) -> LLMRequest:
    base = dict(backend="openai_api", model="gpt-6-luna", prompt="Fact-check: Gödel ≥ Turing", label="t")
    return LLMRequest(**(base | kw))


# ---------- shared subprocess streamer ----------

def test_run_jsonl_streams_events_and_utf8_stdin(tmp_path):
    child = ("import sys, json\n"
             "data = sys.stdin.read()\n"
             "print('not json noise', flush=True)\n"
             "print(json.dumps({'type': 'echo', 'text': data}), flush=True)\n")
    seen = []
    env = subprocess_jsonl.agent_env("subscription", {})  # sets PYTHONIOENCODING=utf-8 for the Python child
    out = subprocess_jsonl.run_jsonl([sys.executable, "-c", child], "Gödel — ≥", env=env, cwd=tmp_path,
                                     timeout_s=30, log=LOG, on_event=seen.append)
    assert out.events == [{"type": "echo", "text": "Gödel — ≥"}] and seen == out.events  # UTF-8 round-trip
    assert "not json noise" in out.raw_lines and out.returncode == 0 and not out.timed_out


def test_run_jsonl_timeout_kills(tmp_path):
    out = subprocess_jsonl.run_jsonl([sys.executable, "-c", "import time; time.sleep(30)"], "", env=None,
                                     cwd=tmp_path, timeout_s=1, log=LOG)
    assert out.timed_out


def test_agent_env_subscription_strips_keys(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "x")
    monkeypatch.setenv("OPENAI_API_KEY", "y")
    env = subprocess_jsonl.agent_env("subscription", {"ANTHROPIC_API_KEY": "secret"})
    assert "ANTHROPIC_API_KEY" not in env and "OPENAI_API_KEY" not in env  # agents use their own logins
    env2 = subprocess_jsonl.agent_env("api_key", {"CODEX_API_KEY": "secret"})
    assert env2["CODEX_API_KEY"] == "secret"


# ---------- Claude Code ----------

def test_claude_cmd_flags(tmp_path):
    r = req(backend="claude_code", model="claude-haiku-5-5", effort="none", web_search=False, allow_subagents=False,
            max_turns=7, max_budget_usd=0.5)
    cmd = claude_code.build_cmd(r, "claude.exe", agents_file=None)
    assert cmd[:2] == ["claude.exe", "-p"] and "--dangerously-skip-permissions" in cmd
    assert cmd[cmd.index("--model") + 1] == "claude-haiku-5-5" and cmd[cmd.index("--effort") + 1] == "low"
    assert cmd[cmd.index("--disallowedTools") + 1] == "WebSearch,WebFetch,Agent,Task"
    assert cmd[cmd.index("--max-turns") + 1] == "7" and cmd[cmd.index("--max-budget-usd") + 1] == "0.5"
    assert {"--strict-mcp-config", "--no-session-persistence", "--disable-slash-commands"} <= set(cmd)
    cmd2 = claude_code.build_cmd(req(backend="claude_code", web_search=True, allow_subagents=True), "c.exe",
                                 agents_file=tmp_path / "agents.json")
    assert "--disallowedTools" not in cmd2 and cmd2[cmd2.index("--agents") + 1].endswith("agents.json")


def test_claude_parse_events():
    events = [json.loads(line) for line in (FIX / "claude_stream.jsonl").read_text(encoding="utf-8").splitlines()]
    res = claude_code.parse_events(req(backend="claude_code", model="claude-haiku-5-5"), events, billed=False)
    assert res.text.startswith("Final report") and res.cost_usd == pytest.approx(0.0123) and not res.billed
    assert res.web_searches == 2 and res.input_tokens == 1600 and res.output_tokens == 300
    assert "https://arxiv.org/abs/2005.14165" in res.sources and res.error is None


# ---------- Codex ----------

def test_codex_cmd_flags(tmp_path):
    cmd = codex.build_cmd(req(backend="codex", web_search=True, effort="low", allow_subagents=False), "codex.exe",
                          tmp_path)
    assert cmd[:2] == ["codex.exe", "exec"] and cmd[-1] == "-"  # prompt from stdin
    assert 'web_search="live"' in cmd and "model_reasoning_effort=low" in cmd
    assert {"--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "--ephemeral", "--json",
            "--dangerously-bypass-approvals-and-sandbox"} <= set(cmd)
    assert cmd[cmd.index("multi_agent") - 1] == "--disable"  # no subagents unless allowed
    assert "computer_use" in cmd  # isolation: desktop-control features are switched off
    off = codex.build_cmd(req(backend="codex", web_search=False), "codex.exe", tmp_path)
    assert 'web_search="disabled"' in off


def test_codex_subagent_roles(tmp_path):
    """Claude-style --agents definitions become Codex roles: `-c agents.<name>.*` plus one TOML layer per role."""
    agents = {"claim-checker": {"description": "Checks one claim.", "prompt": 'Say "hi" — Gödel\nthen stop',
                                "model": "inherit", "disallowedTools": ["WebSearch", "WebFetch"]}}
    cmd = codex._build(req(backend="codex", web_search=True, effort="low", allow_subagents=True, agents=agents,
                           max_subagents=6), "codex.exe", tmp_path)
    assert "--ephemeral" not in cmd  # spawn_agent fails with "no rollout found" in ephemeral sessions (live spike)
    assert "agents.max_concurrent_threads_per_session=6" in cmd  # Codex's own cap must not drop parallel spawns
    assert cmd[cmd.index("multi_agent") - 1] == "--enable"
    role = tmp_path / "agents" / "claim-checker.toml"
    assert f"agents.claim-checker.config_file={json.dumps(role.as_posix())}" in cmd
    assert 'agents.claim-checker.description="Checks one claim."' in cmd
    assert tomllib.loads(role.read_text(encoding="utf-8")) == {
        "developer_instructions": 'Say "hi" — Gödel\nthen stop', "model": "gpt-6-luna",
        "model_reasoning_effort": "low", "web_search": "disabled"}  # "inherit" -> the lead agent's model


def test_codex_parse_events():
    events = [json.loads(line) for line in (FIX / "codex_exec.jsonl").read_text(encoding="utf-8").splitlines()]
    res = codex.parse_events(req(backend="codex"), events, billed=True)
    assert res.text.startswith("Final report") and res.web_searches == 1
    assert res.input_tokens == 2000 and res.cached_input_tokens == 500 and res.output_tokens == 400
    assert res.cost_usd == pytest.approx((1500 * 0.10 + 500 * 0.01 + 400 * 0.50) / 1e6 + 0.01)
    assert "https://arxiv.org/abs/2005.14165" in res.sources


# ---------- OpenAI Responses API ----------

def test_openai_kwargs():
    kw = openai_api.build_kwargs(req(web_search=True, max_searches=4, blocked_domains=["huggingface.co"]))
    tool = kw["tools"][0]
    assert tool["type"] == "web_search" and tool["filters"] == {"blocked_domains": ["huggingface.co"]}
    assert kw["max_tool_calls"] == 4 and kw["include"] == ["web_search_call.action.sources"]
    assert "tools" not in openai_api.build_kwargs(req(web_search=False))  # non-agentic single call


def test_openai_parse_response():
    search = NS(type="web_search_call", action=NS(type="search", query="q",
                                                  sources=[NS(type="url", url="https://a.org")]))
    page = NS(type="web_search_call", action=NS(type="open_page", url="https://b.org"))
    msg = NS(type="message", content=[NS(type="output_text", text="hi",
                                         annotations=[NS(type="url_citation", url="https://c.org")])])
    usage = NS(input_tokens=1000, output_tokens=100, input_tokens_details=NS(cached_tokens=0))
    res = openai_api.parse_response(req(), NS(output=[search, page, msg], output_text="hi", usage=usage))
    assert res.text == "hi" and res.web_searches == 1  # only "search" actions are billed tool calls
    assert res.sources == ["https://a.org", "https://b.org", "https://c.org"]
    assert res.cost_usd == pytest.approx((1000 * 0.10 + 100 * 0.50) / 1e6 + 0.01)


# ---------- Anthropic Messages API ----------

class FakeStream:
    def __init__(self, msg):
        self.msg = msg

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def __iter__(self):
        return iter([])

    def get_final_message(self):
        return self.msg


def amsg(stop, blocks, searches=0):
    return NS(stop_reason=stop, content=blocks,
              usage=NS(input_tokens=1000, output_tokens=100, server_tool_use=NS(web_search_requests=searches)))


def test_anthropic_pause_turn_loop():
    first = amsg("pause_turn", [NS(type="web_search_tool_result", content=[NS(url="https://x.org")])], searches=2)
    second = amsg("end_turn", [NS(type="text", text="Done", citations=[NS(url="https://y.org")])], searches=1)
    calls = []

    class Client:
        class messages:
            @staticmethod
            def stream(**kw):
                calls.append(kw)
                return FakeStream(first if len(calls) == 1 else second)

    r = req(backend="anthropic_api", model="claude-haiku-5-5", web_search=True, max_searches=3)
    res = anthropic_api.run(Client, r, LOG)
    assert len(calls) == 2 and calls[1]["messages"][-1]["role"] == "assistant"  # continued after pause_turn
    assert calls[0]["tools"][0]["type"] == "web_search_20260318" and calls[0]["tools"][0]["max_uses"] == 3
    assert res.text == "Done" and res.web_searches == 3 and res.sources == ["https://x.org", "https://y.org"]
    assert res.cost_usd == pytest.approx(2 * (1000 * 0.10 + 100 * 0.50) / 1e6 + 0.03)


def test_claude_refusal_is_reported_with_reason():
    events = [{"type": "result", "subtype": "success", "is_error": True, "stop_reason": "refusal",
               "result": "API Error: Haiku 5.5 can't help with this.", "total_cost_usd": 0.01, "modelUsage": {}}]
    res = claude_code.parse_events(req(backend="claude_code", model="claude-haiku-5-5"), events, billed=False)
    assert res.error.startswith("refusal: API Error")  # bench caches refusals as final (scored wrong)

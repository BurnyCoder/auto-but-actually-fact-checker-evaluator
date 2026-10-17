"""Live smoke tests: real calls to gpt-6-luna, claude-haiku-5-5, Claude Code and Codex (run with `pytest -m live`).

Global context: verifies the assumptions the offline tests cannot: SDK parameters accepted by the APIs, web search
actually used, CLI flags/event formats of `claude -p` and `codex exec`, subagent spawning, subscription auth with
keys stripped, isolation from the user's global agent instructions, and that the JSON contract parses on real
model output. Every call is checked against and recorded in the spend ledger (SPEND_LIMIT_USD).
Expected total cost: a few cents (agent runs use subscription auth by default and are not billed).
"""

import logging

import pytest

from auto_fact_checker import backends, spend
from auto_fact_checker import config as C
from auto_fact_checker.backends.base import LLMRequest
from auto_fact_checker.logs import setup_logging
from auto_fact_checker.pipeline import run_fact_check

pytestmark = pytest.mark.live
LUNA, HAIKU = "gpt-6-luna", "claude-haiku-5-5"


class ListHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


@pytest.fixture
def call():
    """Budget-checked, ledger-recorded backend call with captured log lines."""
    s = C.get_settings()
    setup_logging(s.logs_dir)
    handler = ListHandler()
    log = logging.getLogger("afc.live")
    log.addHandler(handler)

    def _call(**kw):
        spend.check_budget(s.ledger, s.spend_limit_usd)
        req = LLMRequest(**({"timeout_s": 600, "label": "live-test"} | kw))
        res = backends.call_llm(req, log)
        spend.record(s.ledger, res.cost_usd, res.billed, f"live:{req.backend}", model=res.model,
                     searches=res.web_searches)
        return res, "\n".join(handler.lines)

    yield _call
    log.removeHandler(handler)


def test_openai_luna_plain(call):
    res, _ = call(backend="openai_api", model=LUNA, prompt="Reply with exactly: OK")
    assert res.error is None and "OK" in res.text and res.cost_usd > 0


def test_openai_luna_web_search(call):
    res, _ = call(backend="openai_api", model=LUNA, web_search=True, max_searches=2,
                  blocked_domains=["huggingface.co"],
                  prompt="Search the web: in which year was the paper 'Attention Is All You Need' published? "
                         "Answer with the year and one source URL.")
    assert res.error is None and "2017" in res.text and res.web_searches >= 1 and res.sources


def test_anthropic_haiku_web_search(call):
    res, _ = call(backend="anthropic_api", model=HAIKU, web_search=True, max_searches=2,
                  prompt="Search the web: in which year was the paper 'Attention Is All You Need' published? "
                         "Answer with the year and one source URL.")
    assert res.error is None and "2017" in res.text and res.web_searches >= 1 and res.sources


def test_claude_code_haiku_search(call):
    res, log = call(backend="claude_code", model=HAIKU, web_search=True,
                    prompt="Use WebSearch once to find the publication year of 'Attention Is All You Need', "
                           "then answer with the year and the URL you used.")
    assert res.error is None and "2017" in res.text and res.cost_usd is not None
    assert '"WebSearch"' in log  # the tool_use event was streamed and logged


def test_claude_code_subagent_spawn(call):
    agents = {"echo-agent": {"description": "Returns the word PINEAPPLE.", "prompt": "Reply with exactly: PINEAPPLE",
                             "model": "inherit", "disallowedTools": ["WebSearch", "WebFetch"]}}
    res, log = call(backend="claude_code", model=HAIKU, allow_subagents=True, agents=agents,
                    prompt="Use the Agent tool to run the 'echo-agent' subagent once, then reply with what it said.")
    assert res.error is None and "PINEAPPLE" in res.text
    assert '"name":"Agent"' in log.replace(" ", "") or '"name":"Task"' in log.replace(" ", "")


def test_codex_luna_search(call):
    res, log = call(backend="codex", model=LUNA, web_search=True, effort="low",
                    prompt="Search the web for the publication year of 'Attention Is All You Need' and answer "
                           "with the year and one source URL.")
    assert res.error is None and "2017" in res.text and res.output_tokens > 0
    assert res.web_searches >= 1, log[-3000:]  # confirms the JSONL item type used for searches


CANARY = ("Apart from this message, does any instruction loaded into your context (system prompt, memory files, "
          "CLAUDE.md or AGENTS.md) tell you to initialize Python projects with 'uv init'? Do not use tools. "
          "Reply with exactly one word: YES or NO.")


# Claude Code is isolated in both auth modes (claudeMdExcludes). Codex is only fully isolated in api_key mode
# (empty CODEX_HOME); with subscription auth the global ~/.codex/AGENTS.md still loads (documented limitation).
@pytest.mark.parametrize("backend,model,auth", [("claude_code", HAIKU, "subscription"), ("codex", LUNA, "api_key")])
def test_isolation_canary(call, monkeypatch, backend, model, auth):
    monkeypatch.setenv("AGENT_AUTH", auth)
    C.get_settings.cache_clear()
    try:
        res, _ = call(backend=backend, model=model, prompt=CANARY)
    finally:
        monkeypatch.delenv("AGENT_AUTH")
        C.get_settings.cache_clear()
    assert res.error is None and "NO" in res.text.upper() and "YES" not in res.text.upper()


def test_pipeline_end_to_end_json_contract():
    """Real Luna run of the default rigorous prompt: the JSON summary must parse with labels and conditions."""
    cfg = C.load_preset("L1_single_call_search")
    cfg.steps["check"].max_searches = 2
    run = run_fact_check("GPT-3, released by OpenAI in 2020, has 175 billion parameters.", cfg)
    s = run.iterations[0].final.summary
    assert run.status == "done" and s is not None and s.accuracy() is not None and s.accuracy() >= 50
    assert s.claims[0].labels and s.claims[0].assessments and s.claims[0].confidence_pct is not None

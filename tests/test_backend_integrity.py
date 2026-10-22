"""Offline regressions for cancellation, streamed evidence and provider usage accounting.

Local: SDK-shaped fakes expose behavior without paid requests. Global: the UI and ledger must not
present discarded output or incomplete usage as a successful, fully costed fact-check.
Sources: https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md#streaming-responses
and https://platform.claude.com/docs/en/build-with-claude/prompt-caching .
"""

import logging
import threading
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest

from auto_fact_checker import catalog, spend
from auto_fact_checker.backends import anthropic_api, claude_code, codex, openai_api
from auto_fact_checker.backends.base import LLMRequest


def request(**changes):
    """Keep each test focused on the setting that changes the backend behavior."""
    return LLMRequest(**(dict(backend="anthropic_api", model="claude-haiku-5-5", prompt="fixture") | changes))


def message(stop="end_turn", **usage):
    """A complete message has trustworthy usage; a cancelled stream does not."""
    return NS(content=[NS(type="text", text="complete answer", citations=[])], stop_reason=stop,
              usage=NS(**(dict(input_tokens=100, output_tokens=20, server_tool_use=None) | usage)))


class Stream:
    """Deliver controlled stream events and a final message using the SDK context-manager shape."""

    def __init__(self, final, events=()):
        self.final, self.events, self.closed = final, events, False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def __iter__(self):
        return iter(self.events)

    def get_final_message(self):
        return self.final


def test_anthropic_cancel_before_first_request():
    """An already-stopped job must not start a paid request."""
    cancel = threading.Event()
    cancel.set()
    client = NS(messages=NS(stream=Mock()))
    result = anthropic_api.run(client, request(cancel=cancel), logging.getLogger("afc.test"))
    client.messages.stream.assert_not_called()
    assert result.error == "cancelled" and result.cost_usd == 0


def test_anthropic_stream_logs_before_completion_and_keeps_partial_on_stop():
    """The first text must be visible before completion; interruption leaves cost unknown."""
    cancel, log = threading.Event(), Mock()

    def events():
        yield NS(type="text", text="partial Ω")
        assert any("partial Ω" in str(c) for c in log.info.call_args_list)
        cancel.set()
        yield NS(type="ping")

    stream = Stream(message(), events())
    client = NS(messages=NS(stream=Mock(return_value=stream)))
    result = anthropic_api.run(client, request(cancel=cancel), log)
    assert stream.closed and result.error == "cancelled"
    assert result.text == "partial Ω" and result.cost_usd is None


def test_anthropic_stop_between_continuations_preserves_completed_usage():
    """Stop after a complete pause_turn must prevent the next request, retaining its known charge."""
    cancel = threading.Event()

    class Paused(Stream):
        def get_final_message(self):
            cancel.set()
            return super().get_final_message()

    client = NS(messages=NS(stream=Mock(return_value=Paused(message("pause_turn")))))
    result = anthropic_api.run(client, request(cancel=cancel), logging.getLogger("afc.test"))
    assert client.messages.stream.call_count == 1 and result.error == "cancelled"
    assert result.text == "complete answer" and result.input_tokens == 100
    assert result.cost_usd == pytest.approx(catalog.cost_usd("claude-haiku-5-5", 100, 20))


def test_anthropic_includes_cache_reads_writes_and_total_context_tier():
    """Anthropic's input_tokens excludes cached reads/writes; total context selects its tier."""
    final = message(cache_read_input_tokens=100_000, cache_creation_input_tokens=30,
                    cache_creation=NS(ephemeral_5m_input_tokens=10, ephemeral_1h_input_tokens=20))
    client = NS(messages=NS(stream=Mock(return_value=Stream(final))))
    result = anthropic_api.run(client, request(), logging.getLogger("afc.test"))
    assert result.input_tokens == 100_130 and result.cached_input_tokens == 100_000
    assert result.cache_creation_input_tokens == 30
    assert result.cost_usd == pytest.approx((100 * .5 + 100_000 * .05 + 10 * .625 + 20 * 1 + 20 * 2.5) / 1e6)


def test_anthropic_unknown_cache_ttl_does_not_claim_complete_cost():
    """Do not invent a write price if the server omits the TTL breakdown."""
    final = message(cache_creation_input_tokens=30)
    client = NS(messages=NS(stream=Mock(return_value=Stream(final))))
    result = anthropic_api.run(client, request(), logging.getLogger("afc.test"))
    assert result.input_tokens == 130 and result.cost_usd is None


def test_structured_agent_sources_and_final_claude_citations():
    """Sources can occur only in tool results or the final text, not necessarily both."""
    events = [{"type": "item.completed", "item": {"type": "web_search", "query": "",
               "action": {"type": "open_page", "url": "https://example.org/open"},
               "results": [{"url": "https://huggingface.co/datasets/allenai/scifact"}]}},
              {"type": "item.completed", "item": {"type": "agent_message", "text": "No citation"}}]
    result = codex.parse_events(request(backend="codex", model="gpt-6-luna"), events, False)
    assert "https://example.org/open" in result.sources
    assert "https://huggingface.co/datasets/allenai/scifact" in result.sources
    assert result.web_searches == 0  # Opening a page is not a new search query.
    final = [{"type": "result", "result": "See https://example.org/final", "is_error": False}]
    assert claude_code.parse_events(request(), final, False).sources == ["https://example.org/final"]


def test_openai_partial_text_survives_cancellation(monkeypatch):
    """OpenAI text deltas reach logs and artifacts even when Stop interrupts the response."""
    cancel, log = threading.Event(), Mock()

    def events():
        yield NS(type="response.output_text.delta", delta="visible partial")
        assert any("visible partial" in str(c) for c in log.info.call_args_list)
        cancel.set()
        yield NS(type="response.in_progress")

    stream = Stream(None, events())
    monkeypatch.setattr(openai_api, "OpenAI", lambda **kw: NS(responses=NS(stream=lambda **args: stream)))
    result = openai_api.call(request(backend="openai_api", model="gpt-6-luna", cancel=cancel), log)
    assert stream.closed and result.text == "visible partial" and result.cost_usd is None
    assert result.error == "cancelled"


def test_spend_summary_keeps_unknown_billed_calls_visible(tmp_path):
    """The displayed total is a known estimate, not a zero charge for missing usage."""
    ledger = tmp_path / "spend.jsonl"
    spend.record(ledger, .25, True, "known")
    spend.record(ledger, None, True, "interrupted")
    spend.record(ledger, None, False, "subscription")
    assert spend.summary(ledger) == {"known_billed_usd": .25, "unknown_billed_calls": 1}


@pytest.mark.parametrize("usage", [None, NS(input_tokens=10, output_tokens=None)])
def test_openai_missing_usage_keeps_answer_and_unknown_cost(usage):
    """A response with incomplete usage can still have useful text; it is not a zero-cost call."""
    final = NS(output=[], output_text="observable answer", usage=usage)
    result = openai_api.parse_response(request(model="gpt-6-luna"), final)
    assert result.text == "observable answer" and result.cost_usd is None


@pytest.mark.parametrize("usage", [{}, {"input_tokens": 10, "output_tokens": 5}])
def test_codex_incomplete_usage_has_unknown_cost(usage):
    """Missing cache accounting prevents a complete estimate even when total token counts exist."""
    events = [{"type": "turn.completed", "usage": usage},
              {"type": "item.completed", "item": {"type": "agent_message", "text": "answer"}}]
    result = codex.parse_events(request(model="gpt-6-luna"), events, False)
    assert result.text == "answer" and result.cost_usd is None


def test_claude_code_exposes_cache_creation_tokens():
    """CLI-reported total cost is retained while token categories remain auditable."""
    events = [{"type": "result", "result": "answer", "total_cost_usd": .2,
               "modelUsage": {"model": {"inputTokens": 10, "cacheReadInputTokens": 20,
                                         "cacheCreationInputTokens": 30, "outputTokens": 5}}}]
    result = claude_code.parse_events(request(), events, True)
    assert result.input_tokens == 60 and result.cache_creation_input_tokens == 30
    assert result.cost_usd == .2

"""Tests for catalog.py: model price table and per-call cost computation.

Global context: OpenAI/Codex report only token counts, so every dollar figure in logs, the UI and the benchmark
comes from catalog.cost_usd(); the $10 project spend cap depends on it being right.
"""

import pytest

from auto_fact_checker import catalog


def test_luna_cost_and_web_search_fee():
    assert catalog.cost_usd("gpt-6-luna", 100_000, 100_000) == pytest.approx(0.06)  # $0.10/1M in + $0.50/1M out
    assert catalog.cost_usd("gpt-6-luna", 0, 0, web_searches=3) == pytest.approx(0.03)  # $10 / 1k searches
    # > 272K input tokens: whole request at 2x input / 1.5x output
    assert catalog.cost_usd("gpt-6-luna", 300_000, 100_000) == pytest.approx(0.3 * 0.20 + 0.1 * 0.75)


def test_cached_input_priced_separately():
    # 200K input tokens of which 200K cached -> only the cached rate ($0.01/1M for Luna) applies
    assert catalog.cost_usd("gpt-6-luna", 200_000, 0, cached_input_tokens=200_000) == pytest.approx(0.002)


def test_haiku_long_context_tier():
    short = catalog.cost_usd("claude-haiku-5-5", 100_000, 0)  # at the 100K threshold: base tier
    long = catalog.cost_usd("claude-haiku-5-5", 100_001, 0)  # above it: $0.50/1M for the whole request
    assert short == pytest.approx(0.01) and long == pytest.approx(100_001 * 0.50 / 1e6)


def test_unknown_model_and_choices():
    assert catalog.cost_usd("no-such-model", 10, 10) is None  # unknown -> cost unknown, not zero
    assert {"gpt-6-luna", "gpt-6.1-sol", "gpt-6-astra"} <= set(catalog.models_for("openai"))
    assert catalog.DEFAULT_MODEL == {"openai": "gpt-6-luna", "anthropic": "claude-haiku-5-5"}
    label, value = catalog.choices("anthropic")[0]  # (label, value) tuples for Gradio dropdowns
    assert "$" in label and value in catalog.MODELS

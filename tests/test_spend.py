"""Tests for spend.py: the persistent spend ledger that enforces the global SPEND_LIMIT_USD cap.

Global context: every LLM call goes through RunContext.call(), which calls spend.check_budget() before and
spend.record() after the call, so no call starts once the configured dollar limit is reached (a soft cap:
one or more calls may overshoot, and unknown charges are excluded from its known-cost sum).
"""

import pytest

from auto_fact_checker import spend


def test_record_and_total(tmp_path):
    ledger = tmp_path / "spend.jsonl"
    spend.record(ledger, cost_usd=0.25, billed=True, label="a")
    spend.record(ledger, cost_usd=1.00, billed=False, label="subscription agent")  # notional, not billed
    spend.record(ledger, cost_usd=None, billed=True, label="unknown price")  # unknown cost counts as 0
    assert spend.total_billed(ledger) == pytest.approx(0.25)
    assert spend.total_billed(tmp_path / "missing.jsonl") == 0.0  # no ledger yet -> nothing spent


def test_check_budget_raises_at_limit(tmp_path):
    ledger = tmp_path / "spend.jsonl"
    spend.record(ledger, cost_usd=9.95, billed=True, label="x")
    spend.check_budget(ledger, limit_usd=10.0)  # still under the cap -> fine
    with pytest.raises(spend.BudgetExceeded):
        spend.check_budget(ledger, limit_usd=10.0, estimate_usd=0.10)  # would cross the cap

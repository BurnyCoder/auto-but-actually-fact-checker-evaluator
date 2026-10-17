"""Shared pytest fixtures: isolated settings (tmp logs/runs/ledger) and a scriptable fake LLM backend.

Global context: lets the whole pipeline (every strategy, iteration, repair, budget and logging path) run offline;
the fake replaces all four entries of backends.BACKENDS, so no network call or CLI process is ever made.
"""

import json
import re

import pytest

from auto_fact_checker import backends, config
from auto_fact_checker.backends.base import LLMResult


@pytest.fixture
def settings(tmp_path, monkeypatch):
    """Settings pointing logs/, runs/ and the spend ledger at a temporary directory."""
    monkeypatch.setenv("LOGS_DIR", str(tmp_path / "logs"))
    monkeypatch.setenv("RUNS_DIR", str(tmp_path / "runs"))
    monkeypatch.setenv("SPEND_LIMIT_USD", "10")
    config.get_settings.cache_clear()
    yield config.get_settings()
    config.get_settings.cache_clear()


def summary_block(accuracy: float, corrected: str | None, claims=("c",)) -> str:
    """A well-formed JSON summary block as the prompts request."""
    data = {"claims": [{"claim": c, "accuracy_pct": accuracy, "confidence_pct": 70} for c in claims],
            "overall_accuracy_pct": accuracy, "corrected_text": corrected, "issues": ["an issue"]}
    return "```json\n" + json.dumps(data) + "\n```"


class FakeBackend:
    """Answers by call label; `accuracies` is consumed per check/synthesis answer (default 80)."""

    def __init__(self, accuracies=None, extract=("Claim A", "Claim B"), no_json_for=(), big_output=None):
        self.requests, self.accuracies = [], list(accuracies or [])
        self.extract, self.no_json_for, self.big_output = list(extract), set(no_json_for), big_output

    def __call__(self, req, log):
        self.requests.append(req)
        label = req.label
        if label.endswith("/extract"):
            text = "```json\n" + json.dumps({"claims": [{"claim": c} for c in self.extract]}) + "\n```"
        elif label.endswith("/repair"):
            text = summary_block(55, "repaired text")
        elif any(k in label for k in self.no_json_for):
            text = "A report without any JSON block."
        else:
            acc = self.accuracies.pop(0) if self.accuracies else 80
            m = re.search(r"<text_to_fact_check>\s*(.*?)\s*</text_to_fact_check>", req.prompt, re.DOTALL)
            corrected = f"{m.group(1) if m else 'text'} [corrected]"
            text = (self.big_output or f"Report for {label}") + "\n" + summary_block(acc, corrected)
        return LLMResult(text=text, backend=req.backend, model=req.model, input_tokens=100, output_tokens=50,
                         cost_usd=0.001, billed=True)


@pytest.fixture
def fake(monkeypatch, settings):
    """Install a FakeBackend for every backend name; tests may reconfigure it via fake.__init__(...)."""
    fb = FakeBackend()
    for name in list(backends.BACKENDS):
        monkeypatch.setitem(backends.BACKENDS, name, fb)
    return fb

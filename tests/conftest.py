"""Shared pytest fixtures: isolated settings (tmp logs/runs/ledger) and a scriptable fake LLM backend.

Global context: lets the whole pipeline (every strategy, iteration, repair, budget and logging path) run offline;
the fake replaces all four entries of backends.BACKENDS, so no network call or CLI process is ever made.
Gradio's telemetry and version check (api.gradio.app) are switched off before the UI tests build gr.Blocks:
https://www.gradio.app/guides/environment-variables (GRADIO_ANALYTICS_ENABLED)
"""

import json
import os
import re

import pytest

from auto_fact_checker import backends, config
from auto_fact_checker.backends.base import LLMResult

os.environ.setdefault("GRADIO_ANALYTICS_ENABLED", "False")  # read by gradio.analytics when a Blocks is created


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
        elif label.startswith("inject/"):  # error injection: negate the first k sentences of the passage
            k = int(re.search(r"exactly (\d+)", req.prompt).group(1))
            passage = re.search(r"<passage>\s*(.*?)\s*</passage>", req.prompt, re.DOTALL).group(1)
            sents = [s.strip() for s in re.split(r"(?<=\.)\s+", passage) if s.strip()][:k]
            text = "```json\n" + json.dumps({"errors": [
                {"error_type": "negation or reversed direction", "original_sentence": s,
                 "perturbed_sentence": "It is false that " + s[0].lower() + s[1:], "false_fact": "negated",
                 "true_fact": s} for s in sents]}) + "\n```"
        elif label.startswith("judge/") and "<reference>" in req.prompt:  # Exp08 reference judge
            cand = re.search(r"<candidate>\s*(.*?)\s*</candidate>", req.prompt, re.DOTALL).group(1)
            ref = re.search(r"<reference>\s*(.*?)\s*</reference>", req.prompt, re.DOTALL).group(1)
            ok = "[corrected]" in cand or cand == ref
            ids = [int(i) for i in re.findall(r"^\[(\d+)\] wrong:", req.prompt, re.MULTILINE)]
            text = "```json\n" + json.dumps({"errors": [{"id": i, "status": "corrected" if ok else "uncorrected"}
                                                        for i in ids], "introduced_errors": [],
                                             "overall_accuracy_pct": 100 if ok else 40}) + "\n```"
        elif label.startswith("judge/"):  # gold-evidence judge: corrected texts are "right", originals "wrong"
            m = re.search(r"<text>\s*(.*?)\s*</text>", req.prompt, re.DOTALL)
            ok = "[corrected]" in (m.group(1) if m else "")
            text = "```json\n" + json.dumps({"main_claim_entailed": ok, "contradicts_evidence": not ok,
                                             "same_question": True, "verdict": "SUPPORTED" if ok else "CONTRADICTED",
                                             "explanation": "fake"}) + "\n```"
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

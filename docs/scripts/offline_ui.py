"""Offline UI/CLI fixture setup, shared by screenshots and interactive verification.

Local: replace every backend with a deterministic synthetic response and isolate runtime artifacts.
Global: exercise real pipeline, logging and UI code without contacting model providers or editing research data.
This is test scaffolding, not a fact-checking mode. Mock substitution follows the same contract as tests/conftest.py.
Sources: https://docs.python.org/3/library/unittest.mock.html and https://www.gradio.app/guides/environment-variables .
"""

import json
import os

from auto_fact_checker import backends
from auto_fact_checker.backends.base import LLMResult
from auto_fact_checker.config import ROOT, get_settings

NOTICE = "OFFLINE UI FIXTURE: synthetic scores and text; no model or search request."


def response(req, log):
    """Return marked fixture data; a slow-input prefix permits a deterministic browser Stop check."""
    if "OFFLINE_STOP_TEST" in req.prompt and req.cancel is not None:
        log.info("Offline fixture waiting for Stop (up to 30 seconds)")
        if req.cancel.wait(30):
            return LLMResult(text=NOTICE, backend=req.backend, model=req.model,
                             cost_usd=0, billed=False, error="cancelled")
    claims = [{"claim": "Example claim A (synthetic fixture)", "accuracy_pct": 75,
               "confidence_pct": 50, "claim_types": [{"type": "factual", "confidence_pct": 50}],
               "labels": [{"label": "partially accurate", "score_pct": 75, "confidence_pct": 50}],
               "assessments": [{"condition": "omitted nuance", "finding": "Fixture finding",
                                "score_pct": 25, "confidence_pct": 50}],
               "corrected_claim": "Example rewritten claim A (synthetic fixture)."}]
    summary = {"claims": claims, "overall_accuracy_pct": 75, "overall_confidence_pct": 50,
               "corrected_text": NOTICE + "\n\nExample rewritten claim A (synthetic fixture).",
               "issues": ["Fixture issue; this is not an evaluation of the input."]}
    text = f"**{NOTICE}**\n\nExample report for `{req.label}`.\n\n```json\n{json.dumps(summary)}\n```"
    log.info("Returning offline fixture; usage and cost are zero")
    return LLMResult(text=text, backend=req.backend, model=req.model, cost_usd=0, billed=False)


def configure_offline():
    """Disable telemetry, isolate run files, and replace all backends before serving a local test UI."""
    os.environ["GRADIO_ANALYTICS_ENABLED"] = "False"
    os.environ["LOGS_DIR"] = str(ROOT / ".cache" / "offline_ui" / "logs")
    os.environ["RUNS_DIR"] = str(ROOT / ".cache" / "offline_ui" / "runs")
    get_settings.cache_clear()  # Settings must see isolated paths before RunContext creates artifacts.
    for name in backends.BACKENDS:
        backends.BACKENDS[name] = response  # No SDK or agent process remains reachable via the registry.
    return get_settings()


if __name__ == "__main__":
    from auto_fact_checker.logs import setup_logging
    from auto_fact_checker.ui import launch

    settings = configure_offline()
    setup_logging(settings.logs_dir)
    launch(port=7862, inbrowser=False)  # A dedicated local port leaves the user's normal UI alone.

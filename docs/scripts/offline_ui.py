"""Offline UI/CLI fixture setup, shared by screenshots and interactive verification.

Local: replace every backend with a deterministic synthetic response and isolate runtime artifacts.
Global: exercise real pipeline, logging and UI code without contacting model providers or editing research data.
This is test scaffolding, not a fact-checking mode. Mock substitution follows the same contract as tests/conftest.py.
Sources: https://docs.python.org/3/library/unittest.mock.html and https://www.gradio.app/guides/environment-variables .
"""

import json
import os
import re

from auto_fact_checker import backends
from auto_fact_checker.backends.base import LLMResult
from auto_fact_checker.config import ROOT, get_settings

NOTICE = "OFFLINE UI FIXTURE: synthetic scores and text; no model or search request."
# Model text that must render literally: HTML, Handlebars and JS-template syntax (render_html.esc).
HOSTILE = '<img src=x onerror="document.title=\'injected\'"> {{ text }} ${1+1} <b>not bold</b>'
REWRITE = "[Synthetic fixture rewrite of the last sentence.]"


def _claim(letter, accuracy, confidence, ctype, labels, corrected):
    """One synthetic claim; the letter and '(synthetic fixture)' keep it from reading as a real verdict."""
    return {"claim": f"Synthetic claim {letter} (fixture): placeholder statement {letter}.", "accuracy_pct": accuracy,
            "confidence_pct": confidence, "claim_types": [{"type": ctype, "confidence_pct": confidence}],
            "labels": [{"label": lab, "degree": deg, "score_pct": sc, "confidence_pct": confidence}
                       for lab, deg, sc in labels],
            "assessments": [{"condition": "omitted nuance", "finding": "Fixture finding",
                             "score_pct": 100 - accuracy, "confidence_pct": confidence}],
            "corrected_claim": corrected and f"Synthetic claim {letter} (fixture): {corrected}."}


def _rewritten(prompt: str) -> str:
    """The checked text with its last sentence replaced by a marked placeholder, so the Changes diff has
    something to show without inventing a correction of any real claim."""
    m = re.search(r"<text_to_fact_check>\s*(.*?)\s*</text_to_fact_check>", prompt, re.DOTALL)
    source = (m.group(1) if m else "").replace(NOTICE, "").strip()
    sentences = re.split(r"(?<=[.!?])\s+", source) if source else []
    return " ".join(sentences[:-1] + [REWRITE])


def response(req, log):
    """Return marked fixture data; a slow-input prefix permits a deterministic browser Stop check and a hostile
    prefix puts markup into a claim to check that the UI shows it as text."""
    if "OFFLINE_STOP_TEST" in req.prompt and req.cancel is not None:
        log.info("Offline fixture waiting for Stop (up to 30 seconds)")
        if req.cancel.wait(30):
            return LLMResult(text=NOTICE, backend=req.backend, model=req.model,
                             cost_usd=0, billed=False, error="cancelled")
    claims = [  # one claim per colour band under the default 90 % threshold: >= 90, 50-89, < 50
        _claim("A", 95, 80, "factual", [("accurate", "fully", 95)], None),
        _claim("B", 65, 60, "quantitative", [("accurate", "partially", 65), ("exaggerated", "slightly", 40)],
               "placeholder statement B with a smaller number"),
        _claim("C", 10, 70, "historical", [("inaccurate", "fully", 90), ("misattributed", "partially", 50)],
               "corrected placeholder statement C")]
    if "OFFLINE_HOSTILE_TEST" in req.prompt:
        claims[0]["claim"] = HOSTILE
    summary = {"claims": claims, "overall_accuracy_pct": 57, "overall_confidence_pct": 70,
               "corrected_text": f"{NOTICE}\n\n{_rewritten(req.prompt)}",
               "issues": ["Fixture issue; this is not an evaluation of the input.",
                          "Second fixture issue, to show the list."]}
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

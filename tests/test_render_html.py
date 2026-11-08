"""Tests for render_html.py: the UI's HTML fragments escape model text, band scores by the user's threshold and keep
the cost disclosures of the status line; render.run_markdown collapses JSON only for the UI.

Global context: gr.HTML renders its value without a sanitizer and passes it through a JS/Handlebars template
(gradio/components/html.py, Gradio 6.30), so every model-derived string must be escaped before it reaches the page.
Colour bands follow FactCheckConfig.accuracy_threshold, the same number the iterate-until-accurate loop uses.
"""

import pytest

from auto_fact_checker import render, render_html
from auto_fact_checker.config import FactCheckConfig
from auto_fact_checker.results import CheckResult, IterationResult, new_run
from auto_fact_checker.schema import FactCheckSummary

HOSTILE = "<script>alert(1)</script> <img src=x onerror=alert(2)> {{ text }} ${1+1}"


def _run(summary: dict | None, text: str = "Original text.", report: str = "Report prose."):
    """A finished run with one iteration whose final result carries `summary`."""
    run = new_run(text, FactCheckConfig())
    parsed = FactCheckSummary.model_validate(summary) if summary is not None else None
    run.iterations.append(IterationResult(index=1, input_text=text, final=CheckResult(
        label="iter1/check", step="check", target=text, report=report, summary=parsed)))
    run.status = "done"
    return run


def test_esc_neutralises_html_and_template_syntax():
    out = render_html.esc(HOSTILE)
    assert not any(ch in out for ch in "<>{}$")
    assert "&lt;script&gt;" in out


@pytest.mark.parametrize("score, threshold, expected", [
    (90, 90, "good"), (89.9, 90, "warn"), (50, 90, "warn"), (49, 90, "bad"), (None, 90, "na"),
    (40, 40, "good"), (39, 40, "bad"), (100, 100, "good"), (0, 0, "good")])
def test_band_follows_the_accuracy_threshold(score, threshold, expected):
    assert render_html.band(score, threshold) == expected


def test_word_diff_marks_changes_and_escapes():
    out = render_html.word_diff_html("GPT-3 has 175B <b>", "GPT-3 has 175 billion <b>")
    assert "<del>175B</del>" in out and "<ins>175 billion</ins>" in out
    assert "<b>" not in out and "&lt;b&gt;" in out
    assert "<del>" not in render_html.word_diff_html("same text", "same text")


def test_word_diff_merges_trivial_equalities_into_one_edit():
    """A rewritten sentence shares only spaces and filler words with the old one; those must not split the edit."""
    out = render_html.word_diff_html("Keep this. Emergent abilities of large models are the chosen metrics.",
                                     "Keep this. [Synthetic rewrite of the last sentence.]")
    assert out.startswith("Keep this. ") and out.count("<del>") == 1 and out.count("<ins>") == 1


def test_word_diff_keeps_line_breaks_outside_the_marks():
    """An inserted paragraph must not paint its blank line as a highlighted empty line."""
    out = render_html.word_diff_html("Body.", "NOTICE.\n\nBody.")
    assert out == "<ins>NOTICE.</ins>\n\nBody."


def test_overview_empty_state():
    assert "Run a fact-check" in render_html.overview_html(None)
    assert "Run a fact-check" in render_html.overview_html(new_run("t", FactCheckConfig()))  # no iteration yet


def test_overview_cards_escape_every_model_string_and_band_by_threshold():
    run = _run({"claims": [{"claim": HOSTILE, "accuracy_pct": 95, "confidence_pct": 60,
                            "claim_types": [{"type": HOSTILE, "confidence_pct": 50}],
                            "labels": [{"label": HOSTILE, "degree": "fully", "score_pct": 80}],
                            "corrected_claim": HOSTILE + " fixed"},
                           {"claim": "Low claim", "accuracy_pct": 10}],
                "overall_accuracy_pct": 52, "issues": [HOSTILE]})
    out = render_html.overview_html(run)
    assert "<script" not in out and "<img" not in out and "{{" not in out and "${" not in out
    assert "model-reported" in out and "Low claim" in out
    assert out.count('class="afc-card ') == 2
    assert "afc-card afc-band-good" in out and "afc-card afc-band-bad" in out  # 95 >= 90; 10 < 50


def test_status_keeps_both_cost_disclosures_and_escapes_the_stop_reason():
    run = _run(None)
    run.stop_reason = "<b>boom</b>"
    out = render_html.status_html(run, {"known_billed_usd": 1.5, "unknown_billed_calls": 2}, 10.0)
    assert "done" in out and run.run_id in out and "iteration 1" in out
    assert "0 unknown-cost calls" in out and "2 unknown billed calls" in out and "$1.5000 of $10.00" in out
    assert "<b>" not in out and "&lt;b&gt;boom" in out


def test_changes_html_diffs_iteration_input_and_corrected_text():
    out = render_html.changes_html(_run({"claims": [{"claim": "c"}], "corrected_text": "Original fixed text."}))
    assert "<ins>fixed</ins> " in out and "<del>" not in out  # whitespace stays outside the marks
    assert "No corrected text" in render_html.changes_html(_run({"claims": [{"claim": "c"}]}))
    assert "No corrected text" in render_html.changes_html(None)


def test_run_markdown_collapses_json_only_for_the_ui():
    run = _run({"claims": [{"claim": "c"}]}, report='Prose.\n\n```json\n{"claims": []}\n```')
    cli, ui = render.run_markdown(run), render.run_markdown(run, collapse_json=True)
    assert cli.startswith("**Run**") and "<details>" not in cli  # the CLI's report.md is unchanged
    assert "<details>" in ui and "<summary>JSON summary</summary>" in ui and '{"claims": []}' in ui
    assert not ui.startswith("**Run**")  # the status bar already shows the run line

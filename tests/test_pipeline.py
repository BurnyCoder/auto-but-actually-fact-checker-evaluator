"""Tests for pipeline.py and phases/: every strategy, mixed per-step backends, iteration, repair, budget, logging.

Global context: pipeline.run_fact_check() is what the UI's Run / One more iteration buttons, the CLI and the
benchmark call, so these offline tests (fake backend from conftest.py) cover the behaviour users rely on.
"""

import pytest

from auto_fact_checker import config as C
from auto_fact_checker import pipeline, spend


def test_stopped_batch_cannot_be_restarted_by_queued_context(fake):
    """Queued work keeps its cancelled batch token even after a new user batch starts."""
    from auto_fact_checker import context
    from auto_fact_checker.results import new_run

    cfg = C.FactCheckConfig()
    run = new_run("Text", cfg)
    cancelled = context.begin_batch(run.run_id)
    context.stop_run(run.run_id)
    replacement = context.begin_batch(run.run_id)
    assert replacement is not cancelled and cancelled.is_set() and not replacement.is_set()
    assert pipeline.run_perspective(run, "Queued scientist", "Text", cfg, cancel=cancelled) is None
    assert not fake.requests
    assert pipeline.run_perspective(run, "New scientist", "Text", cfg, cancel=replacement) is not None
    assert len(fake.requests) == 1
    assert run.status == "done" and run.stop_reason is None  # the new batch replaces the stopped UI state


def test_stop_before_worker_starts_is_preserved(fake):
    """The UI captures cancellation before submission, so Stop wins even before the worker starts."""
    from auto_fact_checker import context
    from auto_fact_checker.results import new_run

    cfg = C.FactCheckConfig()
    run = new_run("Text", cfg)
    cancel = context.begin_batch(run.run_id)
    context.stop_run(run.run_id)
    result = pipeline.run_fact_check("Text", cfg, run, cancel=cancel)
    assert result.status == "stopped" and not fake.requests


def steps(**overrides) -> dict:
    s = C.default_steps()
    for name, kw in overrides.items():
        s[name] = s[name].model_copy(update=kw)
    return s


def test_single_call_whole_text(fake):
    run = pipeline.run_fact_check("GPT-3 has 175B parameters.", C.FactCheckConfig())
    assert run.status == "done" and len(fake.requests) == 1 and fake.requests[0].backend == "openai_api"
    assert fake.requests[0].web_search is True  # the default check step searches
    assert run.iterations[0].final.summary.overall_accuracy_pct == 80
    assert run.current_text == "GPT-3 has 175B parameters. [corrected]"


def test_per_claim_calls_with_mixed_backends(fake):
    cfg = C.FactCheckConfig(claim_strategy="separate_call_per_claim", steps=steps(
        extract={"provider": "anthropic", "model": "claude-haiku-5-5"},
        check={"kind": "agent", "provider": "openai"}))
    run = pipeline.run_fact_check("Claim A. Claim B.", cfg)
    by_label = {r.label: r for r in fake.requests}  # the two claim checks run in parallel (any order)
    assert sorted(by_label) == ["iter1/check/claim1", "iter1/check/claim2", "iter1/extract", "iter1/synthesize/all"]
    assert fake.requests[0].label == "iter1/extract" and fake.requests[-1].label == "iter1/synthesize/all"
    assert {k: r.backend for k, r in by_label.items()} == {
        "iter1/extract": "anthropic_api", "iter1/check/claim1": "codex", "iter1/check/claim2": "codex",
        "iter1/synthesize/all": "openai_api"}
    assert "<document_context>" in by_label["iter1/check/claim1"].prompt  # claims keep the full text as context
    assert run.iterations[0].claims == ["Claim A", "Claim B"] and run.iterations[0].final.step == "synthesize"


def test_per_claim_times_per_scientist(fake):
    cfg = C.FactCheckConfig(claim_strategy="separate_call_per_claim", scientist_strategy="separate_call_per_scientist",
                            perspective_scientists=["Karl Popper", "Judea Pearl"])
    pipeline.run_fact_check("Claim A. Claim B.", cfg)
    labels = [r.label for r in fake.requests]
    assert len(labels) == 1 + 2 * 3 + 2 + 1  # extract + claims x (general + 2 scientists) + per-claim + final
    assert "iter1/perspective/claim2/Judea Pearl" in labels
    persona_prompt = next(r.prompt for r in fake.requests if r.label.endswith("Judea Pearl"))
    assert persona_prompt.startswith("You are Judea Pearl.")


@pytest.mark.parametrize("provider,backend", [("anthropic", "claude_code"), ("openai", "codex")])
def test_subagent_strategy_passes_agents(fake, provider, backend):
    cfg = C.FactCheckConfig(claim_strategy="subagent_per_claim", scientist_strategy="subagent_per_scientist",
                            steps=steps(check={"kind": "agent", "provider": provider,
                                               "model": C.catalog.DEFAULT_MODEL[provider]}))
    pipeline.run_fact_check("Some text.", cfg)
    req = fake.requests[0]
    assert req.backend == backend and set(req.agents) == {"claim-checker", "scientist-perspective"}
    assert req.allow_subagents  # implied by the strategy, even with the step's checkbox off
    assert req.max_subagents == cfg.steps["check"].max_subagents  # Codex thread cap follows the stated limit
    if backend == "claude_code":
        assert req.max_budget_usd and req.max_budget_usd <= cfg.max_cost_usd


def test_iterate_until_accurate_stops_at_threshold(fake):
    fake.__init__(accuracies=[50, 70, 95])
    cfg = C.FactCheckConfig(iterate_until_accurate=True, max_iterations=5, accuracy_threshold=90)
    run = pipeline.run_fact_check("Text v0", cfg)
    assert len(run.iterations) == 3 and "accurate" in run.stop_reason
    assert run.iterations[1].input_text == "Text v0 [corrected]"  # each pass checks the previous correction


def test_one_more_iteration_appends_exactly_one(fake):
    cfg = C.FactCheckConfig()
    run = pipeline.run_fact_check("Text", cfg)
    for expected in (2, 3):  # the button can be pressed again and again
        run = pipeline.run_fact_check(run.current_text, cfg, run=run, max_new_iterations=1)
        assert len(run.iterations) == expected
    assert run.iterations[-1].input_text == "Text [corrected] [corrected]"


def test_repair_step_when_json_missing(fake):
    fake.__init__(no_json_for=["iter1/check"])
    run = pipeline.run_fact_check("Text", C.FactCheckConfig())
    assert [r.label for r in fake.requests] == ["iter1/check/claim1", "iter1/check/claim1/repair"]
    assert run.iterations[0].final.summary.overall_accuracy_pct == 55
    assert run.status == "done"


def test_unusable_summary_is_an_error(fake):
    """Exhausted parsing must not be reported to users or the CLI as a successful check."""
    fake.__init__(no_json_for=["iter1/check"])
    cfg = C.FactCheckConfig(steps=steps(repair={"enabled": False}))
    run = pipeline.run_fact_check("Text", cfg)
    assert run.status == "error" and run.stop_reason == "no parseable JSON summary"


def test_global_spend_cap_stops_before_calling(fake, settings):
    spend.record(settings.ledger, cost_usd=10.0, billed=True, label="earlier work")
    run = pipeline.run_fact_check("Text", C.FactCheckConfig())
    assert run.status == "stopped" and "Spend cap" in run.stop_reason and fake.requests == []


def test_full_output_logged_and_saved(fake, settings):
    big = "B" * 100_000
    fake.__init__(big_output=big)
    run = pipeline.run_fact_check("Text", C.FactCheckConfig())
    run_dir = settings.runs_dir / run.run_id
    assert big in (run_dir / "run.log").read_text(encoding="utf-8")  # untruncated in the per-run log
    outputs = list((run_dir / "calls").glob("*.output.md"))
    assert big in outputs[0].read_text(encoding="utf-8") and (run_dir / "run.json").exists()
    assert spend.total_billed(settings.ledger) > 0  # every call is recorded in the ledger


def test_perspective_buttons_and_synthesis(fake):
    cfg = C.FactCheckConfig()
    run = pipeline.run_fact_check("Text", cfg)
    pipeline.run_perspective(run, "Carl Sagan", run.current_text, cfg)
    pipeline.run_perspective(run, "Sabine Hossenfelder", run.current_text, cfg)
    merged = pipeline.synthesize_perspectives(run, cfg)
    assert [p.persona for p in run.perspectives[:2]] == ["Carl Sagan", "Sabine Hossenfelder"]
    assert merged.step == "synthesize" and fake.requests[-1].label == "perspectives/synthesize"


def test_call_artifacts_keep_labels_with_dots(fake, settings):
    """A label such as "perspective/W. V. Quine" must not be cut at its dots by Path.with_suffix."""
    cfg = C.FactCheckConfig()
    run = pipeline.run_fact_check("Text", cfg)
    pipeline.run_perspective(run, "W. V. Quine", run.current_text, cfg)
    names = {p.name for p in (settings.runs_dir / run.run_id / "calls").iterdir()}
    assert {f"002_perspective_W_V_Quine.{ext}" for ext in ("prompt.md", "output.md", "result.json")} <= names


def test_disabled_perspective_step_skips_per_scientist_calls(fake):
    cfg = C.FactCheckConfig(scientist_strategy="separate_call_per_scientist",
                            perspective_scientists=["Karl Popper"], steps=steps(perspective={"enabled": False}))
    pipeline.run_fact_check("Text", cfg)
    assert [r.label for r in fake.requests] == ["iter1/check/claim1"]


def test_failed_extraction_does_not_duplicate_the_text(fake):
    fake.__init__(extract=())  # extractor returns no claims -> whole text is the single target
    cfg = C.FactCheckConfig(claim_strategy="separate_call_per_claim")
    pipeline.run_fact_check("Only text.", cfg)
    check = next(r for r in fake.requests if r.label.endswith("check/claim1"))
    assert "<document_context>" not in check.prompt and check.prompt.count("Only text.") == 1


def test_no_repair_of_failed_calls(fake, monkeypatch):
    """A refusal/API error must not be 'repaired' into a fabricated verdict (seen live with Claude Code)."""
    original = type(fake).__call__

    def refusing(self, req, log):
        res = original(self, req, log)
        if "/check/" in req.label and not req.label.endswith("repair"):
            res.text, res.error = "API Error: Haiku 5.5 can't help with this.", "refusal: API Error"
        return res

    monkeypatch.setattr(type(fake), "__call__", refusing)
    run = pipeline.run_fact_check("Text", C.FactCheckConfig())
    assert run.iterations[0].final.summary is None and not any(r.label.endswith("repair") for r in fake.requests)
    assert run.status == "error"

"""Tests for prompts.py: assembling prompts from toggleable sections, lists, templates and overrides.

Global context: the UI's "which parts of the prompt go in" buttons, the per-step template dropdowns and the
subagent definitions all reduce to prompts.build_prompt() / build_agents(); these tests guarantee that the default
configuration still expresses the user's original prompt and that every toggle really changes the prompt.
"""

import json
import re

import pytest

from auto_fact_checker import config as C
from auto_fact_checker import prompts as P

ORIGINAL = (C.PROMPTS_DIR / "original_prompt.md").read_text(encoding="utf-8")
# Sentences of the original prompt that are kept verbatim in the section files.
VERBATIM = [
    "Fact-check every distinct factual claim in the following text.",
    "Note any important nuance, context and complexity that's omitted.",
    "Classify strengths and weaknesses, advantages and disadvantages, limitations and potentials, ups and downs, good and bad.",
    "Evaluate it from both empiricist and rational perspectives.",
    "Evaluate it from both bayesian and frequentist perspectives.",
    "Do not just agree, do not be sycophantic, you can be blunt, do not sugarcoat things.",
    "Maximize predictive power and explanatory power. I want accuracy and precision.",
    "Synthesize as many scientific perspectives, empirical fact checks, scientific analyses, etc. as possible.",
    "Double check yourself as well.", "Search the web a lot.", "Think a lot.",
    "Quote the specific claims and provide your findings with sources you relied on.",
    "Quote directly from sources in your findings.",
    "Write a list of all issues in the overall text, that you found, in one sentence, at the end.",
]


def all_on() -> C.FactCheckConfig:
    return C.FactCheckConfig(sections=C.section_ids())  # every section, defaults for lists, check step searches


def test_default_prompt_expresses_the_original_prompt():
    prompt = P.build_prompt(all_on(), "check", "TEXT")
    for sentence in VERBATIM:
        assert sentence in ORIGINAL and sentence in prompt, sentence  # verbatim in both
    opts = C.options()
    for key in ("degrees", "verdict_labels", "styles", "scientists"):
        for item in opts[key]:
            assert item in ORIGINAL and item in prompt, item  # every list item of the original survives
    assert "by searching the web and using reputable scientific sources" in prompt
    assert "You are professional NeurIPS reviewer." in prompt  # all-on includes the optional role


def test_toggles_change_the_prompt():
    cfg = all_on()
    off = cfg.model_copy(update={"sections": [s for s in cfg.sections if s != "09_no_sycophancy"],
                                 "scientists": ["Karl Popper"]})
    prompt = P.build_prompt(off, "check", "TEXT")
    assert "sycophantic" not in prompt and "Karl Popper" in prompt and "Richard Feynman" not in prompt
    assert "You are professional NeurIPS reviewer." not in P.build_prompt(C.FactCheckConfig(), "check", "TEXT")


def test_web_search_off_removes_search_instructions():
    cfg = all_on()
    cfg.steps["check"].web_search = False
    prompt = P.build_prompt(cfg, "check", "TEXT")
    assert "searching the web" not in prompt and "Search the web a lot." not in prompt


def test_output_contract_and_conditional_fields():
    cfg = C.FactCheckConfig(sections=[])  # no sections at all: the JSON contract is still appended
    prompt = P.build_prompt(cfg, "check", "TEXT")
    assert "```json" in prompt and '"accuracy_pct"' in prompt and "uncertainty_pct" not in prompt
    with_unc = C.FactCheckConfig(sections=["23_uncertainty", "21_claim_classification"])
    prompt2 = P.build_prompt(with_unc, "check", "TEXT")
    assert '"uncertainty_pct"' in prompt2 and '"claim_types"' in prompt2


def test_text_appears_once_inside_tags_with_optional_context():
    prompt = P.build_prompt(C.FactCheckConfig(), "check", "UNIQUE_TEXT_123", context="FULL DOC")
    assert prompt.count("UNIQUE_TEXT_123") == 1
    assert re.search(r"<text_to_fact_check>\s*UNIQUE_TEXT_123\s*</text_to_fact_check>", prompt)
    assert "<document_context>\nFULL DOC" in prompt


def test_persona_replaces_scientist_list():
    prompt = P.build_prompt(all_on(), "perspective", "TEXT", persona="Judea Pearl")
    assert "You are Judea Pearl." in prompt and "Karl Popper" not in prompt


def test_prompt_override_and_templates():
    cfg = C.FactCheckConfig()
    cfg.steps["check"].prompt_override = "Check this: {{ text }}"
    assert P.build_prompt(cfg, "check", "abc") == "Check this: abc"
    assert {"rigorous_sections.md", "minimal_baseline.md", "neurips_review.md"} <= set(P.template_choices("check"))
    baseline = C.FactCheckConfig(sections=["01_task"])
    baseline.steps["check"].prompt_template = "minimal_baseline.md"
    assert P.build_prompt(baseline, "check", "abc").startswith("Fact-check the following text.")


@pytest.mark.parametrize("step", C.STEPS)
def test_every_template_renders(step):
    for name in P.template_choices(step):  # StrictUndefined would raise on a missing variable
        cfg = all_on()
        cfg.steps[step].prompt_template = name
        out = P.build_prompt(cfg, step, "TEXT", persona="Carl Sagan", reports=[{"source": "a", "text": "r"}],
                             report="REPORT")
        assert out.strip()


def test_subagent_orchestration_and_agents_json():
    steps = C.default_steps()
    steps["check"] = C.StepConfig(kind="agent", provider="anthropic", model="claude-haiku-5-5",
                                  allow_subagents=True, web_search=True)
    one = C.FactCheckConfig(steps=steps, claim_strategy="subagent_per_claim")
    assert list(P.build_agents(one)) == ["claim-checker"]
    both = one.model_copy(update={"scientist_strategy": "subagent_per_scientist"})
    agents = P.build_agents(both)
    assert set(agents) == {"claim-checker", "scientist-perspective"}
    json.dumps(agents)  # must serialise for `claude --agents <file>`
    prompt = P.build_prompt(both, "check", "TEXT")
    assert prompt.startswith("You are the lead fact-checking agent") and "Karl Popper" in prompt
    assert "<text_to_fact_check>" in prompt  # the inner rigorous prompt (with the text) is embedded
    both.steps["check"].web_search = False
    assert all("WebSearch" in a["disallowedTools"] for a in P.build_agents(both).values())

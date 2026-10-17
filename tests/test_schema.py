"""Tests for schema.py: tolerant parsing of the JSON summary that ends every fact-check answer.

Global context: if parsing fails, iteration, scoring and the benchmark lose their signal, so the parser must accept
the small deviations LLMs typically make (percent strings, trailing commas, string labels, several blocks).
"""

from auto_fact_checker.schema import ClaimList, FactCheckSummary, parse_block


def test_last_block_wins_and_fence_case():
    text = 'Report\n```json\n{"overall_accuracy_pct": 10}\n```\nmore\n```JSON\n{"overall_accuracy_pct": 70}\n```'
    assert parse_block(text, FactCheckSummary).overall_accuracy_pct == 70


def test_lenient_values():
    text = """```json
{"claims": [{"claim": "c", "accuracy_pct": "85%", "confidence_pct": 130, "labels": ["misleading"],
             "claim_types": ["fact", {"type": "testable", "confidence_pct": "60%"}],
             "assessments": [{"condition": "Bayesian perspective", "finding": "f", "score_pct": 40}]},],
 "issues": "one issue",}
```"""
    s = parse_block(text, FactCheckSummary)
    c = s.claims[0]
    assert c.accuracy_pct == 85 and c.confidence_pct == 100 and c.labels[0].label == "misleading"
    assert [t.type for t in c.claim_types] == ["fact", "testable"] and c.claim_types[1].confidence_pct == 60
    assert c.assessments[0].condition == "Bayesian perspective" and c.assessments[0].score_pct == 40
    assert s.issues == ["one issue"]
    assert s.accuracy() == 85  # mean of claims when overall is missing


def test_missing_block_and_all_accurate():
    assert parse_block("no json here", FactCheckSummary) is None
    s = FactCheckSummary(claims=[{"claim": "a", "accuracy_pct": 95}, {"claim": "b", "accuracy_pct": None}])
    assert not s.all_accurate(90)  # a missing score fails the threshold
    assert not FactCheckSummary().all_accurate(90)  # no claims -> not "all accurate"


def test_claim_list_accepts_strings_and_unfenced():
    assert [c.claim for c in parse_block('{"claims": ["a", {"claim": "b"}]}', ClaimList).claims] == ["a", "b"]

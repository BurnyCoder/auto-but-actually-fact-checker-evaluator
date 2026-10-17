"""LLM judges for the benchmarks, plus the shared helper for any single JSON-returning benchmark call.

Local: `llm_json` renders a prompts/ template, makes one call through RunContext.call on a small throw-away run and
parses the fenced JSON block into a pydantic model. `judge` (Exp07) grades a text against SciFact's gold abstract;
`judge_reference` (Exp08) grades a candidate passage against the original passage it was corrupted from.
Global context: bench/correction.py and bench/ai_errors.py call these for every text a correction loop produces;
bench/ai_errors.py also uses `llm_json` to inject errors. Going through RunContext.call means every prompt/output is
logged in full and every cost is checked against and recorded in the spend ledger.
SciFact rationale annotations: Wadden et al. 2020, https://arxiv.org/abs/2004.14974
"""

from ..config import FactCheckConfig
from ..context import RunContext
from ..prompts import ENV
from ..results import RUNS, new_run
from ..schema import JudgeVerdict, RefVerdict, parse_block


def llm_json(template: str, variables: dict, model, cfg: FactCheckConfig, label: str):
    """One call (check step of `cfg`) with prompts/<template>; returns (parsed model or None, LLMResult, run_id)."""
    prompt = ENV.get_template(template).render(**variables).strip()
    run = new_run(prompt[:80], cfg)
    ctx = RunContext(run, cfg)
    try:
        res = ctx.call("check", prompt, label)
        return (None if res.error else parse_block(res.text, model)), res, run.run_id
    finally:
        ctx.close()
        RUNS.pop(run.run_id, None)  # persisted in runs/<id>/; keep memory flat


def judge(text: str, question: str, evidence: list[dict], cfg: FactCheckConfig, label: str) -> dict:
    """Exp07 gold-evidence judge: correctness of `text` for the question of the original claim."""
    v, res, run_id = llm_json("judge/gold_evidence.md", {"text": text, "question": question, "evidence": evidence},
                              JudgeVerdict, cfg, label)
    return {"correct": v.correct() if v else None, "entailed": v.main_claim_entailed if v else None,
            "contradicts": v.contradicts_evidence if v else None, "same_question": v.same_question if v else None,
            "verdict": v.verdict if v else "", "explanation": v.explanation if v else "",
            "error": res.error or (None if v else "unparseable judge output"), "cost_usd": res.cost_usd,
            "model": res.model, "run_id": run_id}


def judge_reference(candidate: str, reference: str, errors: list[dict], cfg: FactCheckConfig, label: str) -> dict:
    """Exp08 reference judge: per injected error 1 / 0.5 / 0, introduced errors and a 0-100 accuracy score."""
    v, res, run_id = llm_json("judge/reference_errors.md",
                              {"candidate": candidate, "reference": reference, "errors": errors}, RefVerdict, cfg, label)
    fix = v.fix_scores([e["id"] for e in errors]) if v else {}
    known = [s for s in fix.values() if s is not None]
    return {"overall": v.overall_accuracy_pct if v else None, "fix": fix,
            "fix_mean": sum(known) / len(known) if known else None,
            "introduced": len(v.introduced_errors) if v else None, "introduced_list": v.introduced_errors if v else [],
            "error": res.error or (None if v else "unparseable judge output"), "cost_usd": res.cost_usd,
            "model": res.model, "run_id": run_id}

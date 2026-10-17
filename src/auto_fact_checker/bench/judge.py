"""Gold-evidence judge for Exp07: is a (corrected) text correct according to SciFact's cited abstract?

Local: renders prompts/judge/gold_evidence.md with the gold abstract sentences (expert rationale sentences marked),
the original claim (which fixes the question) and the text to judge; parses a JudgeVerdict.
Global context: bench/correction.py judges the original claim and every text the correction loop produces with one
or more judges from a different model family than the corrector. The call goes through RunContext.call, so the
judge's prompt/output are logged in full and its cost is checked against and recorded in the spend ledger.
SciFact rationale annotations: Wadden et al. 2020, https://arxiv.org/abs/2004.14974
"""

from ..config import FactCheckConfig
from ..context import RunContext
from ..prompts import ENV
from ..results import RUNS, new_run
from ..schema import JudgeVerdict, parse_block


def judge(text: str, question: str, evidence: list[dict], cfg: FactCheckConfig, label: str) -> dict:
    """One judge call (check step of `cfg`, no web search); returns correctness and the parsed fields."""
    run = new_run(text, cfg)
    ctx = RunContext(run, cfg)
    try:
        prompt = ENV.get_template("judge/gold_evidence.md").render(text=text, question=question,
                                                                    evidence=evidence).strip()
        res = ctx.call("check", prompt, label)
        v = None if res.error else parse_block(res.text, JudgeVerdict)
        return {"correct": v.correct() if v else None, "entailed": v.main_claim_entailed if v else None,
                "contradicts": v.contradicts_evidence if v else None, "same_question": v.same_question if v else None,
                "verdict": v.verdict if v else "", "explanation": v.explanation if v else "",
                "error": res.error or (None if v else "unparseable judge output"), "cost_usd": res.cost_usd,
                "model": res.model, "run_id": run.run_id}
    finally:
        ctx.close()
        RUNS.pop(run.run_id, None)  # persisted in runs/<id>/; keep memory flat

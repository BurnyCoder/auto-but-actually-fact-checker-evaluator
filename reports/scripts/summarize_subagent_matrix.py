"""Summarise the 2026-10-28 subagent combination matrix from local runs/ into a committed JSON record.

Local: for each (combination name, run id) read runs/<id>/run.json and run.log, then count calls, call errors,
Claude Code subagent spawns (Agent/Task tool_use events), Codex collab `wait` events, Codex spawn failures and
WARNING/ERROR log lines, and record the per-claim model-reported accuracies.
Global context: runs/ is git-ignored, so this record is the committed evidence behind
reports/verification_2026-10-28_subagents.md. Usage:
    uv run python reports/scripts/summarize_subagent_matrix.py OUT.json name=run_id [name=run_id ...]
"""

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # repo root: reports/scripts/ -> ../../


def summarize(name: str, run_id: str) -> dict:
    """One matrix row from a run's saved record and log."""
    run_dir = ROOT / "runs" / run_id
    run = json.loads((run_dir / "run.json").read_text(encoding="utf-8"))
    log = (run_dir / "run.log").read_text(encoding="utf-8", errors="replace")
    final = (run["iterations"][-1].get("final") or {}) if run["iterations"] else {}
    claims = (final.get("summary") or {}).get("claims", [])
    check = run["config"]["steps"]["check"]
    return {"name": name, "run_id": run_id, "status": run["status"], "stop_reason": run["stop_reason"],
            "claim_strategy": run["config"]["claim_strategy"], "scientist_strategy": run["config"]["scientist_strategy"],
            "check": f"{check['kind']}/{check['provider']}/{check['model']} search={check['web_search']}",
            "calls": len(run["calls"]), "call_errors": sum(bool(c["error"]) for c in run["calls"]),
            "billed_usd": round(sum(c["cost_usd"] or 0 for c in run["calls"] if c["billed"]), 5),
            "claude_subagent_spawns": len(re.findall(r'"name":\s*"(?:Agent|Task)"', log)),
            "codex_wait_events": len(re.findall(r'"item\.completed","item":\{[^}]*"tool":"wait"', log)),
            "codex_spawn_failures": log.count("collab spawn failed"),
            "warning_or_error_lines": len(re.findall(r"\| (?:WARNING|ERROR) ", log)),
            "claims": [{"claim": c["claim"], "accuracy_pct": c.get("accuracy_pct")} for c in claims]}


if __name__ == "__main__":
    rows = [summarize(*arg.split("=", 1)) for arg in sys.argv[2:]]
    Path(sys.argv[1]).write_text(json.dumps(rows, indent=1, ensure_ascii=False), encoding="utf-8")
    for r in rows:
        print(f"{r['name']:32} {r['status']:7} calls={r['calls']} err={r['call_errors']} "
              f"claude_spawns={r['claude_subagent_spawns']} codex_waits={r['codex_wait_events']} "
              f"spawn_fail={r['codex_spawn_failures']} warn={r['warning_or_error_lines']} "
              f"acc={[c['accuracy_pct'] for c in r['claims']]}")

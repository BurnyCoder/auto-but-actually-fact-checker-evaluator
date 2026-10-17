"""Persistent spend ledger (logs/spend.jsonl) enforcing the global SPEND_LIMIT_USD cap.

Local: append one JSON line per LLM call; sum the billed costs; refuse new calls once the cap is reached.
Global context: RunContext.call() (context.py) calls check_budget() before every LLM call and record() after it,
so the cap covers the UI, the CLI, live tests and the benchmark alike. Subscription-auth agent runs are recorded
with billed=False (their cost is notional) and do not count toward the cap.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()  # parallel per-claim calls append from several threads


class BudgetExceeded(RuntimeError):
    """Raised before an LLM call that would push cumulative billed spend over the limit."""


def record(ledger: Path, cost_usd: float | None, billed: bool, label: str, **extra) -> None:
    """Append one spend entry (timestamp, label, cost, billed flag, any extra metadata such as model/backend)."""
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "label": label, "cost_usd": cost_usd,
             "billed": billed, **extra}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, ledger.open("a", encoding="utf-8") as f:  # append-only JSON Lines, https://jsonlines.org/
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def total_billed(ledger: Path) -> float:
    """Sum of billed costs so far; unknown costs (None) count as 0 and a missing ledger means nothing spent."""
    if not ledger.exists():
        return 0.0
    with _LOCK:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    return sum((e.get("cost_usd") or 0.0) for e in map(json.loads, filter(None, lines)) if e.get("billed"))


def check_budget(ledger: Path, limit_usd: float, estimate_usd: float = 0.0) -> float:
    """Raise BudgetExceeded if the limit is already used up or spent + estimate would exceed it; else return spent."""
    spent = total_billed(ledger)
    if spent >= limit_usd or spent + estimate_usd > limit_usd:
        raise BudgetExceeded(f"Spend cap reached: ${spent:.4f} spent + ${estimate_usd:.4f} estimated "
                             f"> SPEND_LIMIT_USD=${limit_usd:.2f} (ledger: {ledger})")
    return spent

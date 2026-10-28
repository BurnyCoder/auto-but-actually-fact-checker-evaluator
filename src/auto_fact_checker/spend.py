"""Persistent ledger of estimated spend and a pre-call check against SPEND_LIMIT_USD.

Local: append one JSON line per LLM call; sum the billed costs; refuse new calls once the cap is reached.
Global context: RunContext.call() (context.py) calls check_budget() before every LLM call and record() after it,
so the cap covers the UI, the CLI and the benchmark; live tests call both functions themselves (tests/test_live.py).
The check is soft (recorded costs only, see README "Costs and safety"). Subscription-auth agent runs are recorded
with billed=False (their cost is notional) and do not count toward the cap.
"""

import json
import threading
from datetime import datetime
from pathlib import Path

_LOCK = threading.Lock()  # parallel per-claim calls append from several threads


class BudgetExceeded(RuntimeError):
    """Raised when recorded known spend plus a supplied estimate reaches the admission limit."""


def record(ledger: Path, cost_usd: float | None, billed: bool, label: str, **extra) -> None:
    """Append one spend entry (timestamp, label, cost, billed flag, any extra metadata such as model/backend)."""
    entry = {"ts": datetime.now().isoformat(timespec="seconds"), "label": label, "cost_usd": cost_usd,
             "billed": billed, **extra}
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK, ledger.open("a", encoding="utf-8") as f:  # append-only JSON Lines, https://jsonlines.org/
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def total_billed(ledger: Path) -> float:
    """Known billed estimates only; summary() separately exposes unknown-cost calls."""
    return summary(ledger)["known_billed_usd"]


def summary(ledger: Path) -> dict:
    """Return the known estimate and count of billed calls missing a cost, not an invoice total."""
    result = {"known_billed_usd": 0.0, "unknown_billed_calls": 0}
    if not ledger.exists():
        return result
    with _LOCK:
        lines = ledger.read_text(encoding="utf-8").splitlines()
    for line in filter(None, lines):
        try:
            e = json.loads(line)
        except json.JSONDecodeError:  # a line another process is still writing
            continue
        if e.get("billed"):
            if e.get("cost_usd") is None:
                result["unknown_billed_calls"] += 1
            else:
                result["known_billed_usd"] += e["cost_usd"]
    return result


def check_budget(ledger: Path, limit_usd: float, estimate_usd: float = 0.0) -> float:
    """Raise BudgetExceeded if the limit is already used up or spent + estimate would exceed it; else return spent."""
    spent = total_billed(ledger)
    if spent >= limit_usd or spent + estimate_usd > limit_usd:
        raise BudgetExceeded(f"Spend cap reached: ${spent:.4f} spent + ${estimate_usd:.4f} estimated "
                             f"> SPEND_LIMIT_USD=${limit_usd:.2f} (ledger: {ledger})")
    return spent

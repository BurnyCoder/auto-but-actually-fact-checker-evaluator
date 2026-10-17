"""Backend-independent request/result types.

Local: LLMRequest describes one call (prompt + per-step settings); LLMResult is what every backend returns.
Global context: RunContext.request() builds an LLMRequest from a StepConfig, RunContext.call() hands it to
backends.call_llm(), and the LLMResult is logged, costed, stored in runs/<id>/ and shown in the UI's cost table.
"""

import threading
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field


class LLMRequest(BaseModel):
    """One LLM call: which backend/model, the full prompt and the step's depth/search/subagent settings."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    backend: str  # "openai_api" | "anthropic_api" | "claude_code" | "codex"
    model: str
    prompt: str
    label: str = ""  # human-readable call name, e.g. "iter1/check/claim3"
    effort: str = "low"
    web_search: bool = False
    search_context_size: str = "medium"
    max_searches: int = 5
    blocked_domains: list[str] = Field(default_factory=list)
    allow_subagents: bool = False
    agents: dict | None = None  # Claude Code --agents definitions (subagent strategies)
    max_turns: int | None = None
    max_budget_usd: float | None = None  # per-call cap passed to Claude Code --max-budget-usd
    timeout_s: int = 900
    workdir: Path | None = None  # agent working directory (a fresh temp dir by default)
    cancel: threading.Event | None = Field(default=None, exclude=True)  # set by the UI's Stop button


class LLMResult(BaseModel):
    """Normalised outcome of one call, whatever the backend."""

    text: str = ""  # final answer (report + JSON block)
    backend: str
    model: str
    input_tokens: int = 0  # incl. cached tokens
    cached_input_tokens: int = 0
    output_tokens: int = 0  # incl. reasoning tokens
    web_searches: int = 0
    cost_usd: float | None = None  # None = unknown price
    billed: bool = True  # False for subscription-auth agent runs (cost is notional)
    sources: list[str] = Field(default_factory=list)  # URLs consulted or cited, in first-seen order
    duration_s: float = 0.0
    error: str | None = None


def dedupe(urls) -> list[str]:
    """Unique URLs in first-seen order (dict preserves insertion order since Python 3.7)."""
    return list(dict.fromkeys(u for u in urls if u))

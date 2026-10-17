"""Backend registry: maps a backend name to its call(LLMRequest, logger) -> LLMResult function.

Global context: config.backend_for(StepConfig) picks the name from (kind, provider); context.RunContext.call() is
the only caller of call_llm(), and tests replace entries in BACKENDS with fakes (monkeypatch) to run the whole
pipeline offline.
"""

from . import anthropic_api, claude_code, codex, openai_api
from .base import LLMRequest, LLMResult

BACKENDS = {"openai_api": openai_api.call, "anthropic_api": anthropic_api.call,
            "claude_code": claude_code.call, "codex": codex.call}


def call_llm(req: LLMRequest, log) -> LLMResult:
    """Dispatch one request to its backend."""
    return BACKENDS[req.backend](req, log)


__all__ = ["BACKENDS", "LLMRequest", "LLMResult", "call_llm"]

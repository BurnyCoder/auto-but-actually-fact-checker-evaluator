"""Anthropic Messages API backend: one conversation turn, optionally with the server-side web_search tool.

Local: builds the request (effort, web_search_20260318 with max_uses and blocked domains), streams it, continues
while the API pauses long server-tool turns (stop_reason == "pause_turn"), and sums usage/cost over continuations.
Global context: used for steps with kind="api", provider="anthropic". Native JSON output is not used because the
docs state structured outputs are incompatible with citations (always on for web search); the pipeline parses the
JSON block from the text instead. Docs: web search https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool ;
pause_turn https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools ;
streaming helpers https://github.com/anthropics/anthropic-sdk-python#streaming-helpers
"""

import logging
import time

import anthropic

from .. import catalog
from ..config import get_settings
from .base import LLMRequest, LLMResult, dedupe

MAX_TOKENS = 32_000  # long reports; streaming is required by the SDK for long requests
MAX_CONTINUATIONS = 8  # safety bound on pause_turn round-trips
EFFORT = {"none": "low", "minimal": "low"}  # output_config.effort accepts low|medium|high|xhigh|max


def build_kwargs(req: LLMRequest) -> dict:
    """messages.stream keyword arguments for the first turn."""
    kw = {"model": req.model, "max_tokens": MAX_TOKENS, "messages": [{"role": "user", "content": req.prompt}],
          "output_config": {"effort": EFFORT.get(req.effort, req.effort)}}
    if req.web_search:
        # allowed_callers=["direct"]: plain model-issued searches with citations. The default on _20260209+ routes
        # searches through code execution ("dynamic filtering"), which exhausted max_uses without an answer in our
        # live test with claude-haiku-5-5 (2026-10-17).
        tool = {"type": "web_search_20260318", "name": "web_search", "max_uses": req.max_searches,
                "allowed_callers": ["direct"]}
        if req.blocked_domains:
            tool["blocked_domains"] = req.blocked_domains  # cannot be combined with allowed_domains
        kw["tools"] = [tool]
    return kw


def run(client, req: LLMRequest, log: logging.Logger | logging.LoggerAdapter,
        workspace_id: str | None = None) -> LLMResult:
    """Execute the request with an existing client (injectable for tests), following pause_turn continuations."""
    kw = build_kwargs(req)
    if workspace_id:
        kw["workspace_id"] = workspace_id  # sent as the anthropic-workspace-id header
    texts, urls = [], []
    tin = tout = searches = 0
    cost = 0.0
    for _ in range(MAX_CONTINUATIONS):
        with client.messages.stream(**kw) as stream:
            msg = stream.get_final_message()  # consumes the stream and returns the accumulated Message
        for b in msg.content:
            if b.type == "text":
                texts.append(b.text)
                urls += [getattr(c, "url", None) for c in (getattr(b, "citations", None) or [])]
            elif b.type == "server_tool_use":
                log.info("[anthropic %s] %s", getattr(b, "name", "tool"), getattr(b, "input", ""))
            elif b.type == "web_search_tool_result" and isinstance(b.content, list):  # error results are objects
                urls += [getattr(x, "url", None) for x in b.content]
        u = msg.usage
        n = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
        tin, tout, searches = tin + u.input_tokens, tout + u.output_tokens, searches + n
        cost += catalog.cost_usd(req.model, u.input_tokens, u.output_tokens, web_searches=n) or 0.0  # per request
        if msg.stop_reason != "pause_turn":
            break
        # Continue the paused server-tool turn by sending the assistant content back unchanged (docs: pause_turn).
        kw["messages"] = kw["messages"] + [{"role": "assistant", "content": msg.content}]
    result = LLMResult(text="".join(texts), backend="anthropic_api", model=req.model, input_tokens=tin,
                       output_tokens=tout, web_searches=searches, sources=dedupe(urls),
                       cost_usd=cost if req.model in catalog.MODELS else None)
    if msg.stop_reason in ("max_tokens", "refusal"):
        result.error = f"stop_reason={msg.stop_reason}"
    return result


def call(req: LLMRequest, log: logging.Logger | logging.LoggerAdapter) -> LLMResult:
    """Create a client from .env and run the request."""
    s = get_settings()
    key = s.anthropic_api_key
    client = anthropic.Anthropic(api_key=key.get_secret_value() if key else None, timeout=req.timeout_s)
    t0 = time.monotonic()
    result = run(client, req, log, workspace_id=s.anthropic_workspace_id)
    result.duration_s = time.monotonic() - t0
    return result

"""Anthropic Messages API backend: one conversation turn, optionally with the server-side web_search tool.

Local: builds the request (effort, web_search_20260318 with max_uses and blocked domains), streams it, continues
while the API pauses long server-tool turns (stop_reason == "pause_turn"), and sums usage/cost over continuations.
Global context: used for steps with kind="api", provider="anthropic". Native JSON output is not used because the
docs state structured outputs are incompatible with citations (always on for web search; "Feature compatibility" in
https://platform.claude.com/docs/en/build-with-claude/structured-outputs); the pipeline parses the JSON block from
the text instead. Docs: web search https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool ;
pause_turn https://platform.claude.com/docs/en/agents-and-tools/tool-use/server-tools ;
effort levels https://platform.claude.com/docs/en/build-with-claude/effort ; cache usage fields (cache_read_input_tokens,
cache_creation.ephemeral_5m/1h_input_tokens) https://platform.claude.com/docs/en/build-with-claude/prompt-caching ;
streaming helpers https://github.com/anthropics/anthropic-sdk-python/blob/main/helpers.md#streaming-responses
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
    """Stream one logical call; max_uses and SDK timeouts apply separately to each continuation request."""
    kw = build_kwargs(req)
    if workspace_id:
        kw["workspace_id"] = workspace_id  # sent as the anthropic-workspace-id header
    result = LLMResult(backend="anthropic_api", model=req.model, cost_usd=0.0)
    for _ in range(MAX_CONTINUATIONS):
        if req.cancel is not None and req.cancel.is_set():  # A completed previous request retains known usage.
            result.error = "cancelled"
            return result
        chunks = []  # Only used if interrupted; completed messages below supply the canonical full text.
        with client.messages.stream(**kw) as stream:
            for event in stream:  # SDK helpers expose text events before get_final_message().
                if event.type == "text":
                    chunks.append(event.text)
                    log.info("[anthropic text] %s", event.text)  # Full delta, immediately mirrored to file/terminal.
                if req.cancel is not None and req.cancel.is_set():
                    result.text += "".join(chunks)
                    result.cost_usd, result.error = None, "cancelled"  # Final usage is unavailable for this request.
                    return result  # Exiting the context closes the stream; server-side billing may still occur.
            msg = stream.get_final_message()
        for b in msg.content:
            if b.type == "text":
                result.text += b.text
                result.sources += [getattr(c, "url", None) for c in (getattr(b, "citations", None) or [])
                                   if getattr(c, "url", None)]
            elif b.type == "server_tool_use":
                log.info("[anthropic %s] %s", getattr(b, "name", "tool"), getattr(b, "input", ""))
            elif b.type == "web_search_tool_result" and isinstance(b.content, list):  # error results are objects
                result.sources += [x.url for x in b.content if getattr(x, "url", None)]
        u = msg.usage
        n = getattr(getattr(u, "server_tool_use", None), "web_search_requests", 0) or 0
        read = getattr(u, "cache_read_input_tokens", 0) or 0
        written = getattr(u, "cache_creation_input_tokens", 0) or 0
        cache = getattr(u, "cache_creation", None)
        short = getattr(cache, "ephemeral_5m_input_tokens", 0) or 0
        long = getattr(cache, "ephemeral_1h_input_tokens", 0) or 0
        total = u.input_tokens + read + written  # Anthropic's three disjoint input categories form the context.
        result.input_tokens += total
        result.cached_input_tokens += read
        result.cache_creation_input_tokens += written
        result.output_tokens += u.output_tokens
        result.web_searches += n
        cost = (catalog.cost_usd(req.model, total, u.output_tokens, read, n,
                                cache_write_short_tokens=short, cache_write_long_tokens=long)
                if written == short + long else None)  # Missing TTL information cannot produce an exact estimate.
        result.cost_usd = result.cost_usd + cost if result.cost_usd is not None and cost is not None else None
        result.sources = dedupe(result.sources)
        if msg.stop_reason != "pause_turn":
            break
        # Continue the paused server-tool turn by sending the assistant content back unchanged (docs: pause_turn).
        kw["messages"] = kw["messages"] + [{"role": "assistant", "content": msg.content}]
    if msg.stop_reason in ("max_tokens", "refusal", "pause_turn"):  # pause_turn here = continuations exhausted
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

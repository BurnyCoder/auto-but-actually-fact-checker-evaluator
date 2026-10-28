"""OpenAI Responses API backend: one request, optionally with the hosted web_search tool.

Local: builds the request (reasoning effort, web_search tool with domain filters and a tool-call cap), streams it
(logging each web search as it completes) and maps the response to LLMResult with sources and computed cost.
Global context: used for every step whose StepConfig is kind="api", provider="openai" — the default for all steps.
With web_search=False this is a single non-agentic LLM call; with it, OpenAI runs the search loop server-side.
Docs: Responses API https://developers.openai.com/api/reference/resources/responses/methods/create.md ;
web search tool (filters, include sources) https://developers.openai.com/api/docs/guides/tools-web-search ;
streaming helper https://github.com/openai/openai-python/blob/main/helpers.md
"""

import logging
import time

from openai import OpenAI

from .. import catalog
from ..config import get_settings
from .base import LLMRequest, LLMResult, dedupe


def build_kwargs(req: LLMRequest) -> dict:
    """responses.create/stream keyword arguments for one request."""
    kw = {"model": req.model, "input": req.prompt, "reasoning": {"effort": req.effort}}
    if req.web_search:
        tool = {"type": "web_search", "search_context_size": req.search_context_size,
                "user_location": {"type": "approximate"}}  # omitted -> "defaults to the United States" (Responses API ref)
        if req.blocked_domains:
            tool["filters"] = {"blocked_domains": req.blocked_domains}  # e.g. benchmark hosts (leakage guard)
        kw |= {"tools": [tool], "include": ["web_search_call.action.sources"],  # available recorded source URLs
               "max_tool_calls": req.max_searches}  # caps built-in tool calls -> caps search cost
    return kw


def parse_response(req: LLMRequest, r) -> LLMResult:
    """Map a Response to LLMResult; counts 'search' actions as billed tool calls (the docs list only those)."""
    calls = [o for o in r.output if o.type == "web_search_call"]
    searches = sum(1 for c in calls if getattr(c.action, "type", None) == "search")
    urls = []
    for c in calls:
        urls += [s.url for s in (getattr(c.action, "sources", None) or [])]  # consulted sources (include=...)
        urls.append(getattr(c.action, "url", None))  # pages opened directly
    for o in r.output:
        if o.type == "message":
            urls += [a.url for part in o.content for a in (getattr(part, "annotations", None) or [])
                     if a.type == "url_citation"]  # inline citations
    u = r.usage
    tin, tout = getattr(u, "input_tokens", None), getattr(u, "output_tokens", None)
    details = getattr(u, "input_tokens_details", None)
    cached = getattr(details, "cached_tokens", None)
    # Reads and writes are subsets of input_tokens; writes split by TTL, and requests that set no
    # prompt_cache_options (as here) use the default "30m"
    # (https://developers.openai.com/api/docs/guides/prompt-caching).
    written = getattr(details, "cache_write_tokens", 0) or 0
    split = getattr(details, "cache_write_tokens_details", None)
    w12h = getattr(split, "ttl_12h_tokens", 0) or 0
    # Usage is optional in the response schema; preserve available text and expose an incomplete estimate.
    cost = (catalog.cost_usd(req.model, tin, tout, cached, searches, cache_write_short_tokens=written - w12h,
                             cache_write_long_tokens=w12h) if None not in (tin, tout, cached) else None)
    return LLMResult(text=r.output_text or "", backend="openai_api", model=req.model, input_tokens=tin or 0,
                     cached_input_tokens=cached or 0, cache_creation_input_tokens=written, output_tokens=tout or 0,
                     web_searches=searches, cost_usd=cost, sources=dedupe(urls))


def call(req: LLMRequest, log: logging.Logger | logging.LoggerAdapter) -> LLMResult:
    """Run one streamed Responses API request and return the normalised result."""
    if req.cancel is not None and req.cancel.is_set():
        return LLMResult(backend="openai_api", model=req.model, error="cancelled", cost_usd=0.0)
    key = get_settings().openai_api_key
    client = OpenAI(api_key=key.get_secret_value() if key else None, timeout=req.timeout_s)
    t0 = time.monotonic()
    chunks = []  # Keep observable partial text if Stop arrives before final usage.
    with client.responses.stream(**build_kwargs(req)) as stream:
        for event in stream:  # realtime visibility of the server-side search loop
            if event.type == "response.output_text.delta":
                chunks.append(event.delta)
                log.info("[openai text] %s", event.delta)  # Untruncated delta; full final output is also archived.
            if req.cancel is not None and req.cancel.is_set():  # UI Stop: abandon the stream (closed on exit)
                return LLMResult(text="".join(chunks), backend="openai_api", model=req.model, error="cancelled",
                                 duration_s=time.monotonic() - t0)
            if event.type == "response.output_item.done" and event.item.type == "web_search_call":
                a = event.item.action
                log.info("[openai web_search] %s %s", getattr(a, "type", ""), getattr(a, "query", None)
                         or getattr(a, "queries", None) or getattr(a, "url", ""))
        response = stream.get_final_response()
    result = parse_response(req, response)
    result.duration_s = time.monotonic() - t0
    if getattr(response, "status", "completed") != "completed":  # e.g. "incomplete" (token limit)
        result.error = f"response status {response.status}: {getattr(response, 'incomplete_details', None)}"
    return result

"""Static price catalog for listed models, plus per-request cost estimation.

Local: a static table of $/1M-token prices and a cost_usd() helper.
Global context: OpenAI (Responses API, Codex) and Anthropic (Messages API) return token counts but no dollar
cost, so those backend estimates use this table. Claude Code reports its own total_cost_usd. These are
standard-rate estimates, not invoices; service tiers, discounts and unavailable usage may change actual charges.

Prices verified 2026-10-17 and re-checked 2026-10-22 (incl. long-context cached rates) from:
- OpenAI:    https://developers.openai.com/api/docs/pricing  (web search: $10 / 1k calls)
- Anthropic: https://platform.claude.com/docs/en/about-claude/pricing  (web search: $10 / 1k searches)
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ModelInfo:
    """One selectable model: provider, $ per 1M tokens and an optional long-context price tier."""

    provider: str  # "openai" or "anthropic" -> which backends can run it
    input_per_m: float  # $ per 1M uncached input tokens
    output_per_m: float  # $ per 1M output tokens (reasoning tokens are billed as output)
    cached_per_m: float  # $ per 1M cached input tokens (OpenAI automatic prompt caching)
    long_threshold: int | None = None  # input tokens above which the whole request uses the long tier
    long_input_per_m: float | None = None  # long-tier input price
    long_output_per_m: float | None = None  # long-tier output price
    note: str = ""  # short human description shown in the UI dropdown
    long_cached_per_m: float | None = None  # long-tier cached-input price


# OpenAI: "Prompts with more than 272K input tokens are priced at 2x input and cache rates and 1.5x output for the
# full request" (model page, e.g. https://developers.openai.com/api/docs/models/gpt-6-luna); prices: pricing page.
_OAI_LONG = 272_000
MODELS: dict[str, ModelInfo] = {
    "gpt-6-luna": ModelInfo("openai", 0.10, 0.50, 0.01, _OAI_LONG, 0.20, 0.75, "cheapest GPT-6", 0.02),
    "gpt-6.1-sol": ModelInfo("openai", 2.00, 10.00, 0.10, _OAI_LONG, 4.00, 15.00, "mid-tier GPT-6.1", 0.20),
    "gpt-6-sol": ModelInfo("openai", 2.00, 10.00, 0.20, _OAI_LONG, 4.00, 15.00, "older Sol", 0.40),
    "gpt-6-astra": ModelInfo("openai", 10.00, 50.00, 1.00, _OAI_LONG, 20.00, 75.00, "most capable GPT-6", 2.00),
    "gpt-5.6-luna": ModelInfo("openai", 0.20, 1.20, 0.02, _OAI_LONG, 0.40, 1.80, "previous-gen Luna", 0.04),
    "gpt-5.4-mini": ModelInfo("openai", 0.75, 4.50, 0.075, note="GPT-5.4 mini"),
    # Anthropic: Haiku 5.5 prompts over 100K tokens cost $0.50 in / $2.50 out / $0.05 cache hits (pricing page).
    "claude-haiku-5-5": ModelInfo("anthropic", 0.10, 0.50, 0.01, 100_000, 0.50, 2.50, "cheapest Claude 5", 0.05),
    "claude-sonnet-5-5": ModelInfo("anthropic", 2.00, 10.00, 0.10, note="balanced Claude 5"),
    "claude-opus-5-5": ModelInfo("anthropic", 4.00, 20.00, 0.20, note="strong Claude 5"),
    "claude-fable-5-1": ModelInfo("anthropic", 10.00, 50.00, 0.25, note="most capable Claude"),
}

WEB_SEARCH_USD = 0.01  # both providers charge $10 per 1,000 searches (see module docstring links)
DEFAULT_MODEL = {"openai": "gpt-6-luna", "anthropic": "claude-haiku-5-5"}  # cheap defaults everywhere


def models_for(provider: str) -> list[str]:
    """Catalogued model IDs for a provider; account access and availability are not checked here."""
    return [m for m, info in MODELS.items() if info.provider == provider]


def label(model: str) -> str:
    """Dropdown label such as 'gpt-6-luna — $0.10/$0.50 per 1M (cheapest GPT-6)'; unknown ids are shown as-is."""
    info = MODELS.get(model)
    return f"{model} — ${info.input_per_m:.2f}/${info.output_per_m:.2f} per 1M ({info.note})" if info else model


def choices(provider: str) -> list[tuple[str, str]]:
    """(label, value) pairs for a Gradio Dropdown; https://www.gradio.app/docs/gradio/dropdown accepts tuples."""
    return [(label(m), m) for m in models_for(provider)]


def cost_usd(model: str, input_tokens: int, output_tokens: int, cached_input_tokens: int = 0,
             web_searches: int = 0, *, cache_write_5m_tokens: int = 0,
             cache_write_1h_tokens: int = 0) -> float | None:
    """Standard-rate estimate for one request; None for unpriced models or unsupported cache writes.

    Input includes cache reads and writes after backend normalization. Anthropic's 5m/1h write rates are
    1.25x/2x base input: https://platform.claude.com/docs/en/build-with-claude/prompt-caching#pricing .
    """
    info = MODELS.get(model)
    if info is None or ((cache_write_5m_tokens or cache_write_1h_tokens) and info.provider != "anthropic"):
        return None
    long = info.long_threshold is not None and input_tokens > info.long_threshold  # tier applies to the whole request
    in_rate = info.long_input_per_m if long else info.input_per_m
    out_rate = info.long_output_per_m if long else info.output_per_m
    cached_rate = info.long_cached_per_m if long else info.cached_per_m
    uncached = max(input_tokens - cached_input_tokens - cache_write_5m_tokens - cache_write_1h_tokens, 0)
    tokens = (uncached * in_rate + cached_input_tokens * cached_rate + output_tokens * out_rate
              + cache_write_5m_tokens * in_rate * 1.25 + cache_write_1h_tokens * in_rate * 2)
    return tokens / 1_000_000 + web_searches * WEB_SEARCH_USD

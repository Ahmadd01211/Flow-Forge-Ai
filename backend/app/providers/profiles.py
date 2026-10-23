"""Reviewed text-generation profiles. A listed model alone is not an execution capability."""

from decimal import Decimal

from pydantic import BaseModel


class ModelCapability(BaseModel):
    runnable: bool = False
    local_tools: bool = False
    structured_output: bool = False
    input_usd_per_million: str | None = None
    output_usd_per_million: str | None = None
    reason: str = "No reviewed execution and pricing profile is available for this model."
    pricing_checked_at: str | None = None


# Standard, uncached text rates; discounts and negotiated pricing are not assumed.
# Sources and supported scope: docs/learning/10-PROVIDER-CAPABILITIES.md.
RATES = {
    ("openai", "gpt-5-mini"): ("0.25", "2.00"),
    ("openai", "gpt-5-nano"): ("0.05", "0.40"),
    ("openai", "gpt-5"): ("1.25", "10.00"),
    ("gemini", "gemini-2.5-flash"): ("0.30", "2.50"),
    ("gemini", "gemini-2.5-flash-lite"): ("0.10", "0.40"),
    ("deepseek", "deepseek-flash"): ("0.30", "1.20"),
    ("deepseek", "deepseek-v4-pro"): ("1.32", "3.96"),
    ("anthropic", "claude-haiku-4-5"): ("1.00", "5.00"),
    ("anthropic", "claude-haiku-4-5-20251001"): ("1.00", "5.00"),
    ("anthropic", "claude-sonnet-4-6"): ("3.00", "15.00"),
    ("openrouter", "openai/gpt-4o-mini"): ("0.15", "0.60"),
}
MODEL_PRICES = {
    key: (Decimal(i) / 1_000_000, Decimal(o) / 1_000_000) for key, (i, o) in RATES.items()
}


def capability(provider: str, model_id: str) -> ModelCapability:
    rates = RATES.get((provider, model_id))
    if not rates:
        return ModelCapability()
    return ModelCapability(
        runnable=True,
        local_tools=provider == "openai",
        structured_output=True,
        input_usd_per_million=rates[0],
        output_usd_per_million=rates[1],
        reason="Ready for text agent runs when this provider lists the model.",
        pricing_checked_at="2026-10-23",
    )

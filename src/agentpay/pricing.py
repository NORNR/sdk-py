from __future__ import annotations

from dataclasses import dataclass


MODEL_PRICING_PER_MILLION_TOKENS: dict[str, dict[str, float]] = {
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    "gpt-4.1-mini": {"input": 0.4, "output": 1.6},
    "gpt-4.1-nano": {"input": 0.1, "output": 0.4},
    "gpt-5": {"input": 1.25, "output": 10.0},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
}


def _estimate_tokens_from_text(text: str | None) -> int:
    if not text:
        return 0
    return max(1, len(text) // 4)


@dataclass(frozen=True)
class CostEstimate:
    model: str
    prompt_tokens: int
    completion_tokens: int
    estimated_input_usd: float
    estimated_output_usd: float
    estimated_total_usd: float
    warning: str | None = None


def estimate_cost(
    *,
    model: str,
    prompt: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int = 0,
) -> CostEstimate:
    pricing = MODEL_PRICING_PER_MILLION_TOKENS.get(model)
    tokens_in = prompt_tokens if prompt_tokens is not None else _estimate_tokens_from_text(prompt)
    if pricing is None:
        return CostEstimate(
            model=model,
            prompt_tokens=tokens_in,
            completion_tokens=completion_tokens,
            estimated_input_usd=0.0,
            estimated_output_usd=0.0,
            estimated_total_usd=0.0,
            warning=f"No built-in pricing table for model {model}.",
        )
    input_usd = round((tokens_in / 1_000_000) * pricing["input"], 6)
    output_usd = round((completion_tokens / 1_000_000) * pricing["output"], 6)
    total_usd = round(input_usd + output_usd, 6)
    warning = None
    if total_usd >= 1:
        warning = f"Estimated cost {total_usd:.2f} USD is unusually high for a single request."
    return CostEstimate(
        model=model,
        prompt_tokens=tokens_in,
        completion_tokens=completion_tokens,
        estimated_input_usd=input_usd,
        estimated_output_usd=output_usd,
        estimated_total_usd=total_usd,
        warning=warning,
    )

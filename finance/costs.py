"""What did the AI cost?

In plain English: every Claude response says how many tokens it read and wrote.
We multiply by the prices in config.yaml and log it, so you always know the spend.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class AICall:
    purpose: str  # "extract" or "categorize"
    model: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    stop_reason: str | None


def from_response(purpose: str, model: str, resp, started: float) -> AICall:
    return AICall(
        purpose=purpose,
        model=model,
        input_tokens=resp.usage.input_tokens,
        output_tokens=resp.usage.output_tokens,
        duration_ms=int((time.monotonic() - started) * 1000),
        stop_reason=resp.stop_reason,
    )


def cost_usd(call: AICall, settings) -> float:
    price = settings.pricing_per_million_tokens.get(call.model)
    if price is None:
        return 0.0
    return (call.input_tokens * price.input + call.output_tokens * price.output) / 1_000_000

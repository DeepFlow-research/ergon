"""Synthetic usage metrics for smoke worker context chunks."""

from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunk,
    ProviderTokenUsage,
)

_SMOKE_TOKEN_COST_USD = 0.000001


def smoke_assistant_chunk(content: str) -> ContextPartChunk:
    """Return a smoke transcript chunk with deterministic observed usage."""
    token_count = max(1, len(content.split()))
    return ContextPartChunk(
        part=AssistantTextPart(content=content),
        provider_usage=ProviderTokenUsage(
            completion_tokens=token_count,
            total_tokens=token_count,
            total_cost_usd=round(token_count * _SMOKE_TOKEN_COST_USD, 8),
        ),
    )

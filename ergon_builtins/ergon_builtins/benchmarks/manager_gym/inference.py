"""Bounded internal inference using Ergon's provider and transcript adapter."""

import asyncio
from time import monotonic
from typing import Any
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter
from ergon_builtins.llm.resolution import resolve_model_target
from ergon_core.core.shared.context_parts import ContextPartChunk, ProviderTokenUsage

INTERNAL_MODEL = (
    "openai-compatible:https://api.training.hcompany.ai/v1/models/qwen3-8-27b-28#qwen3-8-27b-28"
)


def model_settings(temperature: float = 0.0) -> ModelSettings:
    return ModelSettings(
        temperature=temperature,
        max_tokens=32768,
        timeout=300,
        extra_body={"thinking_token_budget": 2048},
    )


def inference_profile() -> dict[str, Any]:
    return {
        "request_settings": model_settings(),
        "role_temperatures": {
            "manager": 0,
            "ai": 0,
            "human": 0.7,
            "stakeholder": 0,
            "estimator": 0,
            "decomposer": 1,
            "judge": 0,
        },
        "validation_retries": 2,
        "request_limit": 12,
        "operation_timeout_seconds": 600,
    }


class InferenceResult(BaseModel):
    output: dict[str, Any]
    chunks: list[ContextPartChunk] = Field(default_factory=list)
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int


def require_internal_model(model: str) -> str:
    prefix, _, target = model.partition(":")
    if (
        prefix != "openai-compatible"
        or urlsplit(target.split("#")[0]).hostname != "api.training.hcompany.ai"
    ):
        raise ValueError("MAG integration runs require an explicit internal training gateway model")
    if not target.partition("#")[2]:
        raise ValueError("MAG requires the explicit served model id after #")
    return model


async def infer(
    *,
    model: str,
    system: str,
    prompt: str,
    output_type: type[BaseModel],
    tools: list[Any] | None = None,
    temperature: float = 0.0,
) -> InferenceResult:
    resolved = resolve_model_target(require_internal_model(model))
    agent = Agent[None, BaseModel](
        resolved.model,
        system_prompt=system,
        output_type=output_type,
        tools=tools or [],
        retries=2,
        model_settings=model_settings(temperature),
    )
    started = monotonic()
    async with asyncio.timeout(600):
        result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=12))
    usage = result.usage()
    chunks = PydanticAITranscriptAdapter().build_chunks(result.all_messages())
    if chunks:
        chunks[-1] = chunks[-1].model_copy(
            update={
                "provider_usage": ProviderTokenUsage(
                    prompt_tokens=usage.input_tokens,
                    completion_tokens=usage.output_tokens,
                    total_tokens=usage.total_tokens,
                )
            }
        )
    return InferenceResult(
        output=result.output.model_dump(mode="json"),
        chunks=chunks,
        elapsed_seconds=monotonic() - started,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
    )

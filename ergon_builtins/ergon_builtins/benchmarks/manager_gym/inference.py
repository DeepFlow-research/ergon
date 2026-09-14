"""Bounded internal inference using Ergon's provider and transcript adapter."""

import asyncio
import json
from time import monotonic
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ToolOutput, capture_run_messages
from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter
from ergon_builtins.llm.resolution import resolve_model_target
from ergon_core.core.shared.context_parts import ContextPartChunk, ProviderTokenUsage

INTERNAL_MODEL = (
    "openai-compatible:https://gateway.example.invalid/v1/models/qwen3-8-27b-28#qwen3-8-27b-28"
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
        "work_operation_timeout_seconds": None,
        "work_lifetime_owner": "native_task_cancellation",
        "output_mode": "strict_output_tool",
        "output_tool_strict": True,
        "worker_model_failure_policy": "native_failed_task",
    }


class ModelFailure(BaseModel):
    kind: Literal["request_limit", "output_validation"]
    message: str


class InferenceResult(BaseModel):
    output: dict[str, Any]
    chunks: list[ContextPartChunk] = Field(default_factory=list)
    elapsed_seconds: float
    input_tokens: int
    output_tokens: int
    failure: ModelFailure | None = None


def captured_result(
    output: dict[str, Any],
    messages: list[ModelMessage],
    started: float,
    failure: ModelFailure | None = None,
) -> InferenceResult:
    responses = [m for m in messages if isinstance(m, ModelResponse)]
    input_tokens = sum(m.usage.input_tokens for m in responses)
    output_tokens = sum(m.usage.output_tokens for m in responses)
    chunks = PydanticAITranscriptAdapter().build_chunks(messages)
    if chunks:
        chunks[-1] = chunks[-1].model_copy(
            update={
                "provider_usage": ProviderTokenUsage(
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    total_tokens=input_tokens + output_tokens,
                )
            }
        )
    return InferenceResult(
        output=output,
        chunks=chunks,
        elapsed_seconds=monotonic() - started,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        failure=failure,
    )


def require_internal_model(model: str) -> str:
    prefix, _, target = model.partition(":")
    if (
        prefix != "openai-compatible"
        or urlsplit(target.split("#")[0]).hostname != "gateway.example.invalid"
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
    accept_model_failure: bool = False,
) -> InferenceResult:
    resolved = resolve_model_target(require_internal_model(model))
    agent = Agent[None, BaseModel](
        resolved.model,
        system_prompt=system,
        output_type=ToolOutput(output_type, strict=True),
        tools=tools or [],
        retries=2,
        model_settings=model_settings(temperature),
    )
    started = monotonic()
    with capture_run_messages() as messages:
        try:
            # Work lifetime belongs to the native task. Its request budget and
            # provider deadlines still apply; manager/auxiliary calls stay bounded.
            async with asyncio.timeout(None if accept_model_failure else 600):
                result = await agent.run(prompt, usage_limits=UsageLimits(request_limit=12))
        except (AgentRunError, TimeoutError) as error:
            # MAG work roles return unsuccessful task results for bounded model
            # behavior. Transport, tool, storage and timeout failures still raise;
            # managers, estimators and judges retain their strict default.
            if (
                accept_model_failure
                and isinstance(error, (UsageLimitExceeded, UnexpectedModelBehavior))
                and any(isinstance(m, ModelResponse) for m in messages)
            ):
                return captured_result(
                    {},
                    messages,
                    started,
                    ModelFailure(
                        kind="request_limit"
                        if isinstance(error, UsageLimitExceeded)
                        else "output_validation",
                        message=str(error),
                    ),
                )
            # Exception notes survive the existing native error/step traceback.
            # Retain response accounting without copying prompts or tool arguments.
            error.add_note(
                json.dumps(
                    {
                        "model_responses": [
                            {
                                "finish_reason": message.finish_reason,
                                "input_tokens": message.usage.input_tokens,
                                "output_tokens": message.usage.output_tokens,
                                "reasoning_tokens": message.usage.details.get("reasoning_tokens"),
                                "tools": [
                                    {
                                        "name": part.tool_name,
                                        "arguments_characters": len(part.args_as_json_str()),
                                    }
                                    for part in message.parts
                                    if isinstance(part, ToolCallPart)
                                ],
                            }
                            for message in messages
                            if isinstance(message, ModelResponse)
                        ]
                    }
                )
            )
            raise
    return captured_result(result.output.model_dump(mode="json"), result.all_messages(), started)

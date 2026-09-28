"""Bounded model calls for Manager Gym roles, through Ergon's model resolution."""

import asyncio
import json
from time import monotonic
from typing import Any, Literal

from ergon_core.core.shared.context_parts import ContextPartChunk, ProviderTokenUsage
from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, ToolOutput, capture_run_messages
from pydantic_ai.exceptions import AgentRunError, UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelMessage, ModelResponse, ToolCallPart
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from ergon_builtins.common.llm_context.adapters.pydantic_ai import PydanticAITranscriptAdapter
from ergon_builtins.llm.resolution import resolve_model_target

Role = Literal["manager", "decomposer", "ai", "human", "stakeholder", "estimator", "judge"]

# Upstream parity: MAG samples human workers at 0.7 and task decomposition at
# 1.0; every other role is deterministic.
DEFAULT_TEMPERATURES: dict[Role, float] = {
    "manager": 0,
    "decomposer": 1,
    "ai": 0,
    "human": 0.7,
    "stakeholder": 0,
    "estimator": 0,
    "judge": 0,
}


class InferenceProfile(BaseModel):
    """Sampling settings and limits applied to every model call in an episode.

    The profile is part of ``EpisodeConfig``, so it is recorded with each sample
    and every role of an episode uses the same limits.
    """

    model_config = ConfigDict(frozen=True)

    temperatures: dict[Role, float] = Field(
        default_factory=lambda: dict(DEFAULT_TEMPERATURES),
        description="Sampling temperature per role.",
    )
    max_tokens: int = Field(default=32_768, gt=0, description="Output token cap per request.")
    request_timeout_seconds: float = Field(default=300, gt=0, description="Per-request timeout.")
    thinking_token_budget: int | None = Field(
        default=None,
        gt=0,
        description=(
            "Reasoning token cap sent as vLLM's `thinking_token_budget`. Leave unset for "
            "providers that reject unknown request fields."
        ),
    )
    output_retries: int = Field(
        default=2, ge=0, description="Retries when a response fails output validation."
    )
    request_limit: int = Field(
        default=12, gt=0, description="Model requests allowed per call, including tool rounds."
    )
    operation_timeout_seconds: float = Field(
        default=600,
        gt=0,
        description="Wall-clock bound on manager, estimator and judge calls. Work calls are "
        "bounded by their native task instead.",
    )

    def model_settings(self, role: Role) -> ModelSettings:
        """Request settings for one model call made by ``role``."""
        settings = ModelSettings(
            temperature=self.temperatures[role],
            max_tokens=self.max_tokens,
            timeout=self.request_timeout_seconds,
        )
        if self.thinking_token_budget is not None:
            settings["extra_body"] = {"thinking_token_budget": self.thinking_token_budget}
        return settings


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


async def infer(
    *,
    model: str,
    role: Role,
    profile: InferenceProfile,
    system: str,
    prompt: str,
    output_type: type[BaseModel],
    tools: list[Any] | None = None,
    accept_model_failure: bool = False,
) -> InferenceResult:
    """Run one structured model call for a MAG role.

    Args:
        model: Ergon model target, e.g. ``"openai:gpt-4o"`` or
            ``"openai-compatible:http://localhost:8000#Qwen/Qwen3-8B"``.
        role: The role making the call; selects its temperature.
        profile: The episode's inference limits.
        system: System prompt.
        prompt: User prompt.
        output_type: Model the response must validate against, returned through
            a strict output tool.
        tools: Extra tools the model may call before answering.
        accept_model_failure: Return request-limit and output-validation failures
            as ``InferenceResult.failure`` instead of raising. Work roles use this
            so the native task fails rather than the episode.

    Returns:
        The validated output with its transcript chunks and token usage.
    """
    resolved = resolve_model_target(model)
    agent = Agent[None, BaseModel](
        resolved.model,
        system_prompt=system,
        output_type=ToolOutput(output_type, strict=True),
        tools=tools or [],
        retries=profile.output_retries,
        model_settings=profile.model_settings(role),
    )
    started = monotonic()
    timeout = None if accept_model_failure else profile.operation_timeout_seconds
    with capture_run_messages() as messages:
        try:
            # Work lifetime belongs to the native task. Its request budget and
            # provider deadlines still apply; manager/auxiliary calls stay bounded.
            async with asyncio.timeout(timeout):
                result = await agent.run(
                    prompt, usage_limits=UsageLimits(request_limit=profile.request_limit)
                )
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

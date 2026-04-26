from collections.abc import Sequence
from typing import Literal, TypeVar, cast

from ergon_core.core.providers.generation.model_resolution import resolve_model_target
from pydantic import BaseModel
from pydantic_ai import Agent

T = TypeVar("T", bound=BaseModel)


class JudgeMessage(BaseModel):
    model_config = {"frozen": True}

    role: Literal["system", "user", "assistant"]
    content: str


async def call_structured_judge(
    *,
    messages: Sequence[JudgeMessage],
    response_type: type[T],
    model: str | None,
) -> T:
    """Call an LLM and parse a structured judge response.

    This helper owns only provider mechanics: model resolution, pydantic-ai
    invocation, and output parsing. Benchmark criteria own the judge prompts,
    user-message formatting, and scoring policy.
    """

    resolved = resolve_model_target(model)
    instructions = "\n\n".join(message.content for message in messages if message.role == "system")
    prompt = "\n\n".join(
        f"{message.role.upper()}:\n{message.content}"
        for message in messages
        if message.role != "system"
    )
    agent = Agent(
        model=resolved.model,
        instructions=instructions or None,
        output_type=response_type,
    )
    result = await agent.run(prompt)
    return cast(T, result.output)

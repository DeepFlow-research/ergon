"""Shared LLM judge utility.

Thin wrapper around OpenAI structured output (beta.chat.completions.parse)
used by the criterion runtime when evaluating LLMJudgeCriterion instances.
"""

from typing import Any, TypeVar

from ergon_core.core.settings import settings
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

T = TypeVar("T", bound=BaseModel)


class LLMJudgeResponse(BaseModel):
    """Default structured response from an LLM judge call."""

    reasoning: str = Field(description="Detailed reasoning for the verdict")
    final_verdict: bool = Field(description="Pass/fail determination")


async def call_llm_judge(
    messages: list[dict[str, Any]],  # slopcop: ignore[no-typing-any]
    model: str = "gpt-4o",
    response_type: type[T] = LLMJudgeResponse,  # type: ignore[assignment]
) -> T:
    """Send *messages* to an OpenAI model and parse a structured response.

    Parameters
    ----------
    messages:
        Chat messages in the OpenAI format.
    model:
        Model identifier (default ``gpt-4o``).
    response_type:
        Pydantic model describing the expected structured output.

    Returns
    -------
    Parsed instance of *response_type*.
    """
    client = AsyncOpenAI(api_key=settings.openai_api_key)
    response = await client.beta.chat.completions.parse(
        model=model,
        messages=messages,
        response_format=response_type,
    )
    parsed = response.choices[0].message.parsed
    if parsed is None:
        raise ValueError("No parsed response from LLM judge")
    return parsed

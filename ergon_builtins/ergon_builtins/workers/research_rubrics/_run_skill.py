"""Skill runner for ResearchRubrics workers.

Constructs a pydantic-ai ``Agent`` per skill invocation with the requested
``response_model`` as the output type.  The agent receives a formatted prompt
containing the skill name and keyword arguments, and returns the parsed
structured output.

Why per-call Agent construction:
    Each skill call may request a different ``response_model`` (SearchResponse,
    QAResponse, ReportWriteResponse, etc.).  pydantic-ai's ``Agent`` requires
    ``output_type`` at construction time, so we cannot reuse a single agent
    across different response types.  The construction cost is negligible
    compared to the LLM round-trip.  If profiling reveals otherwise, a
    per-type agent cache can be added here without changing the public
    interface.
"""

import json
from collections.abc import Awaitable, Callable
from typing import TypeVar

from pydantic import BaseModel

_T = TypeVar("_T", bound=BaseModel)

RunSkillFn = Callable[..., Awaitable[_T]]  # type: ignore[type-arg]


def make_run_skill(
    *,
    model: str | None = None,
) -> RunSkillFn:  # type: ignore[type-arg]
    """Return an async callable ``(skill_name, response_model, **kwargs) -> T``.

    The callable constructs a pydantic-ai Agent with the given response_model
    as output_type, formats a prompt from the skill name and kwargs, and
    returns the parsed response.

    Parameters
    ----------
    model:
        Model identifier passed to ``resolve_model_target``.  Falls through
        to the default cloud model when None.
    """

    async def run_skill(
        skill_name: str,
        response_model: type[_T],
        **kwargs: object,
    ) -> _T:
        # reason: deferred to avoid import-time cost when module is merely imported
        from pydantic_ai import Agent

        # reason: deferred alongside pydantic_ai
        from ergon_core.core.providers.generation.model_resolution import (
            resolve_model_target,
        )

        resolved = resolve_model_target(model)

        agent: Agent[None, _T] = Agent(
            model=resolved.model,
            output_type=response_model,
        )

        prompt = _format_skill_prompt(skill_name, kwargs)
        result = await agent.run(prompt)
        return result.output

    return run_skill


def _format_skill_prompt(skill_name: str, kwargs: dict[str, object]) -> str:
    """Format a skill call into a prompt for the pydantic-ai Agent."""
    serialized = json.dumps(
        {k: str(v) for k, v in kwargs.items()},
        indent=2,
    )
    return (
        f"Execute the '{skill_name}' skill with the following parameters:\n\n"
        f"{serialized}\n\n"
        "Return a structured response matching the expected output schema."
    )

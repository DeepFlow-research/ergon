"""Skill runner for ResearchRubrics workers.

Constructs a pydantic-ai ``Agent`` per skill invocation with the requested
``response_model`` as the output type.  The agent receives a formatted prompt
containing the skill name and keyword arguments, and returns the parsed
structured output.

This is the *stub* skill runner: it asks the model to produce a plausible
response instead of calling real tools.  When the sandbox-backed handlers
land, this runner will be replaced by a dispatcher that forwards to the
actual skill implementation.

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
import logging
from collections.abc import Awaitable, Callable
from typing import TypeVar, get_args, get_origin, get_type_hints

from ergon_core.core.providers.generation.model_resolution import resolve_model_target
from pydantic import BaseModel
from pydantic_ai import Agent

logger = logging.getLogger(__name__)

_T = TypeVar("_T", bound=BaseModel)

RunSkillFn = Callable[..., Awaitable[_T]]  # type: ignore[type-arg]


def make_run_skill(
    *,
    model: str | None = None,
) -> RunSkillFn:  # type: ignore[type-arg]
    """Return an async callable ``(skill_name, response_model, **kwargs) -> T``.

    The callable constructs a pydantic-ai Agent with the given response_model
    as output_type, formats a prompt from the skill name and kwargs, and
    returns the parsed response.  If the Agent call raises, the exception is
    converted to a Failure variant of ``response_model`` when the union has
    one with ``kind == "failure"``; otherwise it is re-raised.

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
        resolved = resolve_model_target(model)

        agent: Agent[None, _T] = Agent(
            model=resolved.model,
            output_type=response_model,
        )

        prompt = _format_skill_prompt(skill_name, kwargs)
        try:
            result = await agent.run(prompt)
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            # LLM/transport errors are opaque; wrap into a Failure variant.
            logger.warning("run_skill(%s) failed: %s", skill_name, exc, exc_info=True)
            failure = _try_build_failure(response_model, kwargs, exc)
            if failure is not None:
                # Narrow: _try_build_failure returns a member of the
                # response_model union, so it is assignable to _T.
                return failure  # type: ignore[return-value]  # ty: ignore[invalid-return-type]
            raise
        return result.output

    return run_skill


def _format_skill_prompt(skill_name: str, kwargs: dict[str, object]) -> str:
    """Format a skill call into a prompt for the pydantic-ai Agent.

    Uses ``default=_json_default`` so BaseModel and other non-JSON-native
    values survive serialization without the ``str(v)`` mangling the previous
    version applied to everything.
    """
    serialized = json.dumps(kwargs, indent=2, default=_json_default)
    return (
        f"Execute the '{skill_name}' skill with the following parameters:\n\n"
        f"{serialized}\n\n"
        "Return a structured response matching the expected output schema."
    )


def _json_default(value: object) -> object:
    """Fallback serializer for ``json.dumps``.

    Pydantic models are dumped via ``model_dump`` so nested fields are
    preserved; everything else falls back to ``str``.
    """
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    return str(value)


# ---------------------------------------------------------------------------
# Failure construction -- used by ``run_skill`` when the Agent call raises.
# ---------------------------------------------------------------------------


def _try_build_failure(
    response_model: type[BaseModel],
    kwargs: dict[str, object],
    exc: BaseException,
) -> BaseModel | None:
    """Best-effort construction of a ``kind='failure'`` variant of ``response_model``.

    Returns ``None`` when the union has no failure member or when required
    fields cannot be satisfied from ``kwargs``.
    """
    failure_cls = _pick_failure_class(response_model)
    if failure_cls is None:
        return None

    try:
        hints = get_type_hints(failure_cls)
    except Exception:  # slopcop: ignore[no-broad-except]  pragma: no cover -- defensive
        return None

    init_kwargs: dict[str, object] = {
        "detail": f"{type(exc).__name__}: {exc}",
        "latency_ms": 0.0,
    }
    if "reason" in hints:
        init_kwargs["reason"] = "unknown"
    # Pass through any kwarg that matches a field name on the failure model
    # (query/question/url/path depending on which failure type we hit).
    for field_name in hints:
        if field_name in kwargs and field_name not in init_kwargs:
            init_kwargs[field_name] = kwargs[field_name]

    try:
        return failure_cls(**init_kwargs)
    except Exception:  # slopcop: ignore[no-broad-except]  pragma: no cover -- defensive
        return None


def _pick_failure_class(response_model: type) -> type[BaseModel] | None:
    """Return the union member whose ``kind`` literal equals ``'failure'``."""
    # response_model may be a single class or a typing.Union alias produced
    # by ``Success | Failure``.  ``get_args`` returns ``()`` for non-unions.
    candidates = get_args(response_model)
    pool: tuple[type, ...]
    if candidates:
        pool = tuple(c for c in candidates if isinstance(c, type))
    else:
        pool = (response_model,) if isinstance(response_model, type) else ()

    for cls in pool:
        if not isinstance(cls, type) or not issubclass(cls, BaseModel):
            continue
        kind_field = cls.model_fields.get("kind")
        if kind_field is None:
            continue
        # Literal type args live on the annotation.
        literal_args = get_args(kind_field.annotation)
        if "failure" in literal_args or kind_field.default == "failure":
            return cls
    return None

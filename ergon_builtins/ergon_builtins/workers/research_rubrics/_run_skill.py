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

import logging
from collections.abc import Awaitable
from types import UnionType
from typing import ClassVar, Literal, Protocol, cast, get_args, get_type_hints

from ergon_core.core.providers.generation.model_resolution import resolve_model_target
from pydantic import BaseModel
from pydantic_ai import Agent

from ergon_builtins.benchmarks.researchrubrics.toolkit_types import (
    DocumentResponse,
    QAResponse,
    ReportReadResponse,
    ReportWriteResponse,
    SearchResponse,
)

logger = logging.getLogger(__name__)

type ResponseModel = type[BaseModel] | UnionType


class ExaSearchSkillRequest(BaseModel):
    skill_name: Literal["exa_search"] = "exa_search"
    response_model: ClassVar[ResponseModel] = SearchResponse
    query: str
    num_results: int = 5

    model_config = {"frozen": True}


class ExaQASkillRequest(BaseModel):
    skill_name: Literal["exa_qa"] = "exa_qa"
    response_model: ClassVar[ResponseModel] = QAResponse
    question: str

    model_config = {"frozen": True}


class ExaGetContentSkillRequest(BaseModel):
    skill_name: Literal["exa_get_content"] = "exa_get_content"
    response_model: ClassVar[ResponseModel] = DocumentResponse
    url: str

    model_config = {"frozen": True}


class ReportWriteSkillRequest(BaseModel):
    skill_name: Literal["write_report_draft"] = "write_report_draft"
    response_model: ClassVar[ResponseModel] = ReportWriteResponse
    relative_path: str
    content: str

    model_config = {"frozen": True}


class ReportEditSkillRequest(BaseModel):
    skill_name: Literal["edit_report_draft"] = "edit_report_draft"
    response_model: ClassVar[ResponseModel] = ReportWriteResponse
    relative_path: str
    patch: str

    model_config = {"frozen": True}


class ReportReadSkillRequest(BaseModel):
    skill_name: Literal["read_report_draft"] = "read_report_draft"
    response_model: ClassVar[ResponseModel] = ReportReadResponse
    relative_path: str

    model_config = {"frozen": True}


type SkillRequest = (
    ExaSearchSkillRequest
    | ExaQASkillRequest
    | ExaGetContentSkillRequest
    | ReportWriteSkillRequest
    | ReportEditSkillRequest
    | ReportReadSkillRequest
)
type SkillResponse = (
    SearchResponse | QAResponse | DocumentResponse | ReportWriteResponse | ReportReadResponse
)


class RunSkillFn(Protocol):
    def __call__(self, request: SkillRequest) -> Awaitable[SkillResponse]: ...


def make_run_skill(
    *,
    model: str | None = None,
) -> RunSkillFn:
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

    async def run_skill(request: SkillRequest) -> SkillResponse:
        resolved = resolve_model_target(model)

        agent = Agent(
            model=resolved.model,
            output_type=request.response_model,
        )

        prompt = _format_skill_prompt(request)
        try:
            result = await agent.run(prompt)
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            # LLM/transport errors are opaque; wrap into a Failure variant.
            logger.warning("run_skill(%s) failed: %s", request.skill_name, exc, exc_info=True)
            failure = _try_build_failure(request, exc)
            if failure is not None:
                return cast(SkillResponse, failure)
            raise
        return cast(SkillResponse, result.output)

    return run_skill


def _format_skill_prompt(request: SkillRequest) -> str:
    """Format a skill call into a prompt for the pydantic-ai Agent.

    Request DTOs keep each skill's argument shape explicit while still giving
    the model a simple JSON object to condition on.
    """
    serialized = request.model_dump_json(indent=2)
    return (
        f"Execute the '{request.skill_name}' skill with the following parameters:\n\n"
        f"{serialized}\n\n"
        "Return a structured response matching the expected output schema."
    )


# ---------------------------------------------------------------------------
# Failure construction -- used by ``run_skill`` when the Agent call raises.
# ---------------------------------------------------------------------------


def _try_build_failure(
    request: SkillRequest,
    exc: BaseException,
) -> BaseModel | None:
    """Best-effort construction of a ``kind='failure'`` variant of ``response_model``.

    Returns ``None`` when the union has no failure member or when required
    fields cannot be satisfied from ``kwargs``.
    """
    failure_cls = _pick_failure_class(request.response_model)
    if failure_cls is None:
        return None

    try:
        hints = get_type_hints(failure_cls)
    except Exception:  # slopcop: ignore[no-broad-except]  pragma: no cover -- defensive
        return None

    init_kwargs = {
        "detail": f"{type(exc).__name__}: {exc}",
        "latency_ms": 0.0,
    }
    if "reason" in hints:
        init_kwargs["reason"] = "unknown"
    request_values = request.model_dump(mode="json")
    # Pass through any request field that matches a field name on the failure model
    # (query/question/url/path depending on which failure type we hit).
    for field_name in hints:
        if field_name in request_values and field_name not in init_kwargs:
            init_kwargs[field_name] = request_values[field_name]

    try:
        return failure_cls(**init_kwargs)
    except Exception:  # slopcop: ignore[no-broad-except]  pragma: no cover -- defensive
        return None


def _pick_failure_class(response_model: ResponseModel) -> type[BaseModel] | None:
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

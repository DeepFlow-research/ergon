"""Public runtime-facing evaluation context."""

from typing import Annotated, Any
from uuid import UUID

from ergon_core.api.criterion_runtime import CriterionRuntime
from ergon_core.api.results import WorkerOutput
from ergon_core.api.task_types import BenchmarkTask
from pydantic import BaseModel, ConfigDict, Field, SkipValidation


class EvaluationContext(BaseModel):
    """Thin evaluation context: sandbox identity + capabilities + task identity.

    Thin by design. Criteria own their data-pulling -- they connect to the
    sandbox via ``sandbox_id`` and pull what they need. The old pattern
    pre-collected resources, which broke agentic evaluators that need to
    explore freely.

    ``sandbox_id`` is the *identity* of the sandbox the worker used.  A
    criterion alone cannot do anything with it -- creating a client,
    running a command, or calling the LLM judge requires the sandbox
    manager and an OpenAI key.  Rather than giving every criterion its
    own handle on the provider stack, the executor wraps those
    capabilities in a ``CriterionRuntime`` and injects it here.  The
    runtime owns the sandbox lifecycle; the criterion just calls
    ``context.runtime.call_llm_judge(...)`` / ``execute_code(...)`` /
    etc.  Criteria that don't need the runtime simply ignore the field.
    """

    # ``CriterionRuntime`` is a ``typing.Protocol``.  Pydantic's synthesised
    # validator for Protocols is overly strict (isinstance checks that fail
    # for AsyncMocks etc.), and the field is never serialised, so we use
    # ``SkipValidation`` -- the type hint remains for static checkers and
    # editor autocompletion while runtime validation is bypassed.
    # ``arbitrary_types_allowed`` is still required for model construction.
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: UUID
    task: BenchmarkTask
    worker_result: WorkerOutput
    sandbox_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
    runtime: Annotated[CriterionRuntime | None, SkipValidation] = None

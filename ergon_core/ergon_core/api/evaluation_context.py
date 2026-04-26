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
    criterion alone cannot do anything with it -- creating a client or
    running a command requires the sandbox manager. Rather than giving
    every criterion its own handle on the sandbox provider stack, the
    executor wraps those capabilities in a ``CriterionRuntime`` and
    injects it here. The runtime owns the sandbox lifecycle; criteria
    that need sandbox evidence call methods like ``execute_code(...)``.
    LLM-as-judge criteria own their provider call and prompt policy
    outside this runtime.
    """

    # ``CriterionRuntime`` is a ``typing.Protocol``.  Pydantic's synthesised
    # validator for Protocols is overly strict (isinstance checks that fail
    # for AsyncMocks etc.), and the field is never serialised, so we use
    # ``SkipValidation`` -- the type hint remains for static checkers and
    # editor autocompletion while runtime validation is bypassed.
    # ``arbitrary_types_allowed`` is still required for model construction.
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    run_id: UUID
    task_id: UUID
    execution_id: UUID
    task: BenchmarkTask
    worker_result: WorkerOutput
    sandbox_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]
    runtime: Annotated[CriterionRuntime | None, SkipValidation] = None

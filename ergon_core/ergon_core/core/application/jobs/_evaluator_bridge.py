"""Picks the i-th evaluator for a task during the PR 4 → PR 5 window.

**Why this module exists.** The v2 final shape is
``evaluator = task.evaluators[i]`` — `Task` carries fully-constructed
`Evaluator` *instances* directly. That field lands in **PR 5**
(`06-pr-05-object-bound-api.md` Task 2). PR 4 is the PR before that:
`Task` still only carries `evaluator_binding_keys: tuple[str, ...]`
(opaque strings), so resolving an evaluator from an index requires a
multi-hop lookup. This module is the multi-hop lookup, kept in one
named place so it's grep-able and deletable.

**What the real shape will look like in PR 5:**

    evaluator = task.evaluators[payload.evaluator_index]

**What this module does today, between PR 4 and PR 5:**

    1. ``task.evaluator_binding_keys[i]`` → binding key (string)
    2. ``RunRecord.workflow_definition_id`` → definition id
    3. ``ExperimentDefinitionEvaluator`` row for
       ``(definition_id, binding_key)`` → ``evaluator_type`` slug +
       persistence id
    4. ``ComponentCatalogService.resolve_evaluator(slug)`` → class
    5. ``cls(name=binding_key)`` → live instance

Steps 1–5 collapse to one attribute access (`task.evaluators[i]`)
once PR 5 lands.

**Why a sibling module instead of inline.** PR 4's architecture
guard `test_evaluate_task_run_uses_thin_payload_and_run_tier_read`
checks the *body* of `evaluate_task_run.py` for definition-tier
identifiers (`DefinitionRepository`, `ComponentCatalogService`,
definition table classes). Keeping the multi-hop lookup in a sibling
file leaves the eval job body matching its v2 shape while preserving
the wiring needed to run today. PR 5 Task 4c § "Retire
`_evaluator_bridge.py`" deletes this file — `git rm` the module,
inline `task.evaluators[i]` at the one call site.
"""

from uuid import UUID

from ergon_core.api.benchmark import Task
from ergon_core.api.rubric import Evaluator
from ergon_core.core.application.components.catalog import ComponentCatalogService
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionEvaluator
from ergon_core.core.persistence.telemetry.models import RunRecord
from pydantic import BaseModel
from sqlmodel import Session, select


# TODO(PR 5): delete with the module; consumers read evaluator instance
# and binding metadata directly off `task.evaluators[i]`.
class BoundEvaluator(BaseModel):
    """The 4-tuple PR 4 needs from the multi-hop evaluator lookup.

    Holds the live ``Evaluator`` instance plus the persistence
    identifiers (``evaluator_id``, ``binding_key``, ``evaluator_type``)
    that ``RunTaskEvaluation`` rows need at insertion time. In v1 those
    identifiers were passed through the wire payload — that's the
    multi-field ``EvaluateTaskRunRequest`` PR 4 retired. Now that the
    wire payload is thin (`TaskEvaluateRequest`), the receiver has to
    *reconstruct* the same identifiers on its side; this DTO is what
    the bridge returns to the eval job.

    In PR 5 the eval body picks ``task.evaluators[i]`` directly and
    reads ``evaluator_id`` / ``binding_key`` from the Task snapshot,
    at which point this class goes away with the module.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    evaluator: Evaluator
    evaluator_id: UUID
    binding_key: str
    evaluator_type: str


# TODO(PR 5): delete with the module; the call site collapses to
# `evaluator = task.evaluators[payload.evaluator_index]`.
def resolve_evaluator(
    session: Session,
    *,
    run_id: UUID,
    task: Task,
    evaluator_index: int,
) -> BoundEvaluator:
    """PR 4-only multi-hop replacement for ``task.evaluators[i]``.

    Walks ``evaluator_binding_keys`` → ``ExperimentDefinitionEvaluator``
    → ``ComponentCatalogService.resolve_evaluator`` → instance, plus
    the persistence ids the legacy wire payload used to carry. PR 5's
    object-bound `Task.evaluators` makes every hop go away.

    Loud failure modes:

    - ``evaluator_index`` out of range for ``task.evaluator_binding_keys``
      → ``ContractViolationError`` (the orchestrator fanned out a stale
      index against a task whose binding list shrank between persistence
      and reload).
    - No ``ExperimentDefinitionEvaluator`` row for the picked binding
      key → ``ContractViolationError`` (the definition row was
      deleted out from under the running workflow).
    """

    bindings = task.evaluator_binding_keys
    if evaluator_index < 0 or evaluator_index >= len(bindings):
        raise ContractViolationError(
            f"evaluator_index {evaluator_index} out of range for task "
            f"{task.task_slug!r} (has {len(bindings)} evaluator bindings)",
            run_id=run_id,
            task_id=task.task_id,
        )
    binding_key = bindings[evaluator_index]

    run = session.get(RunRecord, run_id)
    if run is None:
        raise ContractViolationError(
            f"RunRecord {run_id} not found while resolving evaluator",
            run_id=run_id,
            task_id=task.task_id,
        )

    evaluator_def = session.exec(
        select(ExperimentDefinitionEvaluator).where(
            ExperimentDefinitionEvaluator.experiment_definition_id == run.workflow_definition_id,
            ExperimentDefinitionEvaluator.binding_key == binding_key,
        )
    ).first()
    if evaluator_def is None:
        raise ContractViolationError(
            f"No ExperimentDefinitionEvaluator for binding_key={binding_key!r} "
            f"under definition {run.workflow_definition_id}",
            run_id=run_id,
            task_id=task.task_id,
        )

    catalog = ComponentCatalogService()
    evaluator_cls = catalog.resolve_evaluator(session, evaluator_def.evaluator_type)
    return BoundEvaluator(
        evaluator=evaluator_cls(name=binding_key),
        evaluator_id=evaluator_def.id,
        binding_key=binding_key,
        evaluator_type=evaluator_def.evaluator_type,
    )

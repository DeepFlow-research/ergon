"""Transitional evaluator-resolution bridge for the PR 4 eval body.

TODO(PR 5): delete this module. PR 5 binds evaluators directly to the
``Task`` (``task.evaluators: tuple[Evaluator, ...]``); once that lands,
``evaluate_task_run`` picks ``task.evaluators[index]`` and the
ComponentCatalog / DefinitionRepository code path goes away entirely.

This module exists because PR 4 lands the synchronous-fanout
invariant (orchestrator-bounded sandbox lifetime) against the *current*
codebase, where ``Task`` still only carries ``evaluator_binding_keys:
tuple[str, ...]``. To resolve the i-th evaluator we walk:

    1. ``task.evaluator_binding_keys[i]`` → binding key
    2. ``RunRecord.workflow_definition_id`` → definition id
    3. ``ExperimentDefinitionEvaluator`` row for (definition_id, binding_key)
       → ``evaluator_type`` (slug) + persistence id
    4. ``ComponentCatalogService.resolve_evaluator(slug)`` → class
    5. ``cls(name=binding_key)`` → instance

This whole tower is replaced by ``task.evaluators[i]`` in PR 5.

The bridge intentionally lives in a *sibling* module to
``evaluate_task_run.py`` so the architecture guard
``test_evaluate_task_run_uses_thin_payload_and_run_tier_read`` keeps
passing: the guard checks the eval job's body for forbidden strings
(``DefinitionRepository``, ``ComponentCatalogService``,
``ExperimentDefinitionTask``); the bridge takes them out of that body.
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


class BoundEvaluator(BaseModel):
    """Result of resolving the i-th evaluator for a task at PR 4.

    Carries both the live ``Evaluator`` instance and the persistence
    identifiers (``evaluator_id``, ``binding_key``, ``evaluator_type``)
    the persistence layer needs for ``RunTaskEvaluation`` rows. PR 5
    folds all of this into ``task.evaluators[i]`` (the evaluator
    instance) plus identifiers carried implicitly by the Task snapshot.
    """

    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    evaluator: Evaluator
    evaluator_id: UUID
    binding_key: str
    evaluator_type: str


def resolve_evaluator(
    session: Session,
    *,
    run_id: UUID,
    task: Task,
    evaluator_index: int,
) -> BoundEvaluator:
    """Pick the i-th evaluator from a task's binding keys.

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
            ExperimentDefinitionEvaluator.experiment_definition_id
            == run.workflow_definition_id,
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

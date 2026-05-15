"""Legacy ``TaskSpec``-snapshot evaluator fallback for ``evaluate_task_run``.

**Why this module exists.** PR 5 made ``task.evaluators[i]`` the
canonical source for ``evaluate_task_run``: the evaluator comes from
the object-bound Task snapshot, not from a multi-hop registry lookup.
But the benchmark builtins (minif2f, swebench, researchrubrics,
gdpeval) and the test-owned smoke fixtures still return ``TaskSpec``
instances rather than object-bound ``Task`` instances at the head of
PR 5. ``TaskSpec`` snapshots have no inline evaluators, so on the
eval-worker side ``Task.from_definition`` reconstructs them with
``task.evaluators = ()``.

Retiring the v1 multi-hop bridge outright in PR 5 would break the
e2e smokes for every legacy benchmark — symmetric with the worker
side, which kept ``_legacy_worker_bridge`` exactly for this reason.
This sibling module is the narrow fallback: ``evaluate_task_run.py``'s
body reads ``task.evaluators`` first and only calls
``legacy_evaluator_from_binding`` when it sees an empty tuple.

**Deletion gate.** Each benchmark migration (PR 6 minif2f,
PR 10a swebench, PR 10b researchrubrics, PR 10c gdpeval — plus the
matching smoke fixtures) removes one benchmark from the legacy-shape
set. After PR 10c, no benchmark still produces ``TaskSpec`` — the
"must support" set is empty, and PR 11 deletes both this file and the
``if not task.evaluators:`` fallback branch in ``evaluate_task_run.py``.

The module name is grep-able so each migration PR can confirm
progress: ``rg _legacy_evaluator_bridge ergon_core ergon_builtins``.

**Architecture-guard relationship.** PR 5's
``test_evaluate_task_run_uses_object_bound_evaluators`` checks the
body of ``evaluate_task_run.py`` for forbidden strings. The body
imports this function under an ``if not task.evaluators:`` branch —
the definition-tier identifiers
(``ExperimentDefinitionEvaluator``, ``ComponentCatalogService``) live
here, not in the job body, so the guard stays clean.
"""

from uuid import UUID

from sqlmodel import Session, select

from ergon_core.api.criterion import CriterionContext as PublicCriterionContext
from ergon_core.api.registry import registry
from ergon_core.api.rubric import Evaluator
from ergon_core.core.application.components.catalog import ComponentCatalogService
from ergon_core.core.application.evaluation.criterion_runtime import (
    CriterionRuntimeOptions,
    DefaultCriterionRuntime,
)
from ergon_core.core.application.evaluation.models import (
    CriterionContext as InternalCriterionContext,
)
from ergon_core.core.infrastructure.inngest.errors import ContractViolationError
from ergon_core.core.persistence.definitions.models import ExperimentDefinitionEvaluator
from ergon_core.core.persistence.telemetry.models import RunRecord


# TODO(PR 11): delete this module + the matching `if not task.evaluators:`
# branch in evaluate_task_run.py. See module docstring for the deletion
# gate.
def legacy_evaluator_from_binding(
    session: Session,
    *,
    run_id: UUID,
    binding_key: str,
) -> Evaluator:
    """Reconstruct an ``Evaluator`` instance from the v1 multi-hop lookup.

    Only called by ``evaluate_task_run`` when ``task.evaluators`` is
    empty — i.e. when the snapshot came from a ``TaskSpec``-returning
    benchmark that hasn't been migrated yet.

    The lookup walks: ``run_id`` → ``RunRecord.workflow_definition_id``
    → ``ExperimentDefinitionEvaluator`` for
    ``(definition_id, binding_key)`` → ``evaluator_type`` slug
    → catalog → ``Evaluator`` class → ``cls(name=binding_key)``.

    Raises ``ContractViolationError`` when the run / binding row is
    missing — surfaces a misconfigured definition immediately rather
    than silently producing the wrong evaluator.
    """

    run = session.get(RunRecord, run_id)
    if run is None:
        raise ContractViolationError(
            f"RunRecord {run_id} not found while resolving legacy evaluator binding "
            f"{binding_key!r}",
            run_id=run_id,
        )
    definition_id = run.workflow_definition_id

    binding_row = session.exec(
        select(ExperimentDefinitionEvaluator).where(
            ExperimentDefinitionEvaluator.experiment_definition_id == definition_id,
            ExperimentDefinitionEvaluator.binding_key == binding_key,
        )
    ).first()
    if binding_row is None:
        raise ContractViolationError(
            f"No ExperimentDefinitionEvaluator for "
            f"definition_id={definition_id} binding_key={binding_key!r}",
            run_id=run_id,
        )

    catalog = ComponentCatalogService()
    evaluator_cls = catalog.resolve_evaluator(session, binding_row.evaluator_type)
    return evaluator_cls(name=binding_key)


# TODO(PR 11): delete with the rest of this module.
def legacy_inject_criterion_runtime(
    *,
    public_context: PublicCriterionContext,
    benchmark_type: str,
    run_id: UUID,
    task_id: UUID,
    sandbox_id: str | None,
) -> PublicCriterionContext:
    """Construct a ``CriterionRuntime`` and attach it to ``public_context``.

    Mirrors what ``InngestCriterionExecutor`` did pre-PR-5 for the v1
    eval path. The new object-bound path attaches a runtime via
    ``Task.from_definition(sandbox_id=...)`` (which sets
    ``task.sandbox._runtime``), but legacy ``TaskSpec`` snapshots have
    no ``task.sandbox`` to attach to. We synthesise a runtime here so
    criteria that call ``context.run_command(...)`` /
    ``context.ensure_sandbox(...)`` keep working until the matching
    benchmark migration lands.

    Returns a new ``CriterionContext`` with ``_runtime`` set; the
    original instance is frozen and cannot be mutated.
    """
    sandbox_manager_cls = registry.sandbox_managers[benchmark_type]
    sandbox_manager = sandbox_manager_cls()
    internal_ctx = InternalCriterionContext(
        run_id=run_id,
        task_input="",
        agent_reasoning=None,
    )
    runtime = DefaultCriterionRuntime(
        context=internal_ctx,
        sandbox_manager=sandbox_manager,
        options=CriterionRuntimeOptions(
            run_id=run_id,
            task_id=task_id,
            sandbox_id=sandbox_id,
        ),
    )
    return PublicCriterionContext.with_runtime(
        runtime=runtime,
        run_id=public_context.run_id,
        task_id=public_context.task_id,
        execution_id=public_context.execution_id,
        task=public_context.task,
        worker_result=public_context.worker_result,
        sandbox_id=public_context.sandbox_id,
        metadata=dict(public_context.metadata),
    )

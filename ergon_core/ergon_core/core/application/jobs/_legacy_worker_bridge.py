"""Legacy ``TaskSpec``-snapshot worker fallback for ``worker_execute``.

**Why this module exists.** PR 5 made ``task.worker`` the canonical
source for ``worker_execute``: the worker comes from the object-bound
Task snapshot, not from a registry lookup. But the benchmark builtins
(minif2f, swebench, researchrubrics, gdpeval) still return ``TaskSpec``
instances rather than object-bound ``Task`` instances at the head of
PR 5. ``TaskSpec`` snapshots have no inline worker, so on the
eval-worker side ``Task.from_definition`` reconstructs them with
``task.worker = None``.

Retiring the v1 registry-slug bridge outright in PR 5 would break the
e2e smokes for every legacy benchmark. This sibling module is the
narrow fallback: ``worker_execute.py``'s body reads ``task.worker``
first and only calls ``legacy_worker_from_payload`` when it sees None.

**Deletion gate.** Each benchmark migration (PR 6 minif2f,
PR 10a swebench, PR 10b researchrubrics, PR 10c gdpeval) removes one
benchmark from the legacy-shape set. After PR 10c, no benchmark still
produces ``TaskSpec`` — the "must support" set is empty, and PR 11
(see plan ``12-pr-11-deletion-final-schema.md`` Task 1.5) deletes both
this file and the ``if worker is None:`` fallback branch in
``worker_execute.py``.

The module name is grep-able so each migration PR can confirm
progress: ``rg _legacy_worker_bridge ergon_core ergon_builtins``.

**Architecture-guard relationship.** PR 5's
``test_worker_execute_uses_object_bound_worker`` checks the body of
``worker_execute.py`` for forbidden strings. The body imports this
function under an ``if worker is None:`` branch — the
``ComponentCatalogService`` reference lives here, not in the job body,
so the guard stays clean.
"""

from ergon_core.api.worker.worker import Worker
from ergon_core.core.application.components.catalog import ComponentCatalogService
from ergon_core.core.application.jobs.models import WorkerExecuteJobRequest
from ergon_core.core.persistence.shared.db import get_session


# TODO(PR 11): delete this module. PR 11 Task 1.5 owns the deletion +
# the matching `if worker is None:` branch in worker_execute.py.
def legacy_worker_from_payload(payload: WorkerExecuteJobRequest) -> Worker:
    """Reconstruct a Worker from the v1 registry-slug payload fields.

    Only called by ``worker_execute`` when ``task.worker is None`` —
    i.e. when the snapshot came from a ``TaskSpec``-returning
    benchmark that hasn't been migrated yet. Walks the catalog the
    same way the pre-PR-5 in-body bridge did.

    Raises whatever ``ComponentCatalogService.build_worker`` raises
    (typically ``ValueError`` for an unknown slug, or
    ``ConfigurationError`` upstream). The loud failure is desirable —
    it surfaces an unmigrated benchmark immediately rather than
    silently producing a Worker with the wrong shape.
    """

    catalog = ComponentCatalogService()
    with get_session() as session:
        return catalog.build_worker(
            session,
            slug=payload.worker_type,
            name=payload.assigned_worker_slug,
            model=payload.model_target,
        )

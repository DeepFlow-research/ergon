"""Public ``Experiment`` authoring object.

The v2 authoring shape — what a benchmark author actually writes when
declaring an experiment. Holds the benchmark plus first-class
authoring metadata (``name`` / ``description`` / ``created_by``) and
a free-form ``metadata`` dict for opaque author tags. Anything the
framework reads (dashboard listing, audit, denormalised indexed
columns) goes in a named field, not in ``metadata``.

Compared to v1's domain ``Experiment`` (which still lives under
``core.domain.experiments``), this class:

- Does NOT carry separate ``workers`` / ``evaluators`` / ``assignments``
  maps. v2 binds workers/sandbox/evaluators directly on ``Task``
  instances returned by ``Benchmark.build_instances()``.
- Carries a ``_persisted`` ``PrivateAttr`` that
  ``application/experiments/definition_writer.persist_definition``
  populates so callers can chain ``Experiment(...).persist(...)``-style
  fluent flows in PR 7. PR 5 doesn't expose that public surface yet —
  the field is just plumbed.

Sandbox-compatibility validation runs at construction time so a
benchmark/worker mismatch fails *before* a definition row is written,
not at the next worker_execute call when the eval worker tries to
attach to the wrong shape of sandbox.
"""

from typing import TYPE_CHECKING, Any
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_validator

from ergon_core.api.benchmark import Benchmark, Task
from ergon_core.api.errors import SandboxKindMismatch

if TYPE_CHECKING:
    from ergon_core.core.domain.experiments.handles import DefinitionHandle


class Experiment(BaseModel):
    """v2 public experiment authoring object."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    benchmark: Benchmark
    name: str | None = None
    description: str | None = None
    # First-class authoring-metadata field. Anything the framework reads
    # (dashboard listing, audit, indexed columns) lives here. The opaque
    # ``metadata`` dict below is for author-provided tags only.
    created_by: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    _persisted: "DefinitionHandle | None" = PrivateAttr(default=None)

    @model_validator(mode="after")
    def _validate_sandbox_compatibility(self) -> "Experiment":
        """Reject experiments where a task's worker requires a sandbox
        the bound ``task.sandbox`` doesn't satisfy.

        Only checks object-bound ``Task`` instances — legacy
        ``TaskSpec`` benchmarks have no inline worker/sandbox to
        validate. PR 11 makes ``Task`` the only shape and drops the
        ``isinstance(task, Task)`` branch.
        """

        for tasks in self.benchmark.build_instances().values():
            for task in tasks:
                if not isinstance(task, Task):
                    continue
                if task.worker is None or task.sandbox is None:
                    continue
                required = type(task.worker).requires_sandbox
                if not isinstance(task.sandbox, required):
                    raise SandboxKindMismatch(
                        # Tasks at construction time don't have stable
                        # ids — Task.task_id raises until
                        # ``Task.from_definition`` binds it. A fresh
                        # uuid4 is enough to identify which task in
                        # the error context.
                        task_id=task._task_id if task._task_id else uuid4(),
                        component=type(task.worker).__name__,
                        required=required,
                        actual=type(task.sandbox),
                    )
        return self

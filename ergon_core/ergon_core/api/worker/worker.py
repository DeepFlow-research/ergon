"""Public ``Worker`` ABC (Pydantic BaseModel) for v2 object-bound benchmarks."""

from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator, Callable
from typing import TYPE_CHECKING, Any, ClassVar, cast

from pydantic import BaseModel, ConfigDict, Field, model_serializer

from ergon_core.api._serialization import TaskDefinitionJson, import_component_subclass
from ergon_core.api.benchmark.task import Task
from ergon_core.api.errors import DependencyError
from ergon_core.api.sandbox.sandbox import Sandbox
from ergon_core.api.worker.context import WorkerContext
from ergon_core.api.worker.results import WorkerOutput
from ergon_core.core.domain.generation.context_parts import ContextPartChunk
from ergon_core.core.infrastructure.dependencies import check_packages

WorkerStreamItem = ContextPartChunk | WorkerOutput


class Worker(BaseModel, ABC):
    """Base class for all workers. Pydantic-serializable.

    PR 5 converts the v1 hand-rolled ABC to a Pydantic ``BaseModel``
    so workers can be round-tripped through ``task_json`` snapshots
    alongside ``Task`` and ``Sandbox``. Concrete subclasses declare
    config fields directly on the model.

    ``type_slug`` / ``required_packages`` / ``install_hint`` /
    ``requires_sandbox`` are ``ClassVar``s on the subclass — Pydantic
    leaves ``ClassVar`` alone, so they don't become serialized fields.
    """

    # ``extra="allow"`` lets subclasses keep their hand-rolled
    # ``__init__`` patterns from before PR 5 (e.g. ``ReActWorker``'s
    # tools/system_prompt/max_iterations kwargs). Those flow into
    # ``__pydantic_extra__`` and round-trip through ``model_dump`` /
    # ``model_validate`` like any other field. PR 11 will tighten this
    # to ``extra="forbid"`` once every subclass has been migrated to
    # explicit field declarations.
    model_config = ConfigDict(
        arbitrary_types_allowed=True,
        frozen=False,
        extra="allow",
    )

    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""
    # The Sandbox subclass a Worker requires. Default is the base
    # ``Sandbox`` (accepts any kind); concrete subclasses narrow
    # (e.g. ``LeanReActWorker.requires_sandbox = LeanSandbox``).
    # Validated at ``Experiment`` construction time — see
    # ``api/experiment.py:_validate_sandbox_compatibility``.
    requires_sandbox: ClassVar[type[Sandbox]] = Sandbox

    name: str
    # `model` is required (no default) — defaults hide sizing decisions
    # per RFC 2026-04-22. Subclasses that want a fixed model should set
    # it on the subclass, not on the base.
    model: str | None  # TODO: make not | None
    metadata: dict[str, Any] = Field(default_factory=dict)  # slopcop: ignore[no-typing-any]

    @abstractmethod
    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        """Run the worker, yielding context chunks and a terminal ``WorkerOutput``."""
        raise NotImplementedError

    @classmethod
    def from_definition(cls, worker_json: TaskDefinitionJson) -> "Worker":
        """Reconstruct a Worker subclass from ``_type``-discriminated JSON."""

        worker_type = worker_json.get("_type")
        if not isinstance(worker_type, str):
            raise ValueError(
                f"Worker snapshot is missing the required `_type` discriminator "
                f"(got {type(worker_type).__name__}). Every persisted worker must "
                f"carry `_type`."
            )
        WorkerCls = import_component_subclass(worker_type, Worker, kind="Worker")
        return cast("Worker", WorkerCls.model_validate(worker_json))

    def validate_runtime_deps(self) -> None:
        """Check that runtime dependencies are available.

        Renamed from ``validate`` because Pydantic v2 reserves
        ``validate`` on ``BaseModel`` for input-validation. Renaming
        also makes the intent (check importable packages) explicit at
        every call site.
        """
        errors = check_packages(
            self.required_packages,
            f"Worker '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))

    # TODO: I'd quite like to find some way to kill these serializer methods, they are a bit of a hack and dont really fit in with the rest of the api
    @model_serializer(mode="wrap")
    def _serialize_with_type_discriminator(
        self,
        handler: Callable[["Worker"], dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Inject the ``_type`` discriminator on every dump.

        Worker subclasses dump as ``{..., "_type": "module:Qualname"}``
        so ``from_definition`` can re-resolve the concrete class from
        the JSON without external metadata.
        """
        payload = handler(self)
        payload["_type"] = f"{type(self).__module__}:{type(self).__qualname__}"
        toolkit = getattr(self, "toolkit", None)
        if toolkit is not None:
            from ergon_core.api.toolkit import Toolkit

            if isinstance(toolkit, Toolkit):
                payload["toolkit"] = toolkit.model_dump(mode="json")
        return payload

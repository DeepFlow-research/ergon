"""Public ``Sandbox`` ABC for v2 object-bound benchmarks.

A ``Sandbox`` subclass is a Pydantic ``BaseModel`` that carries the
*config* fields a sandbox author wants (template name, env vars,
timeout) and — once provisioned or attached — holds a live
``SandboxRuntime`` on its private ``_runtime`` slot. The public API
proxies IO (``run_command``, ``write_file``, ``read_file``,
``list_files``) to the runtime; criteria call those directly off
``context.task.sandbox`` rather than reaching into a separate
``CriterionRuntime`` object.

Lifecycle verbs:

- ``provision()`` — author-implemented. Acquire a fresh external
  sandbox and attach ``_runtime`` to it.
- ``_bind_runtime(sandbox_id)`` — author-implemented. Re-attach
  ``_runtime`` to an *existing* external sandbox by id (e.g. e2b's
  ``AsyncSandbox.connect(sandbox_id)``). Used on the eval-worker side
  via ``Sandbox.from_definition(json, sandbox_id=...)``.
- ``terminate()`` — framework-provided. Terminate the external sandbox
  AND drop the local handle. Called only by the orchestrator.
- ``detach()`` — framework-provided. Drop the local handle but leave
  the external sandbox running. Called by eval workers after
  evaluation completes.

Both ``terminate`` and ``detach`` raise ``SandboxNotLiveError`` if
called on a sandbox with no live runtime. That's deliberate: the v1
audit found double-release / release-before-acquire bugs hidden behind
silent no-ops, and the loud failure mode is what shifted lifecycle
bugs from production retry-replay traces to unit tests.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import cast

from pydantic import BaseModel, Field, PrivateAttr

from ergon_core.api._serialization import TaskDefinitionJson, import_component
from ergon_core.api.errors import SandboxNotLiveError
from ergon_core.api.sandbox.runtime import CommandResult, SandboxRuntime


class Sandbox(BaseModel, ABC):
    """Base class for benchmark-authored sandbox specifications."""

    model_config = {"frozen": False, "arbitrary_types_allowed": True}

    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"

    _runtime: SandboxRuntime | None = PrivateAttr(default=None)

    # ── Author-implemented lifecycle hooks ─────────────────────────────

    @abstractmethod
    async def provision(self) -> None:
        """Acquire a fresh external sandbox and attach ``_runtime``.

        Called by the orchestrator (``execute_task``) before the worker
        runs. The implementation is responsible for creating the
        external sandbox, applying ``env`` / ``timeout_seconds`` /
        ``requires_network``, and setting ``_runtime`` on ``self``.
        """

    @abstractmethod
    async def _bind_runtime(self, sandbox_id: str) -> None:
        """Re-attach ``_runtime`` to an EXISTING external sandbox by id.

        Called by ``Sandbox.from_definition`` when a ``sandbox_id`` is
        passed. Authors implement this to connect to an already-running
        sandbox (e.g. ``AsyncSandbox.connect(sandbox_id)``) rather than
        provision a new one.
        """

    # ── Framework-provided lifecycle ───────────────────────────────────

    @classmethod
    async def from_definition(
        cls,
        sandbox_json: TaskDefinitionJson,
        *,
        sandbox_id: str | None = None,
    ) -> "Sandbox":
        """Inflate a Sandbox subclass from ``_type``-discriminated JSON.

        - ``sandbox_id is None`` → config-only sandbox; ``_runtime``
          stays ``None``. The caller can later ``await provision()`` to
          go live, or pass to authors who only need config (static
          benchmark loaders, planners).
        - ``sandbox_id is not None`` → returned instance is fully live;
          callers can immediately use ``run_command`` / ``write_file``
          / etc.
        """

        sandbox_type = sandbox_json.get("_type")
        if not isinstance(sandbox_type, str):
            raise ValueError(
                f"Sandbox snapshot is missing the required `_type` discriminator "
                f"(got {type(sandbox_type).__name__}). Every persisted sandbox "
                f"must carry `_type`."
            )
        SandboxCls = import_component(sandbox_type)
        instance = cast("Sandbox", SandboxCls.model_validate(sandbox_json))
        if sandbox_id is not None:
            await instance._bind_runtime(sandbox_id)
        return instance

    async def terminate(self) -> None:
        """Terminate the EXTERNAL sandbox AND drop the local handle.

        Called only by the orchestrator. Raises ``SandboxNotLiveError``
        if called twice or before ``provision()`` — both are lifecycle
        bugs the v1 audit was designed to surface.
        """
        if self._runtime is None:
            raise SandboxNotLiveError(
                f"{type(self).__name__}.terminate() called on a sandbox with no live "
                "runtime. Likely double-terminate or terminate-before-acquire — "
                "both are lifecycle bugs."
            )
        await self._runtime.close()
        object.__setattr__(self, "_runtime", None)

    async def detach(self) -> None:
        """Drop the local handle; DO NOT terminate the external sandbox.

        Called by eval workers after evaluation completes — the
        external sandbox keeps running so sibling eval workers and the
        orchestrator's final terminate can still access it. Raises
        ``SandboxNotLiveError`` if called on a sandbox with no live
        runtime; eval workers always attach before they detach, so a
        bare detach is a programming error worth surfacing.
        """
        if self._runtime is None:
            raise SandboxNotLiveError(
                f"{type(self).__name__}.detach() called on a sandbox with no live "
                "runtime. Eval workers must attach before detaching — see "
                "Sandbox.from_definition(sandbox_id=...)."
            )
        await self._runtime.close_local()
        object.__setattr__(self, "_runtime", None)

    @property
    def is_live(self) -> bool:
        """``True`` iff ``_runtime`` is attached."""
        return self._runtime is not None

    @property
    def sandbox_id(self) -> str:
        """Live runtime's external sandbox id. Raises on a config-only sandbox."""
        return self._require_runtime().sandbox_id

    # ── IO proxy methods ───────────────────────────────────────────────

    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        """Run a shell command in the external sandbox.

        ``timeout`` defaults to ``self.timeout_seconds`` so the v1-audit
        regression (evaluators issuing commands with no timeout) can't
        recur silently — the sandbox spec is the source of truth.
        """
        runtime = self._require_runtime()
        effective_timeout = timeout if timeout is not None else self.timeout_seconds
        return await runtime.run_command(cmd, timeout=effective_timeout)

    async def write_file(self, path: str, content: bytes | str) -> None:
        """Write a file to the external sandbox. ``str`` content is utf-8 encoded."""
        runtime = self._require_runtime()
        payload = content.encode() if isinstance(content, str) else content
        await runtime.write_file(path, payload)

    async def read_file(self, path: str) -> bytes:
        runtime = self._require_runtime()
        return await runtime.read_file(path)

    async def list_files(self, path: str | None = None) -> list[str]:
        """List files at ``path`` (defaults to ``self.output_path``)."""
        runtime = self._require_runtime()
        return await runtime.list_files(path or self.output_path)

    # ── Internal ───────────────────────────────────────────────────────

    def _require_runtime(self) -> SandboxRuntime:
        if self._runtime is None:
            raise SandboxNotLiveError(
                f"{type(self).__name__} has no live runtime. Construct via "
                "Sandbox.from_definition(json, sandbox_id=...) or call "
                "provision() first."
            )
        return self._runtime

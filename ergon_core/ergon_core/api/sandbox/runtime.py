"""Public ``SandboxRuntime`` Protocol.

The Protocol is what concrete sandbox backends (e2b, local docker, the
test stub) must satisfy so a v2 ``Sandbox`` can hold one as its private
``_runtime``. The Protocol intentionally splits ``close()`` (terminate
the external sandbox AND drop the local handle) from ``close_local()``
(drop only the local handle) — the lifecycle invariant from PR 4
(orchestrator terminates external, eval workers only detach locally)
needs both verbs to exist on the Protocol.

``CommandResult`` (the return type of ``run_command``) lives in
``core/application/evaluation/protocols.py`` to avoid cycles between
the public API and the evaluation service; the ``api/sandbox`` package
re-exports it from there.
"""

from collections.abc import Sequence
from typing import Protocol

from ergon_core.core.application.evaluation.protocols import CommandResult


class SandboxRuntime(Protocol):
    """Lifecycle + IO surface a ``Sandbox`` holds onto when it's live.

    Concrete implementations: ``ManagerBackedSandboxRuntime`` (production,
    backed by ``BaseSandboxManager`` + an e2b ``AsyncSandbox``) and the
    in-process test stub in ``ergon_core/test_support/sandbox/``.
    """

    sandbox_id: str

    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult: ...

    async def write_file(self, path: str, content: bytes) -> None: ...

    async def read_file(self, path: str) -> bytes: ...

    async def list_files(self, path: str) -> list[str]: ...

    async def close(self) -> None:
        """Terminate the external sandbox AND close the local handle.

        Called by lifecycle owners (the orchestrator) when an external
        sandbox should be torn down for good. Implementations call the
        backing manager's terminate-by-id and release any local IO
        resources (gRPC streams, TCP connections).
        """
        ...

    async def close_local(self) -> None:
        """Close the local handle only; leave the external sandbox alive.

        Called by eval workers after evaluation completes, so the
        external sandbox keeps running for sibling eval workers and the
        orchestrator's final terminate. Implementations close the local
        SDK connection but skip the manager's terminate-by-id call.
        """
        ...

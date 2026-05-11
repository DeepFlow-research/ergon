"""Default concrete implementation of ``CriterionRuntime``."""

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import UUID

from e2b import SandboxNotFoundException, TimeoutException
from ergon_core.core.application.evaluation.protocols import (
    CommandResult,
    SandboxResult,
)
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.infrastructure.sandbox.event_sink import (
    NoopSandboxEventSink,
    SandboxEventSink,
)
from ergon_core.core.application.evaluation.models import CriterionContext
from ergon_core.core.application.resources import RunResourceView
from pydantic import BaseModel, ConfigDict
from sqlmodel import Session, desc, select
from ergon_core.core.application.evaluation.errors import ResourceNotFoundError

if TYPE_CHECKING:
    from ergon_core.core.infrastructure.sandbox.manager import AsyncSandbox, BaseSandboxManager

logger = logging.getLogger(__name__)



class CriterionRuntimeOptions(BaseModel):
    """Optional runtime context for criterion execution."""

    model_config = ConfigDict(arbitrary_types_allowed=True, frozen=True)

    run_id: UUID | None = None
    task_id: UUID | None = None
    sandbox_id: str | None = None
    event_sink: SandboxEventSink | None = None


class DefaultCriterionRuntime:
    """Real criterion runtime backed by sandbox manager + OpenAI + DB.

    Parameters
    ----------
    context:
        ``CriterionContext`` passed by the executor.  ``context.run_id`` is
        the default ``run_id`` for resource and DB queries if ``run_id`` is
        not provided explicitly.
    sandbox_manager:
        The ``BaseSandboxManager`` that owns the task sandbox.
    run_id:
        Explicit run UUID for resource/DB scoping.  Defaults to
        ``context.run_id`` if ``None``.
    task_id:
        Task UUID used in trace attributes; optional.
    sandbox_id:
        E2B sandbox ID of the task's live sandbox, when known.  If
        provided, ``ensure_sandbox`` prefers attaching via
        ``manager.reconnect(sandbox_id)`` over constructing a fresh
        sandbox — the blessed cross-process path per RFC
        ``2026-04-17-sandbox-lifetime-covers-criteria``.
    event_sink:
        Pre-constructed ``SandboxEventSink``.  If ``None`` a
        ``NoopSandboxEventSink`` is used.
    """

    def __init__(
        self,
        context: CriterionContext,
        sandbox_manager: "BaseSandboxManager",
        options: CriterionRuntimeOptions | None = None,
    ) -> None:
        runtime_options = CriterionRuntimeOptions() if options is None else options
        self.context = context
        self.sandbox_manager: "BaseSandboxManager" = sandbox_manager
        self._run_id: UUID = (
            runtime_options.run_id if runtime_options.run_id is not None else context.run_id
        )
        self._task_id: UUID | None = runtime_options.task_id
        self._sandbox_id: str | None = runtime_options.sandbox_id
        self._reconnected_sandbox: "AsyncSandbox | None" = None
        self._owns_sandbox = False
        self._event_sink: SandboxEventSink = (
            NoopSandboxEventSink()
            if runtime_options.event_sink is None
            else runtime_options.event_sink
        )

    # ── sandbox lifecycle ─────────────────────────────────────────────

    async def ensure_sandbox(self) -> None:
        """Attach to the task's sandbox if possible; else create one.

        Resolution order:

        1. **In-process cache** — ``sandbox_manager.get_sandbox(run_id)``.
           Used when the criterion runs in the same process as the task
           worker (class-level ``_sandboxes`` dict is shared).
        2. **Cross-process reconnect** — if a ``sandbox_id`` was passed
           in, call ``sandbox_manager.reconnect(sandbox_id)`` to attach
           to the still-live task sandbox.  RFC
           ``sandbox-lifetime-covers-criteria`` guarantees it's alive
           through criterion execution.  Does NOT populate the
           in-process ``_sandboxes`` dict; the handle is retained on
           ``self._reconnected_sandbox``.
        3. **Fresh creation** — only when both of the above are absent.
           This is a last-resort fallback for criteria with no task
           sandbox to attach to.  Sets ``_owns_sandbox = True`` so
           ``cleanup`` tears it down.

        ``SandboxExpiredError`` from reconnect is re-raised as-is so the
        caller (``check_evaluators`` fan-out) can surface a
        ``"sandbox-expired"`` evaluation outcome distinct from a
        generic failure.
        """
        # 1. In-process cache
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is not None:
            await self.sandbox_manager.reset_timeout(self._run_id, timeout_minutes=30)
            return

        # 2. Cross-process reconnect via the manager.  Raises
        #    SandboxExpiredError if the task sandbox is already gone;
        #    the caller translates that to a benign evaluation outcome.
        if self._sandbox_id:
            self._reconnected_sandbox = await self.sandbox_manager.reconnect(
                self._sandbox_id,
            )
            return

        # 3. Last resort: create a fresh sandbox (criterion owns it).
        await self.sandbox_manager.create(
            self._run_id,
            run_id=self._run_id,
            timeout_minutes=30,
        )
        self._owns_sandbox = True

    def _current_sandbox(self) -> "AsyncSandbox | None":
        """Return the currently-attached sandbox handle.

        Prefers the in-process ``_sandboxes`` entry (populated by
        ``create``); falls back to the reconnected handle when we
        attached via cross-process ``reconnect``.
        """
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is not None:
            return sandbox
        return self._reconnected_sandbox

    async def upload_files(self, files: list[dict]) -> None:
        sandbox = self._current_sandbox()
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        for resource in files:
            name = resource.get("name", "unknown")
            sandbox_path = f"/evaluation/{name}"
            content = resource.get("content", b"")
            if isinstance(content, str):
                content = content.encode("utf-8")
            # Propagate upload failures: a criterion that quietly proceeds
            # against missing inputs would silently produce wrong scores.
            await sandbox.files.write(sandbox_path, content)

    async def write_file(self, path: str, content: bytes) -> None:
        sandbox = self._current_sandbox()
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.files.write(path, content)

    async def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        sandbox = self._current_sandbox()
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        # Intentionally NOT wrapping in try/except: a sandbox exception
        # (timeout, killed, network) is not the same as the command exiting
        # non-zero. Propagate so criteria see real infra failures distinctly
        # from program-level exit codes.
        result = await sandbox.commands.run(command, timeout=timeout)
        return CommandResult(
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=result.exit_code,
        )

    async def execute_code(self, code: str) -> SandboxResult:
        sandbox = self._current_sandbox()
        if sandbox is None:
            raise RuntimeError("Sandbox not created")
        # Wrap concrete sandbox-side timeout / not-found errors with a
        # useful message; anything else propagates so unrelated bugs do not
        # get silently reclassified as timeouts.
        try:
            execution = await sandbox.run_code(code, language="python", timeout=30)
        except (TimeoutException, SandboxNotFoundException) as exc:
            raise RuntimeError(
                f"Sandbox execution failed (likely timeout): {exc}. "
                "Code criterion may have taken too long (>30s)."
            ) from exc
        return SandboxResult(
            stdout=list(execution.logs.stdout),
            stderr=list(execution.logs.stderr),
        )

    async def cleanup(self) -> None:
        if self._owns_sandbox:
            await self.sandbox_manager.terminate(self._run_id)
            self._owns_sandbox = False

    # ── resource I/O ──────────────────────────────────────────────────

    async def read_resource(self, name: str) -> bytes:
        """Read the latest worker-published blob for ``name`` in this run.

        Queries ``run_resources`` for the most-recently-created row matching
        ``(run_id, name)``, then reads bytes from ``file_path`` on disk.

        Raises
        ------
        ResourceNotFoundError
            No ``run_resources`` row matches ``(run_id, name)``.
        OSError
            The blob file is missing or unreadable.
        """
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(RunResource.run_id == self._run_id)
                .where(RunResource.name == name)
                .order_by(desc(RunResource.created_at))
                .limit(1)
            )
            row = session.exec(stmt).first()

        if row is None:
            raise ResourceNotFoundError(f"No run_resource named {name!r} for run {self._run_id}")

        result = Path(row.file_path).read_bytes()
        logger.info(
            "criterion read_resource run_id=%s name=%s size_bytes=%d",
            self._run_id,
            name,
            len(result),
        )
        return result

    async def read_resource_by_id(self, resource_id: UUID) -> bytes:
        """Read one worker-published blob by its RunResource primary key."""
        with get_session() as session:
            row = session.get(RunResource, resource_id)

        if row is None or row.run_id != self._run_id:
            raise ResourceNotFoundError(f"No run_resource {resource_id!s} for run {self._run_id}")

        result = Path(row.file_path).read_bytes()
        logger.info(
            "criterion read_resource_by_id run_id=%s resource_id=%s size_bytes=%d",
            self._run_id,
            resource_id,
            len(result),
        )
        return result

    async def list_resources(
        self,
        task_execution_id: UUID | None = None,
    ) -> list[RunResourceView]:
        """Return resource DTOs for this run, newest first.

        Defaults to this runtime's evaluated task execution. Passing
        ``task_execution_id`` lets a benchmark criterion inspect a related task
        explicitly without core knowing benchmark semantics.
        """
        effective_execution_id = (
            task_execution_id if task_execution_id is not None else self._task_id
        )
        with get_session() as session:
            stmt = select(RunResource).where(RunResource.run_id == self._run_id)
            if effective_execution_id is not None:
                stmt = stmt.where(RunResource.task_execution_id == effective_execution_id)
            stmt = stmt.order_by(desc(RunResource.created_at))
            rows = list(session.exec(stmt).all())
        return [RunResourceView.from_row(r) for r in rows]

    async def get_all_files_for_task(self) -> dict[str, bytes]:
        """See ``CriterionRuntime.get_all_files_for_task``.

        Returns ``{}`` when this runtime has no ``task_id`` scope.  For
        scoped calls, queries ``run_resources`` filtered by
        ``(run_id, task_execution_id)``, dedups by ``name`` keeping the
        newest, and materializes each ``file_path`` into bytes.
        """
        if self._task_id is None:
            return {}
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(RunResource.run_id == self._run_id)
                .where(RunResource.task_execution_id == self._task_id)
                .order_by(desc(RunResource.created_at))
            )
            rows = list(session.exec(stmt).all())

        seen: set[str] = set()
        out: dict[str, bytes] = {}
        for row in rows:
            if row.name in seen:
                continue
            seen.add(row.name)
            out[row.name] = Path(row.file_path).read_bytes()
        return out

    # ── DB access ─────────────────────────────────────────────────────

    def db_read_session(self) -> Session:
        """Return a ``sqlmodel.Session`` for read-only queries.

        The caller owns the session lifecycle.  Use as a context manager:

            with runtime.db_read_session() as s:
                result = s.exec(select(RunRecord).where(...)).first()

        Mutating writes via this session violate the intent but are not
        blocked at runtime in v1.
        """
        return get_session()

    # ── event emission ────────────────────────────────────────────────

    def event_sink(self) -> SandboxEventSink:
        """Return the ``SandboxEventSink`` wired to the dashboard emitter."""
        return self._event_sink

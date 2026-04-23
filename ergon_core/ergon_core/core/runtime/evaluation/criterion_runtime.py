"""Default concrete implementation of ``CriterionRuntime``.

The Protocol itself lives in ``ergon_core.api.criterion_runtime`` so that
``EvaluationContext`` (also in ``api/``) can type it without importing
from ``core``.  This module is the real implementation backed by the
sandbox manager + OpenAI LLM judge.
"""

import logging
from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from uuid import UUID

from e2b import SandboxNotFoundException, TimeoutException
from ergon_core.api.criterion_runtime import (
    CommandResult,
    CriterionRuntime,
    SandboxResult,
)
from ergon_core.api.run_resource import RunResourceView
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.providers.sandbox.event_sink import (
    NoopSandboxEventSink,
    SandboxEventSink,
)
from ergon_core.core.runtime.evaluation.evaluation_schemas import CriterionContext
from ergon_core.core.settings import settings
from openai import AsyncOpenAI
from pydantic import BaseModel
from sqlmodel import Session, select

if TYPE_CHECKING:
    from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

# Re-export the Protocol so existing imports from this module keep working.
__all__ = ["CriterionRuntime", "DefaultCriterionRuntime", "ResourceNotFoundError"]


class ResourceNotFoundError(LookupError):
    """Raised by ``read_resource`` when no ``RunResource`` row matches the name."""


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
    llm_model:
        OpenAI model name for ``call_llm_judge``.
    llm_max_tokens:
        Token limit for judge responses.
    llm_temperature:
        Sampling temperature for judge calls.
    event_sink:
        Pre-constructed ``SandboxEventSink``.  If ``None`` a
        ``NoopSandboxEventSink`` is used.
    """

    def __init__(
        self,
        context: CriterionContext,
        sandbox_manager: "BaseSandboxManager",
        run_id: UUID | None = None,
        task_id: UUID | None = None,
        llm_model: str = "gpt-4o",
        llm_max_tokens: int = 1024,
        llm_temperature: float = 0.0,
        event_sink: SandboxEventSink | None = None,
    ) -> None:
        self.context = context
        self.sandbox_manager: "BaseSandboxManager" = sandbox_manager
        self._run_id: UUID = run_id if run_id is not None else context.run_id
        self._task_id: UUID | None = task_id
        self._owns_sandbox = False
        self._llm_model = llm_model
        self._llm_max_tokens = llm_max_tokens
        self._llm_temperature = llm_temperature
        self._event_sink: SandboxEventSink = event_sink or NoopSandboxEventSink()

    # ── sandbox lifecycle ─────────────────────────────────────────────

    async def ensure_sandbox(self) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            await self.sandbox_manager.create(
                self._run_id,
                run_id=self._run_id,
                timeout_minutes=30,
            )
            self._owns_sandbox = True
            return
        await self.sandbox_manager.reset_timeout(self._run_id, timeout_minutes=30)

    async def upload_files(self, files: list[dict]) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
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
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.files.write(path, content)

    async def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
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
        sandbox = self.sandbox_manager.get_sandbox(self._run_id)
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

    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.beta.chat.completions.parse(
            model=self._llm_model,
            messages=messages,
            max_tokens=self._llm_max_tokens,
            temperature=self._llm_temperature,
            response_format=response_type,
        )
        message = response.choices[0].message
        if message.parsed is None:
            raise ValueError("No parsed response from LLM judge")
        return message.parsed

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
                .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]  # ty: ignore[unresolved-attribute]
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

    async def list_resources(self) -> list[RunResourceView]:
        """Return all ``RunResourceView`` DTOs for this run, newest first."""
        with get_session() as session:
            stmt = (
                select(RunResource)
                .where(RunResource.run_id == self._run_id)
                .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]  # ty: ignore[unresolved-attribute]
            )
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
                .order_by(RunResource.created_at.desc())  # type: ignore[arg-type]  # ty: ignore[unresolved-attribute]
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

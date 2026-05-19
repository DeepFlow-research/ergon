"""Shared smoke criterion: structural + probe checks; env subclass adds content.

``SmokeCriterionBase`` owns the data-pulling (children, probe artifacts)
and structural checks (graph shape, child completion, probe exit codes).
Env subclasses implement:

- ``_verify_env_content`` — env-specific checks against leaf artifacts
  (pulled via blob storage; no sandbox needed).
- ``_verify_sandbox_setup`` — env-specific probe run inside the parent
  task's sandbox via ``context.task.sandbox.run_command(...)``; proves the
  toolchain is healthy at evaluation time.

Both hooks raise ``CriterionCheckError`` to surface as a failed
``CriterionOutcome``; anything else propagates as a bug.

Topology + slug set is sourced from ``constants.EXPECTED_SUBTASK_SLUGS``.

See docs/superpowers/plans/test-refactor/01-fixtures.md §2.5 and §2.7.
"""

import asyncio
import json
import logging
import time
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol
from uuid import UUID

from ergon_core.api.criterion import Criterion
from ergon_core.api.criterion import CriterionContext, CriterionOutcome
from ergon_core.api.errors import CriterionCheckError
from ergon_core.api.sandbox.runtime import CommandResult
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.application.runtime.status import COMPLETED, NON_AUTONOMOUS_STATUSES
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution
from tests.fixtures.smoke_components.smoke_base.constants import EXPECTED_SUBTASK_SLUGS
from pydantic import BaseModel
from sqlmodel import col, desc, select

logger = logging.getLogger(__name__)


class ProbeResult(BaseModel):
    """Parsed ``probe_*.json`` payload persisted by smoke leaf workers."""

    model_config = {"frozen": True}

    exit_code: int | None = None
    stdout: str | None = None


class ProbeChild(Protocol):
    id: UUID
    task_slug: str


class SlugChild(Protocol):
    task_slug: str


class CompletionChild(Protocol):
    task_slug: str
    status: str


class SmokeCriterionBase(Criterion):
    """Structural + probe-success checks shared by every env's smoke criterion.

    Concrete implementations of ``_pull_children`` and ``_pull_probe_results``
    live here (the previous generation's file stubbed them as
    ``NotImplementedError``).  Subclasses override the two ``_verify_*``
    hooks only.
    """

    async def evaluate(self, context: CriterionContext) -> CriterionOutcome:
        try:
            # 1. Parent-side planning checks. Child completion, artifacts,
            # probes, messages, and WAL are asserted by the E2E harness after
            # graph propagation reaches a terminal run state. The parent
            # evaluator runs before task/completed is emitted, so waiting for
            # child artifacts here would deadlock propagation.
            children = await self._pull_children(context)
            self._check_graph_shape(children)

            # 2. Sandbox-side check: attach to the parent task's OWN sandbox
            #    (kept alive by the runtime per RFC
            #    `sandbox-lifetime-covers-criteria`) and run a trivial
            #    env-specific command.  Proves the image / toolchain is
            #    healthy at evaluation time independent of what the leaves
            #    produced.  No fresh sandbox acquisition — zero extra
            #    E2B cost.
            await self._verify_sandbox_setup(context)
        except CriterionCheckError as e:
            return CriterionOutcome(
                slug=self.slug,
                name=self.slug,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"smoke criterion failed: {e}",
            )
        return CriterionOutcome(
            slug=self.slug,
            name=self.slug,
            score=1.0,
            passed=True,
            weight=self.weight,
            feedback="smoke passed",
        )

    # -- pullers (overridable; tests monkeypatch these) ----------------------

    async def _pull_children(
        self,
        context: CriterionContext,
    ) -> list[RunGraphNode]:
        """Return direct-child ``RunGraphNode`` rows of the parent task.

        ``context.execution_id`` points at the parent's
        ``RunTaskExecution``; ``RunTaskExecution.task_id`` is the parent's
        graph-node id.  Direct children are the rows whose
        ``parent_task_id`` equals that id.
        """
        with get_session() as session:
            parent_exec = session.get(RunTaskExecution, context.execution_id)
            if parent_exec is None or parent_exec.task_id is None:
                raise CriterionCheckError(
                    f"no RunTaskExecution / task_id for execution_id={context.execution_id}",
                )
            children = list(
                session.exec(
                    select(RunGraphNode)
                    .where(RunGraphNode.parent_task_id == parent_exec.task_id)
                    .order_by(RunGraphNode.task_slug),
                ).all(),
            )
        return children

    async def _wait_for_artifact_state(
        self,
        context: CriterionContext,
        *,
        timeout_s: float = 180.0,
        interval_s: float = 2.0,
    ) -> tuple[list[RunGraphNode], list[RunGraphNode], dict[UUID, ProbeResult]]:
        deadline = time.monotonic() + timeout_s
        last_error: CriterionCheckError | None = None

        while time.monotonic() < deadline:
            try:
                children = await self._pull_children(context)
                self._check_graph_shape(children)
                artifact_children = await self._artifact_children(children)
                self._check_children_completed(children)
                self._check_children_completed(artifact_children)
                probes = await self._pull_probe_results(context, artifact_children)
                self._check_probes_succeeded(probes, artifact_children)
                return children, artifact_children, probes
            except CriterionCheckError as err:
                last_error = err
                if await self._observed_terminal_non_completed(context):
                    raise
                await asyncio.sleep(interval_s)

        raise CriterionCheckError(
            f"timed out waiting for smoke child artifacts: {last_error}",
        )

    async def _artifact_children(
        self,
        children: list[RunGraphNode],
    ) -> list[RunGraphNode]:
        """Return leaf descendants that should publish probe/artifact resources.

        The happy smoke path routes direct child ``l_2`` to a recursive worker.
        ``l_2`` is still part of the direct-child topology check, but its
        nested children are the artifact-producing leaves.
        """
        with get_session() as session:
            nested = list(
                session.exec(
                    select(RunGraphNode)
                    .where(RunGraphNode.parent_task_id.in_([child.task_id for child in children]))  # ty: ignore[unresolved-attribute]
                    .order_by(RunGraphNode.task_slug),
                ).all(),
            )
        nested_parent_ids = {node.parent_task_id for node in nested}
        direct_artifact_children = [
            child for child in children if child.task_id not in nested_parent_ids
        ]
        return [*direct_artifact_children, *nested]

    async def _pull_probe_results(
        self,
        context: CriterionContext,
        children: list[RunGraphNode],
    ) -> dict[UUID, ProbeResult]:
        """Return ``{child_task_id: {"exit_code": int, "stdout": str}}``.

        For each child, finds its ``RunTaskExecution`` rows, picks the
        latest ``RunResource`` whose name begins with ``probe_`` and
        ends with ``.json``, and parses its blob-stored bytes.
        """
        results: dict[UUID, ProbeResult] = {}
        with get_session() as session:
            for child in children:
                exec_ids = [
                    row.id
                    for row in session.exec(
                        select(RunTaskExecution).where(
                            RunTaskExecution.task_id == child.task_id,
                        ),
                    ).all()
                ]
                if not exec_ids:
                    raise CriterionCheckError(
                        f"{child.task_slug}: no RunTaskExecution rows for task",
                    )
                resource = session.exec(
                    select(RunResource)
                    .where(
                        col(RunResource.task_execution_id).in_(exec_ids),
                    )
                    .where(
                        col(RunResource.name).like("probe_%.json"),
                    )
                    .order_by(
                        desc(RunResource.created_at),
                    )
                    .limit(1),
                ).first()
                if resource is None:
                    raise CriterionCheckError(
                        f"{child.task_slug}: no probe_*.json RunResource row",
                    )
                blob_bytes = Path(resource.file_path).read_bytes()
                try:
                    parsed = json.loads(blob_bytes)
                except json.JSONDecodeError as err:
                    raise CriterionCheckError(
                        f"{child.task_slug}: probe JSON invalid: {err}",
                    ) from err
                results[child.task_id] = ProbeResult.model_validate(parsed)
        return results

    # -- structural checks (raise CriterionCheckError -> failed result) -------

    def _check_graph_shape(
        self,
        children: Sequence[SlugChild],
    ) -> None:
        actual = {c.task_slug for c in children}
        expected = set(EXPECTED_SUBTASK_SLUGS)
        if actual != expected:
            raise CriterionCheckError(
                f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}",
            )

    def _check_children_completed(
        self,
        children: Sequence[CompletionChild],
    ) -> None:
        for c in children:
            if c.status != COMPLETED:
                raise CriterionCheckError(
                    f"child {c.task_slug} not completed (status={c.status!r})",
                )

    async def _observed_terminal_non_completed(self, context: CriterionContext) -> bool:
        try:
            children = await self._pull_children(context)
            artifact_children = await self._artifact_children(children)
        except CriterionCheckError:
            return False
        all_children = [*children, *artifact_children]
        return bool(all_children) and any(
            child.status in NON_AUTONOMOUS_STATUSES and child.status != COMPLETED
            for child in all_children
        )

    def _check_probes_succeeded(
        self,
        probes: dict[UUID, ProbeResult],
        children: Sequence[ProbeChild],
    ) -> None:
        by_id = {c.task_id: c for c in children}
        for child_id, probe in probes.items():
            slug = by_id[child_id].task_slug if child_id in by_id else str(child_id)
            code = probe.exit_code
            if code != 0:
                stdout = "" if probe.stdout is None else probe.stdout
                raise CriterionCheckError(
                    f"probe for {slug} exited {code}, stdout={stdout!r}",
                )

    # -- env-specific hooks (subclasses implement) ---------------------------

    async def _verify_env_content(
        self,
        context: CriterionContext,
        children: list[RunGraphNode],
        probes: dict[UUID, ProbeResult],
    ) -> None:
        """Subclass hook: read artifacts and check env-specific file shape.

        Raise ``CriterionCheckError`` when content does not match
        expectations; any other exception propagates as a bug.
        """
        raise NotImplementedError(
            "Subclasses must implement env-specific content verification",
        )

    async def _verify_sandbox_setup(self, context: CriterionContext) -> None:
        """Subclass hook: run a trivial env-specific command in the parent
        task's sandbox to prove the toolchain is healthy.

        Canonical shape for subclasses (uses the landed ``public sandbox runtime``
        DI API — criteria never call ``AsyncSandbox.connect`` directly):

            if context.task.sandbox is None:
                raise CriterionCheckError("no public sandbox runtime injected")
            await context.task.sandbox.ensure_sandbox()
            result = await context.task.sandbox.run_command("<env-probe>", timeout=20)
            if result.exit_code != 0:
                raise CriterionCheckError(
                    f"<env> health probe failed: exit={result.exit_code} "
                    f"stdout={(result.stdout or '')[:200]!r}",
                )
        """
        raise NotImplementedError(
            "Subclasses must implement env-specific sandbox health check",
        )

    async def _write_sandbox_file(
        self,
        context: CriterionContext,
        path: str,
        content: bytes,
    ) -> None:
        if context.task.sandbox.is_live:
            await context.task.sandbox.write_file(path, content)
            return
        raise CriterionCheckError("no live task sandbox attached")

    async def _run_sandbox_command(
        self,
        context: CriterionContext,
        command: str,
        *,
        timeout: int,
    ) -> CommandResult:
        if context.task.sandbox.is_live:
            return await context.task.sandbox.run_command(command, timeout=timeout)
        raise CriterionCheckError("no live task sandbox attached")

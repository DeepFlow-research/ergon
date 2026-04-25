"""Shared smoke criterion: structural + probe checks; env subclass adds content.

``SmokeCriterionBase`` owns the data-pulling (children, probe artifacts)
and structural checks (graph shape, child completion, probe exit codes).
Env subclasses implement:

- ``_verify_env_content`` — env-specific checks against leaf artifacts
  (pulled via blob storage; no sandbox needed).
- ``_verify_sandbox_setup`` — env-specific probe run inside the parent
  task's sandbox via ``context.runtime.run_command(...)``; proves the
  toolchain is healthy at evaluation time.

Both hooks raise ``CriteriaCheckError`` to surface as a failed
``CriterionResult``; anything else propagates as a bug.

Topology + slug set is sourced from ``constants.EXPECTED_SUBTASK_SLUGS``.

See docs/superpowers/plans/test-refactor/01-fixtures.md §2.5 and §2.7.
"""

import json
import logging
from collections.abc import Sequence
from pathlib import Path
from typing import Protocol
from uuid import UUID

from ergon_core.api.criterion import Criterion
from ergon_core.api.errors import CriteriaCheckError
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.api.results import CriterionResult
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import COMPLETED
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution
from pydantic import BaseModel
from sqlmodel import col, desc, select

from ergon_core.test_support.smoke_fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS

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

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        try:
            # 1. Artifact-side checks (no sandbox; reads blob storage only)
            children = await self._pull_children(context)
            self._check_graph_shape(children)
            self._check_children_completed(children)
            probes = await self._pull_probe_results(context, children)
            self._check_probes_succeeded(probes, children)
            await self._verify_env_content(context, children, probes)

            # 2. Sandbox-side check: attach to the parent task's OWN sandbox
            #    (kept alive by the runtime per RFC
            #    `sandbox-lifetime-covers-criteria`) and run a trivial
            #    env-specific command.  Proves the image / toolchain is
            #    healthy at evaluation time independent of what the leaves
            #    produced.  No fresh sandbox acquisition — zero extra
            #    E2B cost.
            await self._verify_sandbox_setup(context)
        except CriteriaCheckError as e:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=f"smoke criterion failed: {e}",
            )
        return CriterionResult(
            name=self.name,
            score=1.0,
            passed=True,
            weight=self.weight,
            feedback="smoke passed",
        )

    # -- pullers (overridable; tests monkeypatch these) ----------------------

    async def _pull_children(
        self,
        context: EvaluationContext,
    ) -> list[RunGraphNode]:
        """Return direct-child ``RunGraphNode`` rows of the parent task.

        ``context.execution_id`` points at the parent's
        ``RunTaskExecution``; ``RunTaskExecution.node_id`` is the parent's
        graph-node id.  Direct children are the rows whose
        ``parent_node_id`` equals that id.
        """
        with get_session() as session:
            parent_exec = session.get(RunTaskExecution, context.execution_id)
            if parent_exec is None or parent_exec.node_id is None:
                raise CriteriaCheckError(
                    f"no RunTaskExecution / node_id for execution_id={context.execution_id}",
                )
            children = list(
                session.exec(
                    select(RunGraphNode)
                    .where(RunGraphNode.parent_node_id == parent_exec.node_id)
                    .order_by(RunGraphNode.task_slug),
                ).all(),
            )
        return children

    async def _pull_probe_results(
        self,
        context: EvaluationContext,
        children: list[RunGraphNode],
    ) -> dict[UUID, ProbeResult]:
        """Return ``{child_node_id: {"exit_code": int, "stdout": str}}``.

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
                            RunTaskExecution.node_id == child.id,
                        ),
                    ).all()
                ]
                if not exec_ids:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: no RunTaskExecution rows for node",
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
                    raise CriteriaCheckError(
                        f"{child.task_slug}: no probe_*.json RunResource row",
                    )
                blob_bytes = Path(resource.file_path).read_bytes()
                try:
                    parsed = json.loads(blob_bytes)
                except json.JSONDecodeError as err:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: probe JSON invalid: {err}",
                    ) from err
                results[child.id] = ProbeResult.model_validate(parsed)
        return results

    # -- structural checks (raise CriteriaCheckError → failed result) --------

    def _check_graph_shape(
        self,
        children: Sequence[SlugChild],
    ) -> None:
        actual = {c.task_slug for c in children}
        expected = set(EXPECTED_SUBTASK_SLUGS)
        if actual != expected:
            raise CriteriaCheckError(
                f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}",
            )

    def _check_children_completed(
        self,
        children: Sequence[CompletionChild],
    ) -> None:
        for c in children:
            if c.status != COMPLETED:
                raise CriteriaCheckError(
                    f"child {c.task_slug} not completed (status={c.status!r})",
                )

    def _check_probes_succeeded(
        self,
        probes: dict[UUID, ProbeResult],
        children: Sequence[ProbeChild],
    ) -> None:
        by_id = {c.id: c for c in children}
        for child_id, probe in probes.items():
            slug = by_id[child_id].task_slug if child_id in by_id else str(child_id)
            code = probe.exit_code
            if code != 0:
                stdout = "" if probe.stdout is None else probe.stdout
                raise CriteriaCheckError(
                    f"probe for {slug} exited {code}, stdout={stdout!r}",
                )

    # -- env-specific hooks (subclasses implement) ---------------------------

    async def _verify_env_content(
        self,
        context: EvaluationContext,
        children: list[RunGraphNode],
        probes: dict[UUID, ProbeResult],
    ) -> None:
        """Subclass hook: read artifacts and check env-specific file shape.

        Raise ``CriteriaCheckError`` when content does not match
        expectations; any other exception propagates as a bug.
        """
        raise NotImplementedError(
            "Subclasses must implement env-specific content verification",
        )

    async def _verify_sandbox_setup(self, context: EvaluationContext) -> None:
        """Subclass hook: run a trivial env-specific command in the parent
        task's sandbox to prove the toolchain is healthy.

        Canonical shape for subclasses (uses the landed ``CriterionRuntime``
        DI API — criteria never call ``AsyncSandbox.connect`` directly):

            if context.runtime is None:
                raise CriteriaCheckError("no CriterionRuntime injected")
            await context.runtime.ensure_sandbox()
            result = await context.runtime.run_command("<env-probe>", timeout=20)
            if result.exit_code != 0:
                raise CriteriaCheckError(
                    f"<env> health probe failed: exit={result.exit_code} "
                    f"stdout={(result.stdout or '')[:200]!r}",
                )
        """
        raise NotImplementedError(
            "Subclasses must implement env-specific sandbox health check",
        )


__all__ = ["CompletionChild", "ProbeChild", "ProbeResult", "SlugChild", "SmokeCriterionBase"]

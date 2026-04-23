"""Shared smoke criterion: structural + probe checks; env subclass adds content.

The base class owns all data-pulling (children, probe artifacts). Subclasses
implement `_verify_env_content` to check env-specific file contents.
"""

from typing import Any
from uuid import UUID

from ergon_core.api import (
    Criterion,
    CriterionResult,
    CriteriaCheckError,
    EvaluationContext,
)
from ergon_core.core.persistence.graph.status_conventions import COMPLETED

from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_SLUGS


class SmokeCriterionBase(Criterion):
    """Structural + probe-success checks shared by every env's smoke criterion."""

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        # Only CriteriaCheckError represents an expected domain rejection
        # (graph shape / probe exit code / content mismatch). Any other
        # exception is a bug in this criterion or in the data path it
        # reads from -- propagate so it surfaces in the run instead of
        # being silently scored as 'failed'.
        try:
            children = await self._pull_children(context)
            self._check_graph_shape(children)
            self._check_children_completed(children)
            probes = await self._pull_probe_results(context, children)
            self._check_probes_succeeded(probes, children)
            await self._verify_env_content(context, children, probes)
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
            feedback="canonical smoke passed",
        )

    # -- pullers (overridable; tests monkeypatch these) --------------------

    async def _pull_children(
        self,
        context: EvaluationContext,  # slopcop: ignore[no-typing-any]
    ) -> list[Any]:  # slopcop: ignore[no-typing-any]
        """Return direct-child RunGraphNodes of the smoke parent.

        Opens a session, finds the parent node by
        `task_execution_id == context.execution_id`, and returns its
        direct children (one row per subtask). Each row must expose
        `task_slug`, `status`, and `id`.

        Use the graph repository in `ergon_core/core/persistence/graph/`
        -- grep for the method name; mirror the pattern in
        `task_management_service.py`.
        """
        raise NotImplementedError(
            "_pull_children: port the graph-repo call from task_management_service.py",
        )

    async def _pull_probe_results(
        self,
        context: EvaluationContext,
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> dict[UUID, dict[str, Any]]:  # slopcop: ignore[no-typing-any]
        """Return `{child_node_id: {"exit_code": int, "stdout": str}}`.

        Strategy: for each child, locate its probe artifact via `RunResource`
        (kind=ARTIFACT, name matches `probe_*.json`), download the blob,
        and parse JSON. See `sandbox_file_check.py` for a blob-reading
        idiom; grep `ergon_core/` for the RunResource repository API.
        """
        raise NotImplementedError(
            "_pull_probe_results: read probe_*.json RunResources for each child",
        )

    # -- structural checks (raise CriteriaCheckError → failed CriterionResult) --

    def _check_graph_shape(
        self,
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        actual = {c.task_slug for c in children}
        expected = set(EXPECTED_SUBTASK_SLUGS)
        if actual != expected:
            raise CriteriaCheckError(
                f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}",
            )

    def _check_children_completed(
        self,
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        for c in children:
            if c.status != COMPLETED:
                raise CriteriaCheckError(
                    f"child {c.task_slug} not completed (status={c.status!r})",
                )

    def _check_probes_succeeded(
        self,
        probes: dict[UUID, dict[str, Any]],  # slopcop: ignore[no-typing-any]
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        by_id = {c.id: c for c in children}
        for child_id, probe in probes.items():
            slug = by_id[child_id].task_slug if child_id in by_id else str(child_id)
            code = probe.get("exit_code")
            if code != 0:
                raise CriteriaCheckError(
                    f"probe for {slug} exited {code}, stdout={probe.get('stdout', '')!r}",
                )

    # -- env-specific hook ------------------------------------------------

    async def _verify_env_content(
        self,
        context: EvaluationContext,
        children: list[Any],  # slopcop: ignore[no-typing-any]
        probes: dict[UUID, dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> None:
        """Subclasses implement env-specific file checks.

        Raise ``CriteriaCheckError`` (from ``ergon_core.api``) when content
        does not match expectations so :meth:`evaluate` returns a failed
        ``CriterionResult``; raise other exceptions for bugs or I/O failures.
        """
        raise NotImplementedError(
            "Subclasses must implement env-specific content verification",
        )


class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    """Researchrubrics env smoke criterion.

    `_verify_env_content` inherits the base's `NotImplementedError` default --
    PR 2 overrides it with the researchrubrics file-content assertions.
    """

    type_slug = "researchrubrics-smoke-criterion"


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    """MiniF2F env smoke criterion.

    `_verify_env_content` inherits the base's `NotImplementedError` default --
    PR 3 overrides it with the minif2f file-content assertions.
    """

    type_slug = "minif2f-smoke-criterion"


class SweBenchSmokeCriterion(SmokeCriterionBase):
    """SWE-bench env smoke criterion.

    `_verify_env_content` inherits the base's `NotImplementedError` default --
    PR 4 overrides it with the swebench file-content assertions.
    """

    type_slug = "swebench-smoke-criterion"

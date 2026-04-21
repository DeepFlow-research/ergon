"""Shared smoke criterion: structural + probe checks; env subclass adds content.

The base class owns all data-pulling (children, probe artifacts). Subclasses
implement `_verify_env_content` to check env-specific file contents.
"""

from typing import Any
from uuid import UUID

from ergon_core.api import Criterion, CriterionResult, EvaluationContext

from ergon_builtins.workers.stubs.canonical_smoke_worker import EXPECTED_SUBTASK_SLUGS


class SmokeCriterionBase(Criterion):
    """Structural + probe-success checks shared by every env's smoke criterion."""

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        try:
            children = await self._pull_children(context)
            self._assert_graph_shape(children)
            self._assert_children_completed(children)
            probes = await self._pull_probe_results(context, children)
            self._assert_probes_succeeded(probes, children)
            await self._verify_env_content(context, children, probes)
        except AssertionError as e:
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

    # -- structural assertions --------------------------------------------

    def _assert_graph_shape(
        self,
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        actual = {c.task_slug for c in children}
        expected = set(EXPECTED_SUBTASK_SLUGS)
        if actual != expected:
            # AssertionError is control flow: caught by evaluate() and surfaced
            # as CriterionResult.feedback.
            raise AssertionError(
                f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}",
            )

    def _assert_children_completed(
        self,
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        for c in children:
            # `getattr` with default reads either the enum .name or the raw str status;
            # RunGraphNode.status is a SQLAlchemy enum in production and plain str in tests.
            status = getattr(c.status, "name", c.status)  # slopcop: ignore[no-hasattr-getattr]
            if str(status).lower() != "completed":
                raise AssertionError(
                    f"child {c.task_slug} not completed (status={status!r})",
                )

    def _assert_probes_succeeded(
        self,
        probes: dict[UUID, dict[str, Any]],  # slopcop: ignore[no-typing-any]
        children: list[Any],  # slopcop: ignore[no-typing-any]
    ) -> None:
        by_id = {c.id: c for c in children}
        for child_id, probe in probes.items():
            slug = by_id[child_id].task_slug if child_id in by_id else str(child_id)
            code = probe.get("exit_code")
            if code != 0:
                raise AssertionError(
                    f"probe for {slug} exited {code}, stdout={probe.get('stdout', '')!r}",
                )

    # -- env-specific hook ------------------------------------------------

    async def _verify_env_content(
        self,
        context: EvaluationContext,
        children: list[Any],  # slopcop: ignore[no-typing-any]
        probes: dict[UUID, dict[str, Any]],  # slopcop: ignore[no-typing-any]
    ) -> None:
        raise NotImplementedError(
            "Subclasses must implement env-specific content verification",
        )


class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 2 when the researchrubrics subworker lands."""

    type_slug = "researchrubrics-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:  # noqa: ANN001
        raise NotImplementedError("populated in PR 2")


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 3."""

    type_slug = "minif2f-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:  # noqa: ANN001
        raise NotImplementedError("populated in PR 3")


class SweBenchSmokeCriterion(SmokeCriterionBase):
    """Populated in PR 4."""

    type_slug = "swebench-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:  # noqa: ANN001
        raise NotImplementedError("populated in PR 4")

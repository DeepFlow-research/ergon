"""ResearchRubrics score-zero sad-path fixture.

Used in researchrubrics cohort slot 3 (see
``docs/superpowers/plans/test-refactor/00-program.md §3.2``).  Routes
``l_2`` to a failing leaf that DOES real work (file write + sandbox
command) BEFORE raising; the rest of the 9-subtask topology is
unchanged.

Driver asserts partial artifact + pre-fail WAL entry persist, all leaves
complete, and the run evaluation scores zero because l_2 reports a failed
probe result.
"""

from typing import ClassVar

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
from ergon_core.api import WorkerContext

from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from ergon_core.core.runtime.services.task_management_dto import SubtaskSpec

from ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from ergon_core.test_support.smoke_fixtures.smoke_base.subworker import SubworkerResult
from ergon_core.test_support.smoke_fixtures.smoke_base.worker_base import SmokeWorkerBase


class AlwaysFailSubworker:
    """Does TWO units of real work, then returns a failing probe result.

    Proves the partial-work-persists-on-failure path.  When the leaf
    fails after partial work:

      1. The partial file we wrote to ``/workspace/final_output/`` still
         becomes a ``RunResource`` row (the runtime's persist step runs
         regardless of worker exit outcome).
      2. The sandbox command we already ran still emits a
         ``sandbox_command`` event / WAL entry (the command path writes
         synchronously, before our raise).
      3. The leaf's task row still completes because worker execution itself
         completed and output persistence should remain exercised.
      4. The reused smoke criterion scores the run zero after reading the
         failed probe result.
    """

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        # Action 1: write partial artifact — must land as a RunResource.
        partial_path = f"/workspace/final_output/partial_{node_id}.md"
        await sandbox.files.write(
            partial_path,
            (
                f"# Partial work {node_id}\n\n"
                "This content was written before a deliberate failure. If smoke "
                "sees this as a RunResource row, partial serialization works.\n"
            ),
        )

        # Action 2: run a sandbox command — must emit sandbox_command WAL.
        pre_check = await sandbox.commands.run(
            f"wc -l {partial_path}",
            timeout=5,
        )
        if pre_check.exit_code != 0:
            raise RuntimeError(
                "AlwaysFailSubworker: precondition failed — expected wc to "
                f"succeed but got exit={pre_check.exit_code}. Sad-path design "
                "assumes partial work completes cleanly before the raise.",
            )

        # Action 3: deliberate failure via WorkerOutput.success=False.  This
        # exercises the failed-task path without bypassing output persistence.
        return SubworkerResult(
            file_path=partial_path,
            probe_stdout=(
                f"SmokeSadPathError: deliberate failure of {node_id} after "
                f"writing {partial_path} and running probe "
                f"(exit={pre_check.exit_code}). Smoke asserts the partial file + "
                "probe WAL survive."
            ),
            probe_exit_code=1,
        )


class ResearchRubricsFailingLeafWorker(BaseSmokeLeafWorker):
    """Registered leaf that always fails after 2 units of real work."""

    type_slug = "researchrubrics-smoke-leaf-failing"
    subworker_cls = AlwaysFailSubworker

    async def _send_completion_message(
        self,
        context: WorkerContext,
        result: SubworkerResult,
    ) -> None:
        """Preserve sad-path invariant: failed l_2 does not report completion."""
        return None


class ResearchRubricsSadPathSmokeWorker(SmokeWorkerBase):
    """Parent that routes ``l_2`` to the failing leaf; everything else
    routes to the normal leaf.

    Topology stays identical (still 9 subtasks, same deps); only the leaf
    binding for ``l_2`` differs. ``execute`` is still ``@final``; the
    hook is ``_spec_for``.
    """

    type_slug = "researchrubrics-sadpath-smoke-worker"
    leaf_slug = "researchrubrics-smoke-leaf"  # default for everything EXCEPT l_2

    FAILING_SLUGS: ClassVar[frozenset[str]] = frozenset({"l_2"})
    FAILING_LEAF_SLUG: ClassVar[str] = "researchrubrics-smoke-leaf-failing"

    def _spec_for(self, slug, deps, desc):
        leaf_slug = self.FAILING_LEAF_SLUG if slug in self.FAILING_SLUGS else self.leaf_slug
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=desc,
            assigned_worker_slug=AssignedWorkerSlug(leaf_slug),
            depends_on=[TaskSlug(d) for d in deps],
        )


__all__ = [
    "AlwaysFailSubworker",
    "ResearchRubricsFailingLeafWorker",
    "ResearchRubricsSadPathSmokeWorker",
]

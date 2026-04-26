"""Shared smoke sad-path helpers.

The canonical sad path routes ``l_2`` to a failing leaf. ``l_3`` depends
on ``l_2``, so runtime propagation should leave ``l_3`` blocked and never
started while independent branches continue normally.
"""

from typing import ClassVar

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]

from ergon_core.api import WorkerContext
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from ergon_core.core.runtime.services.task_management_dto import SubtaskSpec
from ergon_core.test_support.smoke_fixtures.smoke_base.subworker import SubworkerResult


class AlwaysFailSubworker:
    """Writes partial work and runs a probe before returning failure."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        partial_path = f"/workspace/final_output/partial_{node_id}.md"
        await sandbox.files.write(
            partial_path,
            (
                f"# Partial work {node_id}\n\n"
                "This content was written before a deliberate failure. If smoke "
                "sees this as a RunResource row, partial serialization works.\n"
            ),
        )

        pre_check = await sandbox.commands.run(
            f"wc -l {partial_path}",
            timeout=5,
        )
        if pre_check.exit_code != 0:
            raise RuntimeError(
                "AlwaysFailSubworker: precondition failed - expected wc to "
                f"succeed but got exit={pre_check.exit_code}. Sad-path design "
                "assumes partial work completes cleanly before the failure result.",
            )

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


class SadPathSmokeWorkerMixin:
    """Route ``l_2`` to a failing leaf without changing smoke topology."""

    FAILING_SLUGS: ClassVar[frozenset[str]] = frozenset({"l_2"})
    FAILING_LEAF_SLUG: ClassVar[str]
    leaf_slug: ClassVar[str]

    def _spec_for(self, slug, deps, desc):
        leaf_slug = self.FAILING_LEAF_SLUG if slug in self.FAILING_SLUGS else self.leaf_slug
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=desc,
            assigned_worker_slug=AssignedWorkerSlug(leaf_slug),
            depends_on=[TaskSlug(d) for d in deps],
        )


class FailingSmokeLeafMixin:
    """Suppress happy-path completion messages for deliberate failing leaves."""

    async def _send_completion_message(
        self,
        context: WorkerContext,
        result: SubworkerResult,
    ) -> None:
        return None


__all__ = ["AlwaysFailSubworker", "FailingSmokeLeafMixin", "SadPathSmokeWorkerMixin"]

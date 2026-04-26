"""ResearchRubrics canonical smoke — happy-path fixtures.

Happy-path triple:

- ``ResearchRubricsSmokeWorker``   — parent; spawns the 9-leaf DAG.
- ``ResearchRubricsSubworker``     — env-specific work: writes one
                                     deterministic markdown report +
                                     a ``probe_<node>.json`` with
                                     ``wc -l`` output.
- ``ResearchRubricsSmokeLeafWorker`` — thin leaf wrapper that binds the
                                       subworker class.

Registered by ``tests/e2e/_fixtures/__init__.py``.  MiniF2F and
SWE-Bench fixtures in Phase D follow the same shape.
"""

import json

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]

from ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from ergon_core.test_support.smoke_fixtures.smoke_base.sadpath import (
    AlwaysFailSubworker,
    FailingSmokeLeafMixin,
    SadPathSmokeWorkerMixin,
)
from ergon_core.test_support.smoke_fixtures.smoke_base.subworker import SubworkerResult
from ergon_core.test_support.smoke_fixtures.smoke_base.worker_base import SmokeWorkerBase


class ResearchRubricsSmokeWorker(SmokeWorkerBase):
    """Happy-path parent worker for the researchrubrics leg."""

    type_slug = "researchrubrics-smoke-worker"
    leaf_slug = "researchrubrics-smoke-leaf"


class ResearchRubricsSubworker:
    """Writes a deterministic markdown report + runs ``wc -l`` as the probe.

    Artifacts written to ``/workspace/final_output/`` so the runtime's
    persist step produces RunResource rows:

    - ``report_<node>.md``    — markdown content (content check target)
    - ``probe_<node>.json``   — ``{exit_code, stdout}`` from ``wc -l``
    """

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        report_path = f"/workspace/final_output/report_{node_id}.md"
        contents = (
            f"# Research report {node_id}\n\n"
            "Deterministic smoke output. Non-empty body required by criterion.\n"
        )
        await sandbox.files.write(report_path, contents)

        probe = await sandbox.commands.run(f"wc -l {report_path}", timeout=10)
        probe_stdout = ("" if probe.stdout is None else probe.stdout).strip()
        probe_path = f"/workspace/final_output/probe_{node_id}.json"
        await sandbox.files.write(
            probe_path,
            json.dumps({"exit_code": probe.exit_code, "stdout": probe_stdout}),
        )
        return SubworkerResult(
            file_path=report_path,
            probe_stdout=probe_stdout,
            probe_exit_code=probe.exit_code,
        )


class ResearchRubricsSmokeLeafWorker(BaseSmokeLeafWorker):
    """Registered leaf that delegates to ``ResearchRubricsSubworker``."""

    type_slug = "researchrubrics-smoke-leaf"
    subworker_cls = ResearchRubricsSubworker


class ResearchRubricsFailingLeafWorker(FailingSmokeLeafMixin, BaseSmokeLeafWorker):
    """Registered leaf that fails after partial work."""

    type_slug = "researchrubrics-smoke-leaf-failing"
    subworker_cls = AlwaysFailSubworker


class ResearchRubricsSadPathSmokeWorker(SadPathSmokeWorkerMixin, SmokeWorkerBase):
    """Parent that routes ``l_2`` to the failing leaf."""

    type_slug = "researchrubrics-sadpath-smoke-worker"
    leaf_slug = "researchrubrics-smoke-leaf"
    FAILING_LEAF_SLUG = "researchrubrics-smoke-leaf-failing"


__all__ = [
    "ResearchRubricsFailingLeafWorker",
    "ResearchRubricsSadPathSmokeWorker",
    "ResearchRubricsSmokeLeafWorker",
    "ResearchRubricsSmokeWorker",
    "ResearchRubricsSubworker",
]

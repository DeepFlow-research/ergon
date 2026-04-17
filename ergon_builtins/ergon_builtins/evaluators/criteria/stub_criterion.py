"""Deterministic sandbox-exercising smoke criterion.

Previous behaviour: returned 1.0 iff ``worker.success == True`` -- a
self-report, so the rubric could pass without the evaluator touching
the sandbox or the resource store at all.

New behaviour: returns 1.0 iff three things all hold for the current
execution:

1. At least one RunResource row exists for the execution.
2. Every RunResource's host-side blob file exists on disk, and each
   resource with a ``sandbox_path`` is readable from the sandbox
   (``test -r <sandbox_path>`` exits 0).
3. A canary bash command runs in the sandbox: ``echo $((1+1))``
   returns exit 0 with stdout ``"2"``.

The value is that an end-to-end test can now assert ``score == 1.0``
against ``stub-rubric`` and that assertion actually means the
resource-publisher, resource store, and sandbox runtime are all wired
up correctly.  No LLM, no record/replay, fully deterministic.

See ergon_paper_plans/roadmap/code/backlog/stub-consolidation/RFC.md §3.
"""

import shlex
from pathlib import Path
from typing import ClassVar

from ergon_core.api import Criterion, CriterionResult, EvaluationContext
from ergon_core.core.persistence.queries import queries


class StubCriterion(Criterion):
    """Deterministic sandbox smoke-check; see module docstring."""

    type_slug: ClassVar[str] = "stub-criterion"

    def __init__(self, *, name: str = "stub-criterion", weight: float = 1.0) -> None:
        super().__init__(name=name, weight=weight)

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        def fail(reason: str) -> CriterionResult:
            return CriterionResult(
                name=self.name,
                score=0.0,
                passed=False,
                weight=self.weight,
                feedback=reason,
            )

        # 1. resources exist
        resources = queries.resources.list_latest_for_execution(context.execution_id)
        if not resources:
            return fail(f"no RunResource produced for execution {context.execution_id}")

        # 2. blobs on disk + sandbox readability
        runtime = context.runtime
        if runtime is None:
            return fail("no criterion runtime available (sandbox not wired up)")

        for r in resources:
            blob_path = Path(r.file_path)
            if not blob_path.exists():
                return fail(f"blob missing on host at {r.file_path}")

            # ``SandboxResourcePublisher`` stores the sandbox-side path under
            # metadata_json["sandbox_origin"]; probe it so we verify the
            # sandbox runtime can actually read the file back.
            metadata = r.parsed_metadata()
            sandbox_origin = metadata.get("sandbox_origin")
            if isinstance(sandbox_origin, str) and sandbox_origin:
                probe = await runtime.run_command(f"test -r {shlex.quote(sandbox_origin)}")
                if probe.exit_code != 0:
                    return fail(f"resource not readable in sandbox: {sandbox_origin}")

        # 3. sandbox canary
        canary = await runtime.run_command("echo $((1+1))")
        if canary.exit_code != 0 or (canary.stdout or "").strip() != "2":
            return fail(
                f"sandbox bash canary failed: exit={canary.exit_code!r} "
                f"stdout={canary.stdout!r} stderr={canary.stderr!r}"
            )

        return CriterionResult(
            name=self.name,
            score=1.0,
            passed=True,
            weight=self.weight,
            feedback=(
                f"ok: {len(resources)} RunResource(s) + sandbox canary passed "
                f"for execution {context.execution_id}"
            ),
        )

"""MiniF2F canonical smoke criterion.

Env-specific hooks:

- ``_verify_env_content`` — reads each leaf's ``proof_*.lean`` artifact
  and asserts the theorem marker + proof term ``:=`` are present.
- ``_verify_sandbox_setup`` — writes a health theorem and runs
  ``lean --check`` (no ``|| true``) to prove the toolchain works at
  evaluation time, independent of what the leaves produced.
"""

from pathlib import Path

from ergon_core.api.errors import CriteriaCheckError
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution
from sqlmodel import select

from tests.e2e._fixtures.smoke_base.criterion_base import SmokeCriterionBase

HEALTH_THEOREM = """\
theorem health_check : True := trivial
"""


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    type_slug = "minif2f-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        with get_session() as session:
            for child in children:
                exec_ids = [
                    row.id
                    for row in session.exec(
                        select(RunTaskExecution).where(RunTaskExecution.node_id == child.id),
                    ).all()
                ]
                if not exec_ids:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: no RunTaskExecution rows",
                    )
                resource = session.exec(
                    select(RunResource)
                    .where(
                        RunResource.task_execution_id.in_(exec_ids),  # ty: ignore[unresolved-attribute]
                    )
                    .where(
                        RunResource.name.like("proof_%.lean"),  # ty: ignore[unresolved-attribute]
                    )
                    .order_by(
                        RunResource.created_at.desc(),  # ty: ignore[unresolved-attribute]
                    )
                    .limit(1),
                ).first()
                if resource is None:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: no proof_*.lean RunResource",
                    )
                text = Path(resource.file_path).read_bytes().decode("utf-8")
                if "theorem smoke_trivial" not in text:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: lean source missing theorem marker",
                    )
                if ":=" not in text:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: lean source missing proof term `:=`",
                    )

    async def _verify_sandbox_setup(self, context: EvaluationContext) -> None:
        """Compile a trivial theorem.  Proves Lean + elan wrapper are
        wired up.  ``trivial`` proof term avoids Mathlib dependency so
        this runs fast even on a cold toolchain."""
        if context.runtime is None:
            raise CriteriaCheckError(
                "minif2f sandbox health: CriterionRuntime not injected",
            )
        await context.runtime.ensure_sandbox()
        await context.runtime.write_file(
            "/tmp/smoke_health.lean",
            HEALTH_THEOREM.encode("utf-8"),
        )
        result = await context.runtime.run_command(
            "lean --check /tmp/smoke_health.lean",
            timeout=60,
        )
        if result.exit_code != 0:
            stdout = (result.stdout or "")[:300]
            stderr = (result.stderr or "")[:300]
            raise CriteriaCheckError(
                f"minif2f sandbox health failed: lean --check "
                f"exit={result.exit_code} stdout={stdout!r} stderr={stderr!r}",
            )


__all__ = ["MiniF2FSmokeCriterion"]

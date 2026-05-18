"""MiniF2F canonical smoke criterion.

Env-specific hooks:

- ``_verify_env_content`` — reads each leaf's ``proof_*.lean`` artifact
  and asserts the theorem marker + proof term ``:=`` are present.
- ``_verify_sandbox_setup`` — writes a health theorem and runs
  ``lean --check`` (no ``|| true``) to prove the toolchain works at
  evaluation time, independent of what the leaves produced.
"""

from pathlib import Path

from ergon_core.api.criterion import CriterionContext
from ergon_core.api.errors import CriterionCheckError
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution
from tests.fixtures.smoke_components.smoke_base.criterion_base import SmokeCriterionBase
from sqlmodel import col, desc, select

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
                    raise CriterionCheckError(
                        f"{child.task_slug}: no RunTaskExecution rows",
                    )
                resource = session.exec(
                    select(RunResource)
                    .where(
                        col(RunResource.task_execution_id).in_(exec_ids),
                    )
                    .where(
                        col(RunResource.name).like("proof_%.lean"),
                    )
                    .order_by(
                        desc(RunResource.created_at),
                    )
                    .limit(1),
                ).first()
                if resource is None:
                    raise CriterionCheckError(
                        f"{child.task_slug}: no proof_*.lean RunResource",
                    )
                text = Path(resource.file_path).read_bytes().decode("utf-8")
                if "theorem smoke_trivial" not in text:
                    raise CriterionCheckError(
                        f"{child.task_slug}: lean source missing theorem marker",
                    )
                if ":=" not in text:
                    raise CriterionCheckError(
                        f"{child.task_slug}: lean source missing proof term `:=`",
                    )

    async def _verify_sandbox_setup(self, context: CriterionContext) -> None:
        """Compile a trivial theorem.  Proves Lean + elan wrapper are
        wired up.  ``trivial`` proof term avoids Mathlib dependency so
        this runs fast even on a cold toolchain."""
        await self._write_sandbox_file(
            context,
            "/tmp/smoke_health.lean",
            HEALTH_THEOREM.encode("utf-8"),
        )
        result = await self._run_sandbox_command(
            context,
            "lean --check /tmp/smoke_health.lean",
            timeout=60,
        )
        if result.exit_code != 0:
            stdout = ("" if result.stdout is None else result.stdout)[:300]
            stderr = ("" if result.stderr is None else result.stderr)[:300]
            raise CriterionCheckError(
                f"minif2f sandbox health failed: lean --check "
                f"exit={result.exit_code} stdout={stdout!r} stderr={stderr!r}",
            )

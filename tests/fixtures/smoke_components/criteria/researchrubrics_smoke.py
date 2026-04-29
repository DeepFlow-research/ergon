"""ResearchRubrics canonical smoke criterion.

Implements the env-specific hooks on ``SmokeCriterionBase``:

- ``_verify_env_content`` — reads each leaf's ``report_*.md`` artifact
  (via blob storage) and asserts:
    * body starts with ``"# Research report"``
    * body is at least 20 bytes (non-empty content)
- ``_verify_sandbox_setup`` — runs a trivial bash probe (write file →
  wc → echo OK) via ``context.runtime.run_command`` against the parent
  task's live sandbox.  Proves bash + coreutils + /tmp are wired up.

Uses the landed CriterionRuntime DI API (RFC
``criterion-runtime-di-container``) — criteria never call
``AsyncSandbox.connect`` directly.  Phase G migrates the runtime
internal to use ``BaseSandboxManager.reconnect`` for cross-process
criteria; smoke criterion code does not change at that point.
"""

from pathlib import Path

from ergon_core.api.criterion import CriterionContext
from ergon_core.api.errors import CriterionCheckError
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution
from tests.fixtures.smoke_components.smoke_base.criterion_base import SmokeCriterionBase
from sqlmodel import col, desc, select


class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    """Env criterion for the researchrubrics smoke run."""

    type_slug = "researchrubrics-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        """Read each leaf's ``report_*.md`` and check shape."""
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
                        col(RunResource.name).like("report_%.md"),
                    )
                    .order_by(
                        desc(RunResource.created_at),
                    )
                    .limit(1),
                ).first()
                if resource is None:
                    raise CriterionCheckError(
                        f"{child.task_slug}: no report_*.md RunResource",
                    )
                body = Path(resource.file_path).read_bytes()
                if not body.startswith(b"# Research report"):
                    raise CriterionCheckError(
                        f"{child.task_slug}: report missing `# Research report` header",
                    )
                if len(body.strip()) < 20:
                    raise CriterionCheckError(
                        f"{child.task_slug}: report body too short ({len(body)} bytes)",
                    )

    async def _verify_sandbox_setup(self, context: CriterionContext) -> None:
        """Trivial env probe: bash + coreutils + /tmp writable."""
        if not context.has_runtime:
            raise CriterionCheckError(
                "researchrubrics sandbox health: CriterionRuntime not injected",
            )
        await context.ensure_sandbox()
        result = await context.run_command(
            "set -e; "
            "echo '# hello world' > /tmp/smoke_health.md && "
            "test \"$(wc -l < /tmp/smoke_health.md)\" = '1' && "
            "echo OK",
            timeout=10,
        )
        stdout = "" if result.stdout is None else result.stdout
        if result.exit_code != 0 or "OK" not in stdout:
            raise CriterionCheckError(
                f"researchrubrics sandbox health failed: "
                f"exit={result.exit_code} stdout={stdout[:200]!r}",
            )

"""SWE-Bench canonical smoke criterion.

Env-specific hooks:

- ``_verify_env_content`` — reads each leaf's ``patch_*.py`` artifact,
  parses the AST, asserts a function named ``add`` is present.  AST
  parse catches syntax errors; the presence check pins that the
  deterministic leaf output is intact end-to-end.
- ``_verify_sandbox_setup`` — asserts Python 3.10+ + ``pytest``
  importable in the sandbox.  Proves the two assumptions every
  swebench-verified leaf makes about its image.
"""

import ast
from pathlib import Path

from ergon_core.api.errors import CriteriaCheckError
from ergon_core.api.evaluation_context import EvaluationContext
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import RunResource, RunTaskExecution
from sqlmodel import select

from tests.e2e._fixtures.smoke_base.criterion_base import SmokeCriterionBase

HEALTH_PY = """\
import sys
assert sys.version_info >= (3, 10), sys.version_info
print("HEALTH_OK")
"""


class SweBenchSmokeCriterion(SmokeCriterionBase):
    type_slug = "swebench-smoke-criterion"

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
                        RunResource.name.like("patch_%.py"),  # ty: ignore[unresolved-attribute]
                    )
                    .order_by(
                        RunResource.created_at.desc(),  # ty: ignore[unresolved-attribute]
                    )
                    .limit(1),
                ).first()
                if resource is None:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: no patch_*.py RunResource",
                    )
                source = Path(resource.file_path).read_bytes().decode("utf-8")
                try:
                    tree = ast.parse(source)
                except SyntaxError as err:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: python AST parse failed: {err}",
                    ) from err
                func_names = {
                    node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
                }
                if "add" not in func_names:
                    raise CriteriaCheckError(
                        f"{child.task_slug}: expected function `add`, got {sorted(func_names)}",
                    )

    async def _verify_sandbox_setup(self, context: EvaluationContext) -> None:
        """Python 3.10+ present + pytest importable."""
        if context.runtime is None:
            raise CriteriaCheckError(
                "swebench sandbox health: CriterionRuntime not injected",
            )
        await context.runtime.ensure_sandbox()
        await context.runtime.write_file(
            "/tmp/smoke_health.py",
            HEALTH_PY.encode("utf-8"),
        )
        result = await context.runtime.run_command(
            "python /tmp/smoke_health.py && python -c 'import pytest; print(pytest.__version__)'",
            timeout=15,
        )
        stdout = result.stdout or ""
        if result.exit_code != 0 or "HEALTH_OK" not in stdout:
            stderr = (result.stderr or "")[:300]
            raise CriteriaCheckError(
                f"swebench sandbox health failed: exit={result.exit_code} "
                f"stdout={stdout[:300]!r} stderr={stderr!r}",
            )


__all__ = ["SweBenchSmokeCriterion"]

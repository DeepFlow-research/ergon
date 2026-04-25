"""SWE-Bench canonical smoke — happy-path fixtures.

Writes a trivial Python module + runs ``py_compile`` + executes it as
the probe.  ``add(2, 3) == 5`` self-check inside the file so a single
probe run exercises compile + execute + assertion pass.
"""

import json

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]

from ergon_core.test_support.smoke_fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from ergon_core.test_support.smoke_fixtures.smoke_base.subworker import SubworkerResult
from ergon_core.test_support.smoke_fixtures.smoke_base.worker_base import SmokeWorkerBase

PY_SOURCE = """\
def add(a, b):
    return a + b


if __name__ == "__main__":
    assert add(2, 3) == 5
"""


class SweBenchSmokeWorker(SmokeWorkerBase):
    """Happy-path parent for the swebench-verified leg."""

    type_slug = "swebench-smoke-worker"
    leaf_slug = "swebench-smoke-leaf"


class SweBenchSubworker:
    """Writes a trivial .py file + compiles + executes as the probe."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        patch_path = f"/workspace/final_output/patch_{node_id}.py"
        await sandbox.files.write(patch_path, PY_SOURCE)

        probe = await sandbox.commands.run(
            f"python -m py_compile {patch_path} && python {patch_path}",
            timeout=20,
        )
        probe_stdout = ("" if probe.stdout is None else probe.stdout).strip()[:4096]
        probe_path = f"/workspace/final_output/probe_{node_id}.json"
        await sandbox.files.write(
            probe_path,
            json.dumps({"exit_code": probe.exit_code, "stdout": probe_stdout}),
        )
        return SubworkerResult(
            file_path=patch_path,
            probe_stdout=probe_stdout,
            probe_exit_code=probe.exit_code,
        )


class SweBenchSmokeLeafWorker(BaseSmokeLeafWorker):
    """Registered leaf that delegates to ``SweBenchSubworker``."""

    type_slug = "swebench-smoke-leaf"
    subworker_cls = SweBenchSubworker


__all__ = [
    "SweBenchSmokeLeafWorker",
    "SweBenchSmokeWorker",
    "SweBenchSubworker",
]

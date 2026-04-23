"""MiniF2F canonical smoke — happy-path fixtures.

Writes a trivial Lean theorem + runs ``lean --check`` as the probe.
Probe uses ``|| true`` so the leaf-side probe exit is deterministic
during first-boot toolchain warmup; the criterion-side
``_verify_sandbox_setup`` runs ``lean --check`` *without* ``|| true``
so a genuinely broken toolchain fails loudly there.
"""

import json

from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]

from tests.e2e._fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from tests.e2e._fixtures.smoke_base.subworker import SubworkerResult
from tests.e2e._fixtures.smoke_base.worker_base import SmokeWorkerBase

# Trivial Lean source used by every leaf.  Deterministic; small enough to
# parse in <1s even on a cold Lean toolchain.
LEAN_SOURCE = """\
theorem smoke_trivial : 1 + 1 = 2 := by norm_num
"""


class MiniF2FSmokeWorker(SmokeWorkerBase):
    """Happy-path parent for the minif2f leg."""

    type_slug = "minif2f-smoke-worker"
    leaf_slug = "minif2f-smoke-leaf"


class MiniF2FSubworker:
    """Writes a trivial .lean proof + runs ``lean --check`` as the probe."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        proof_path = f"/workspace/final_output/proof_{node_id}.lean"
        await sandbox.files.write(proof_path, LEAN_SOURCE)

        # ``|| true`` keeps the leaf-side probe exit deterministic even if
        # Lean first-boot warmup is slow; criterion side checks the real
        # exit code via a separate health probe.
        probe = await sandbox.commands.run(
            f"lean --check {proof_path} || true",
            timeout=60,
        )
        probe_stdout = (probe.stdout or "").strip()[:4096]
        probe_path = f"/workspace/final_output/probe_{node_id}.json"
        await sandbox.files.write(
            probe_path,
            json.dumps({"exit_code": probe.exit_code, "stdout": probe_stdout}),
        )
        return SubworkerResult(
            file_path=proof_path,
            probe_stdout=probe_stdout,
            probe_exit_code=probe.exit_code,
        )


class MiniF2FSmokeLeafWorker(BaseSmokeLeafWorker):
    """Registered leaf that delegates to ``MiniF2FSubworker``."""

    type_slug = "minif2f-smoke-leaf"
    subworker_cls = MiniF2FSubworker  # type: ignore[assignment]


__all__ = [
    "MiniF2FSmokeLeafWorker",
    "MiniF2FSmokeWorker",
    "MiniF2FSubworker",
]

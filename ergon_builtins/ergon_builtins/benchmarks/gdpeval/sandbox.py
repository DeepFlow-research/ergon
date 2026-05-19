"""GDPEvalSandbox — object-bound E2B sandbox for GDPEval."""

from ergon_core.api.sandbox import Sandbox

from ergon_builtins.sandbox._manager_backed import bind_e2b_runtime, provision_e2b_runtime


class GDPEvalSandbox(Sandbox):
    """E2B-backed sandbox for GDPEval document-processing tasks."""

    template_id: str = "ergon-gdpeval-v1"
    requires_network: bool = False
    workspace_dir: str = "/workspace/gdpeval"

    async def provision(self) -> None:
        runtime = await provision_e2b_runtime(
            template=self.template_id,
            envs=self.env if self.env else None,
            timeout_seconds=self.timeout_seconds,
        )
        object.__setattr__(self, "_runtime", runtime)

    async def _bind_runtime(self, sandbox_id: str) -> None:
        runtime = await bind_e2b_runtime(sandbox_id)
        object.__setattr__(self, "_runtime", runtime)

"""LeanSandbox — object-bound Lean 4 sandbox for MiniF2F."""

from ergon_core.api.sandbox import Sandbox

from ergon_builtins.sandbox._manager_backed import bind_e2b_runtime, provision_e2b_runtime


class LeanSandbox(Sandbox):
    """Lean 4 E2B sandbox for MiniF2F."""

    lean_version: str = "4.7.0"
    e2b_template: str = "ergon-minif2f-v1"
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"

    async def provision(self) -> None:
        runtime = await provision_e2b_runtime(
            template=self.e2b_template,
            envs=self.env if self.env else None,
            timeout_seconds=self.timeout_seconds,
        )
        object.__setattr__(self, "_runtime", runtime)

    async def _bind_runtime(self, sandbox_id: str) -> None:
        runtime = await bind_e2b_runtime(sandbox_id)
        object.__setattr__(self, "_runtime", runtime)

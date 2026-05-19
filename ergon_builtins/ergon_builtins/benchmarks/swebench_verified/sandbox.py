"""SWEBenchSandbox — object-bound E2B sandbox for SWE-Bench Verified."""

from ergon_core.api.sandbox import Sandbox

from ergon_builtins.sandbox._manager_backed import bind_e2b_runtime, provision_e2b_runtime


class SWEBenchSandbox(Sandbox):
    """E2B-backed sandbox for SWE-Bench Verified instances."""

    image_tag: str = "ergon-swebench-v1"
    repo_url: str | None = None
    base_commit: str | None = None
    requires_network: bool = True

    async def provision(self) -> None:
        runtime = await provision_e2b_runtime(
            template=self.image_tag,
            envs=self.env if self.env else None,
            timeout_seconds=self.timeout_seconds,
        )
        object.__setattr__(self, "_runtime", runtime)

    async def _bind_runtime(self, sandbox_id: str) -> None:
        runtime = await bind_e2b_runtime(sandbox_id)
        object.__setattr__(self, "_runtime", runtime)

"""Shared base for E2B-backed built-in sandboxes."""

from ergon_core.api.sandbox import Sandbox

from ergon_builtins.sandbox.e2b_runtime import E2BSandboxRuntime


class E2BSandbox(Sandbox):
    """Public ``Sandbox`` implementation backed by an E2B runtime."""

    template: str | None = None

    async def provision(self) -> None:
        object.__setattr__(self, "_runtime", await self._runtime_create())

    async def _bind_runtime(self, sandbox_id: str) -> None:
        object.__setattr__(self, "_runtime", await self._runtime_connect(sandbox_id))

    async def _runtime_create(self) -> E2BSandboxRuntime:
        return await E2BSandboxRuntime.create(
            template=self.template,
            envs=self.env if self.env else None,
            timeout_seconds=self.timeout_seconds,
        )

    async def _runtime_connect(self, sandbox_id: str) -> E2BSandboxRuntime:
        return await E2BSandboxRuntime.connect(sandbox_id)

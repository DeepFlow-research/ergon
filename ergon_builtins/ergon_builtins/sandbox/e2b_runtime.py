"""E2B runtime adapter for public ``Sandbox`` implementations."""

from collections.abc import Sequence
from shlex import quote
from typing import Any

from e2b import SandboxNotFoundException, TimeoutException
from e2b_code_interpreter import AsyncSandbox

from ergon_core.api.sandbox.runtime import CommandResult, SandboxRuntime
from ergon_core.core.shared.settings import settings


class E2BSandboxRuntime(SandboxRuntime):
    """E2B-backed implementation of the public ``SandboxRuntime`` contract."""

    def __init__(self, sandbox: Any) -> None:
        self._sandbox = sandbox
        self.sandbox_id: str = sandbox.sandbox_id

    @classmethod
    async def create(
        cls,
        *,
        template: str | None,
        envs: dict[str, str] | None,
        timeout_seconds: int | None,
    ) -> "E2BSandboxRuntime":
        _ensure_e2b_api_key()
        sandbox = await AsyncSandbox.create(
            template=template,
            timeout=timeout_seconds,
            envs=envs,
            api_key=settings.e2b_api_key,
        )
        await sandbox.commands.run(
            "mkdir -p /inputs /workspace /workspace/scratchpad "
            "/workspace/final_output /skills /tools 2>/dev/null || true",
            timeout=30,
        )
        return cls(sandbox=sandbox)

    @classmethod
    async def connect(cls, sandbox_id: str) -> "E2BSandboxRuntime":
        _ensure_e2b_api_key()
        try:
            sandbox = await AsyncSandbox.connect(
                sandbox_id=sandbox_id,
                api_key=settings.e2b_api_key,
            )
        except (SandboxNotFoundException, TimeoutException) as exc:
            raise RuntimeError(f"Sandbox {sandbox_id} is not available: {exc}") from exc
        return cls(sandbox=sandbox)

    async def run_command(
        self,
        cmd: str | Sequence[str],
        *,
        timeout: int | None = None,
    ) -> CommandResult:
        rendered = cmd if isinstance(cmd, str) else " ".join(cmd)
        result = await self._sandbox.commands.run(rendered, timeout=timeout)
        return CommandResult(
            exit_code=result.exit_code,
            stdout=result.stdout or "",
            stderr=result.stderr or "",
        )

    async def write_file(self, path: str, content: bytes) -> None:
        await self._sandbox.files.write(path, content)

    async def read_file(self, path: str) -> bytes:
        return await self._sandbox.files.read(path)

    async def list_files(self, path: str) -> list[str]:
        result = await self._sandbox.commands.run(
            f"find {quote(path)} -type f 2>/dev/null || true",
            timeout=30,
        )
        if not result.stdout:
            return []
        return [line.strip() for line in result.stdout.split("\n") if line.strip()]

    async def close(self) -> None:
        await self._sandbox.kill()

    async def close_local(self) -> None:
        await self._sandbox.close()


def _ensure_e2b_api_key() -> None:
    if not settings.e2b_api_key:
        raise ValueError("E2B_API_KEY is not set.")

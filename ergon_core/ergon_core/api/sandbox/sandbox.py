"""Public sandbox base class."""

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field, PrivateAttr

from ergon_core.api._definition import from_definition_dict, to_definition_dict
from ergon_core.api.errors import SandboxNotLiveError
from ergon_core.api.sandbox.runtime import SandboxRuntime


class Sandbox(BaseModel, ABC):
    """Base for typed sandbox definitions with runtime-backed IO proxies."""

    model_config = {"arbitrary_types_allowed": True, "extra": "ignore", "frozen": False}

    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: int | None = None
    requires_network: bool = False

    _runtime: SandboxRuntime | None = PrivateAttr(default=None)

    @classmethod
    def from_definition(
        cls, sandbox_json: dict[str, Any]
    ) -> "Sandbox":  # slopcop: ignore[no-typing-any]
        """Reconstruct a concrete sandbox from persisted definition JSON."""
        return from_definition_dict(sandbox_json)

    def to_definition(self) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
        """Serialize this sandbox for persisted experiment definitions."""
        return to_definition_dict(self)

    @abstractmethod
    async def provision(self) -> None:
        """Spin up the backing environment and attach `_runtime`."""

    async def terminate(self) -> None:
        """Tear down the backing environment."""

    @property
    def is_live(self) -> bool:
        return self._runtime is not None

    @property
    def sandbox_id(self) -> str:
        return self._require_runtime().sandbox_id

    async def run_command(
        self,
        command: str,
        timeout: int = 30,
    ) -> Any:  # slopcop: ignore[no-typing-any]
        """Run a command through the live runtime."""
        return await self._require_runtime().run_command(command, timeout)

    async def write_file(self, path: str, content: bytes) -> None:
        """Write bytes through the live runtime."""
        await self._require_runtime().write_file(path, content)

    async def read_file(self, path: str) -> bytes:
        """Read bytes through the live runtime."""
        return await self._require_runtime().read_file(path)

    async def list_files(self, path: str) -> list[str]:
        """List files through the live runtime."""
        return await self._require_runtime().list_files(path)

    def _require_runtime(self) -> SandboxRuntime:
        if self._runtime is None:
            raise SandboxNotLiveError(type(self).__name__)
        return self._runtime

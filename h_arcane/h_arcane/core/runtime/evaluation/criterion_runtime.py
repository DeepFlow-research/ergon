"""Criterion runtime: execution helpers passed into criteria.

CriterionRuntime is a protocol. DefaultCriterionRuntime is the real
implementation backed by E2B sandbox + OpenAI LLM judge.
"""

import logging
from typing import TYPE_CHECKING, Protocol, TypeVar

from h_arcane.core.runtime.evaluation.evaluation_schemas import (
    CommandResult,
    CriterionContext,
    SandboxResult,
)
from openai import AsyncOpenAI

from h_arcane.core.settings import settings
from pydantic import BaseModel

if TYPE_CHECKING:
    from h_arcane.core.providers.sandbox.manager import BaseSandboxManager

T = TypeVar("T", bound=BaseModel)
logger = logging.getLogger(__name__)

class CriterionRuntime(Protocol):
    """Execution helper passed into a single criterion."""

    async def ensure_sandbox(self) -> None: ...
    async def upload_files(self, files: list[dict]) -> None: ...
    async def write_file(self, path: str, content: bytes) -> None: ...
    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...
    async def execute_code(self, code: str) -> SandboxResult: ...
    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...
    async def cleanup(self) -> None: ...

class DefaultCriterionRuntime:
    """Real criterion runtime backed by sandbox manager + OpenAI.

    Ported from ref's evaluation/runtime.py DefaultCriterionRuntime.
    """

    def __init__(
        self,
        context: CriterionContext,
        sandbox_manager: BaseSandboxManager,
        llm_model: str = "gpt-4o",
        llm_max_tokens: int = 1024,
        llm_temperature: float = 0.0,
    ) -> None:
        self.context = context
        self.sandbox_manager: BaseSandboxManager = sandbox_manager
        self._owns_sandbox = False
        self._llm_model = llm_model
        self._llm_max_tokens = llm_max_tokens
        self._llm_temperature = llm_temperature

    async def ensure_sandbox(self) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            await self.sandbox_manager.create(
                self.context.run_id,
                run_id=self.context.run_id,
                timeout_minutes=30,
            )
            self._owns_sandbox = True
            return
        await self.sandbox_manager.reset_timeout(self.context.run_id, timeout_minutes=30)

    async def upload_files(self, files: list[dict]) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        for resource in files:
            name = resource.get("name", "unknown")
            sandbox_path = f"/evaluation/{name}"
            content = resource.get("content", b"")
            if isinstance(content, str):
                content = content.encode("utf-8")
            try:
                await sandbox.files.write(sandbox_path, content)
            except Exception as exc:  # slopcop: ignore[no-broad-except]
                logger.warning("Failed to upload %s: %s", name, exc)

    async def write_file(self, path: str, content: bytes) -> None:
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.files.write(path, content)

    async def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        try:
            result = await sandbox.commands.run(command, timeout=timeout)
            return CommandResult(
                stdout=result.stdout,
                stderr=result.stderr,
                exit_code=result.exit_code,
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return CommandResult(
                stdout="",
                stderr=str(exc),
                exit_code=1,
            )

    async def execute_code(self, code: str) -> SandboxResult:
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created")
        try:
            execution = await sandbox.run_code(code, language="python", timeout=30)
            return SandboxResult(
                stdout=list(execution.logs.stdout),
                stderr=list(execution.logs.stderr),
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            error_msg = str(exc)
            if "timeout" in error_msg.lower() or "sandbox was not found" in error_msg.lower():
                raise RuntimeError(
                    f"Sandbox execution failed (likely timeout): {error_msg}. "
                    "Code criterion may have taken too long (>30s)."
                ) from exc
            raise

    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        response = await client.beta.chat.completions.parse(
            model=self._llm_model,
            messages=messages,
            max_tokens=self._llm_max_tokens,
            temperature=self._llm_temperature,
            response_format=response_type,
        )
        message = response.choices[0].message
        if message.parsed is None:
            raise ValueError("No parsed response from LLM judge")
        return message.parsed

    async def cleanup(self) -> None:
        if self._owns_sandbox:
            await self.sandbox_manager.terminate(self.context.run_id)
            self._owns_sandbox = False

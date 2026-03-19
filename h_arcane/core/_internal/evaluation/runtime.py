"""Framework-agnostic runtime for executing a single criterion."""

from __future__ import annotations

import logging
from typing import Protocol, TypeVar

from e2b.sandbox.commands.command_handle import CommandExitException
from openai import AsyncOpenAI
from pydantic import BaseModel

from h_arcane.core._internal.db.models import ResourceRecord
from h_arcane.core._internal.evaluation.schemas import (
    CommandResult,
    CriterionContext,
    SandboxResult,
)
from h_arcane.core._internal.infrastructure.sandbox import BaseSandboxManager
from h_arcane.core.settings import settings

T = TypeVar("T", bound=BaseModel)


class CriterionRuntime(Protocol):
    """Execution helper passed into a single criterion."""

    async def ensure_sandbox(self) -> None: ...

    async def upload_files(self, files: list[ResourceRecord]) -> None: ...

    async def write_file(self, path: str, content: bytes) -> None: ...

    async def run_command(self, command: str, timeout: int = 30) -> CommandResult: ...

    async def execute_code(self, code: str) -> SandboxResult: ...

    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T: ...

    async def cleanup(self) -> None: ...


class DefaultCriterionRuntime:
    """Default criterion runtime backed by sandbox + OpenAI helpers."""

    def __init__(
        self,
        context: CriterionContext,
        sandbox_manager: BaseSandboxManager,
        llm_model: str = "gpt-4o",
        llm_max_tokens: int = 1024,
        llm_temperature: float = 0.0,
    ):
        self.context = context
        self.sandbox_manager = sandbox_manager
        self._owns_sandbox = False
        self._llm_model = llm_model
        self._llm_max_tokens = llm_max_tokens
        self._llm_temperature = llm_temperature

    async def ensure_sandbox(self) -> None:
        """Ensure sandbox exists for this criterion execution."""
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

    async def upload_files(self, files: list[ResourceRecord]) -> None:
        """Upload files to sandbox /evaluation/ directory."""
        logger = logging.getLogger(__name__)

        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")

        uploaded_files = []
        failed_files = []

        for resource in files:
            sandbox_path = f"/evaluation/{resource.name}"
            try:
                content = resource.load_content()
                if not isinstance(content, bytes):
                    content = (
                        bytes(content)
                        if hasattr(content, "__bytes__")
                        else str(content).encode("utf-8")
                    )
                await sandbox.files.write(sandbox_path, content)
                uploaded_files.append(resource.name)
                logger.debug("Uploaded %s (%s bytes)", resource.name, len(content))
            except Exception as exc:
                logger.warning("Failed to upload %s: %s", resource.name, exc)
                failed_files.append({"name": resource.name, "error": str(exc)})

        if not uploaded_files and files:
            raise RuntimeError(f"No files uploaded to sandbox. Failed: {failed_files}")

    async def write_file(self, path: str, content: bytes) -> None:
        """Write a file directly into the sandbox."""
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created - call ensure_sandbox first")
        await sandbox.files.write(path, content)

    async def run_command(self, command: str, timeout: int = 30) -> CommandResult:
        """Run a command in the sandbox and capture both success and failure."""
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
        except CommandExitException as exc:
            return CommandResult(
                stdout=exc.stdout,
                stderr=exc.stderr,
                exit_code=exc.exit_code,
            )

    async def execute_code(self, code: str) -> SandboxResult:
        """Execute Python code in sandbox and return stdout/stderr."""
        sandbox = self.sandbox_manager.get_sandbox(self.context.run_id)
        if sandbox is None:
            raise RuntimeError("Sandbox not created")

        try:
            execution = await sandbox.run_code(code, language="python", timeout=30)
            return SandboxResult(
                stdout=list(execution.logs.stdout),
                stderr=list(execution.logs.stderr),
            )
        except Exception as exc:
            error_msg = str(exc)
            if "timeout" in error_msg.lower() or "sandbox was not found" in error_msg.lower():
                raise RuntimeError(
                    f"Sandbox execution failed (likely timeout): {error_msg}. "
                    "Code criterion may have taken too long (>30s)."
                ) from exc
            raise

    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T:
        """Call the judge model with structured output."""
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
        """Clean up resources if this runtime created the sandbox."""
        if self._owns_sandbox:
            await self.sandbox_manager.terminate(self.context.run_id)
            self._owns_sandbox = False

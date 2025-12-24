"""Evaluation context - data and runner with Inngest step support."""

import logging
from typing import Awaitable, Callable, TypeVar

import inngest
from openai import AsyncOpenAI
from pydantic import BaseModel, ConfigDict
from uuid import UUID

from h_arcane.core.infrastructure.sandbox import SandboxManager
from h_arcane.core.config.evaluation_config import evaluation_config
from h_arcane.core.db.models import Resource
from h_arcane.core.evaluation.schemas import SandboxResult
from h_arcane.settings import settings

T = TypeVar("T", bound=BaseModel)
R = TypeVar("R")


class EvaluationData(BaseModel):
    """Pure data for evaluation - no infrastructure methods."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    run_id: UUID
    task_input: str
    agent_reasoning: str
    agent_outputs: list[Resource]
    stage_idx: int
    stage_name: str
    rule_idx: int
    max_score: float


class EvaluationRunner:
    """Infrastructure runner - handles sandbox and LLM calls with Inngest steps.

    All operations are wrapped in ctx.step.run() for:
    - Granular observability in Inngest dashboard
    - Per-step retry on failure
    - Timing breakdown
    """

    def __init__(
        self,
        data: EvaluationData,
        sandbox_manager: SandboxManager,
        inngest_ctx: inngest.Context,
    ):
        """
        Initialize runner with data, sandbox manager, and Inngest context.

        Args:
            data: Evaluation data (task info, outputs, etc.)
            sandbox_manager: Sandbox manager for code execution
            inngest_ctx: Inngest context for step-level tracing (required)
        """
        self.data = data
        self.sandbox_manager = sandbox_manager
        self.inngest_ctx = inngest_ctx
        self._owns_sandbox = False

    async def step(
        self,
        step_id: str,
        fn: Callable[[], Awaitable[R]],
        output_type: type | None = None,
    ) -> R:
        """Run a function as an Inngest step.

        Args:
            step_id: Unique identifier for the step
            fn: Async function to execute
            output_type: Optional Pydantic type for step output serialization

        Returns:
            Result from the function
        """
        if output_type:
            return await self.inngest_ctx.step.run(step_id, fn, output_type=output_type)
        return await self.inngest_ctx.step.run(step_id, fn)

    async def ensure_sandbox(self) -> dict:
        """Ensure sandbox exists for this run. Returns status dict."""
        sandbox = self.sandbox_manager.get_sandbox(self.data.run_id)
        if not sandbox:
            # Use 30 minute timeout for evaluation sandboxes as well
            await self.sandbox_manager.create(self.data.run_id, timeout_minutes=30)
            self._owns_sandbox = True
            return {"created": True, "run_id": str(self.data.run_id)}
        return {"created": False, "run_id": str(self.data.run_id)}

    async def upload_files(self, files: list[Resource]) -> dict:
        """Upload files to sandbox /evaluation/ directory."""
        logger = logging.getLogger(__name__)

        sandbox = self.sandbox_manager.get_sandbox(self.data.run_id)
        if not sandbox:
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
                logger.debug(f"Uploaded {resource.name} ({len(content)} bytes)")
            except Exception as e:
                logger.warning(f"Failed to upload {resource.name}: {e}")
                failed_files.append({"name": resource.name, "error": str(e)})

        if not uploaded_files and files:
            raise RuntimeError(f"No files uploaded to sandbox. Failed: {failed_files}")

        return {
            "uploaded": uploaded_files,
            "failed": failed_files,
            "total": len(files),
        }

    async def execute_code(self, code: str) -> SandboxResult:
        """Execute code in sandbox and return stdout/stderr."""
        sandbox = self.sandbox_manager.get_sandbox(self.data.run_id)
        if not sandbox:
            raise RuntimeError("Sandbox not created")

        try:
            execution = await sandbox.run_code(code, language="python", timeout=30)
            return SandboxResult(
                stdout=list(execution.logs.stdout),
                stderr=list(execution.logs.stderr),
            )
        except Exception as e:
            error_msg = str(e)
            if "timeout" in error_msg.lower() or "sandbox was not found" in error_msg.lower():
                raise RuntimeError(
                    f"Sandbox execution failed (likely timeout): {error_msg}. "
                    f"Code rule may have taken too long (>30s)."
                ) from e
            raise

    async def call_llm_judge(self, messages: list, response_type: type[T]) -> T:
        """Call LLM with structured output.

        Uses evaluation_config for model/temperature/max_tokens.
        Uses OpenAI's .parse() for structured output.
        """
        client = AsyncOpenAI(api_key=settings.openai_api_key)

        response = await client.beta.chat.completions.parse(
            model=evaluation_config.llm_evaluation.model,
            messages=messages,
            max_tokens=evaluation_config.llm_evaluation.max_tokens,
            temperature=evaluation_config.llm_evaluation.temperature,
            response_format=response_type,
        )

        message = response.choices[0].message
        if message.parsed is None:
            raise ValueError("No parsed response from LLM judge")

        return message.parsed

    async def cleanup(self) -> None:
        """Clean up resources (sandbox) if we created them."""
        if self._owns_sandbox:
            await self.sandbox_manager.terminate(self.data.run_id)
            self._owns_sandbox = False

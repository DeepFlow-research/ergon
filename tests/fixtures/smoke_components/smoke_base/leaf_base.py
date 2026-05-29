"""Abstract smoke leaf worker.

``BaseSmokeLeafWorker`` is the common execution glue between the per-env
``SmokeSubworker`` implementations and the ``Worker`` ABC.  Subclasses
set ``type_slug`` and ``subworker_cls``; everything else is here.

Leaf execution:

  1. Attach to the leaf's sandbox via ``AsyncSandbox.connect``.
  2. Delegate the actual env-specific work to ``subworker_cls().work``.
  3. Post a one-line completion message to the shared
     ``smoke-completion`` thread so the driver can assert on message
     ordering + thread-FK integrity.
  4. Yield 2 ``ContextPartChunk`` objects (attach → done).

Sad-path leaves (``AlwaysFailSubworker`` in Phase C) raise inside
``subworker.work()``, so they never reach ``_send_completion_message``
— driver asserts 8 messages on sad runs vs 9 on happy runs.

See docs/superpowers/plans/test-refactor/01-fixtures.md §2.4.
"""

import json
from collections.abc import AsyncGenerator, Mapping
from typing import Any, ClassVar
from uuid import UUID

from ergon_core.api import Task, Worker, WorkerContext, WorkerStreamItem
from ergon_core.api.sandbox.runtime import CommandResult
from ergon_core.api.worker import WorkerOutput
from ergon_core.core.persistence.graph.models import SampleGraphNode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.application.communication.models import CreateMessageRequest
from ergon_core.core.application.communication.service import (
    communication_service,
)
from tests.fixtures.smoke_components.smoke_base.constants import (
    EXPECTED_PARENT_VISIBLE_CHILD_RESULT,
    EXPECTED_RESOURCE_HANDOFF,
    EXPECTED_SMOKE_LOGPROBS,
    EXPECTED_SMOKE_TOKEN_IDS,
    EXPECTED_SUBAGENT_INTERNAL_MARKER,
    HANDOFF_RESOURCE_NAME,
    SEEDED_SOURCE_DOC_NAME,
    SMOKE_OUTPUT_DIR,
    SMOKE_REPO_DIR,
    SMOKE_THREAD_TOPIC,
    SMOKE_WORKSPACE_DIR,
)
from tests.fixtures.smoke_components.smoke_base.metrics import smoke_assistant_chunk
from tests.fixtures.smoke_components.smoke_base.subworker import (
    SmokeSubworker,
    SubworkerResult,
)
from sqlmodel import select


class BaseSmokeLeafWorker(Worker):
    """Abstract leaf.  Subclasses set ``type_slug`` and ``subworker_cls``."""

    # Subclasses bind a concrete SmokeSubworker implementation here.  The
    # leaf's ``execute`` instantiates ``subworker_cls()`` and delegates.
    subworker_cls: ClassVar[type[SmokeSubworker]]
    toolkit_type: ClassVar[str | None] = None

    # Driver asserts per-leaf context chunk count against this constant.
    # Sad-path leaves that raise inside subworker.work() emit fewer turns
    # (only the first 'attaching' turn) and are skipped from the strict
    # equality check on the sad run.
    LEAF_TURN_COUNT: ClassVar[int] = 2

    def __init__(
        self,
        *,
        name: str,
        model: str | None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        # PR 5 converted Worker to a Pydantic BaseModel — `metadata` is
        # now a non-nullable `dict[str, Any]` field with a
        # `default_factory=dict`. Convert the nullable sentinel
        # into ``{}`` so callers that still pass ``metadata=None``
        # (e.g. smoke unit tests) keep working.
        super().__init__(name=name, model=model, metadata=dict(metadata) if metadata else {})
        self._last_result: SubworkerResult | None = None

    async def execute(
        self,
        task: Task,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[WorkerStreamItem, None]:
        task_hex = context.task_id.hex[:8] if context.task_id else "unknown"

        # --- Turn 1: attaching + starting ---------------------------------
        yield smoke_assistant_chunk(
            (
                f"{type(self).__name__}: attaching to sandbox "
                f"{context.sandbox_id} for task={task_hex}"
            ),
        )

        if not task.sandbox.is_live:
            raise RuntimeError(f"{type(task.sandbox).__name__} is not live for smoke leaf")

        sandbox = _PublicSandboxAdapter(task.sandbox)
        await task.sandbox.run_command(
            f"mkdir -p {SMOKE_OUTPUT_DIR} {SMOKE_WORKSPACE_DIR} {SMOKE_REPO_DIR}",
            timeout=10,
        )
        await self._prepare_semantic_inputs(task, context)
        result = await self.subworker_cls().work(task_id=task_hex, sandbox=sandbox)
        toolkit_probe = await self._run_builtin_toolkit_probe(task=task, context=context)
        toolkit_probe.update(
            {
                "synthetic_token_ids": EXPECTED_SMOKE_TOKEN_IDS,
                "synthetic_logprobs": EXPECTED_SMOKE_LOGPROBS,
                "internal_marker": EXPECTED_SUBAGENT_INTERNAL_MARKER,
                "parent_visible_marker": EXPECTED_PARENT_VISIBLE_CHILD_RESULT,
            },
        )
        await task.sandbox.write_file(
            f"{SMOKE_OUTPUT_DIR}/toolkit_probe_{task_hex}.json",
            json.dumps(toolkit_probe, sort_keys=True),
        )
        await self._maybe_publish_source_handoff(task=task, context=context)
        handoff_probe = await self._maybe_verify_source_handoff(context=context)
        self._last_result = result

        # Post a one-line completion message to the shared
        # ``smoke-completion`` thread.  Every happy-path leaf sends exactly
        # one message; sad-path leaves that raise inside ``subworker.work``
        # never reach this call — driver asserts on that shape.
        await self._send_completion_message(context, result)

        # --- Turn 2: done + result summary --------------------------------
        yield smoke_assistant_chunk(
            (
                f"{type(self).__name__}: done task={task_hex} "
                f"file={result.file_path} probe_exit={result.probe_exit_code}"
            ),
        )

        yield WorkerOutput(
            output=result.probe_stdout,
            success=result.probe_exit_code == 0,
            metadata={
                "probe_exit_code": result.probe_exit_code,
                "file_path": result.file_path,
                "toolkit_probe": toolkit_probe,
                "handoff_probe": handoff_probe,
            },
        )

    async def _prepare_semantic_inputs(self, task: Task, context: WorkerContext) -> None:
        task_slug = self._lookup_task_slug(context.task_id)
        if task_slug != EXPECTED_RESOURCE_HANDOFF.producer_slug:
            return
        await task.sandbox.write_file(
            f"{SMOKE_OUTPUT_DIR}/{SEEDED_SOURCE_DOC_NAME}",
            (
                "# Smoke Source Brief\n\n"
                "Use this seeded brief to prove resource handoff and task-local "
                "sandbox IO both work in canonical smoke.\n"
            ),
        )

    async def _maybe_publish_source_handoff(
        self,
        *,
        task: Task,
        context: WorkerContext,
    ) -> None:
        task_slug = self._lookup_task_slug(context.task_id)
        if task_slug != EXPECTED_RESOURCE_HANDOFF.producer_slug:
            return
        payload = {
            "producer_slug": EXPECTED_RESOURCE_HANDOFF.producer_slug,
            "consumer_slug": EXPECTED_RESOURCE_HANDOFF.consumer_slug,
            "source_doc": SEEDED_SOURCE_DOC_NAME,
            "parent_visible_result": EXPECTED_PARENT_VISIBLE_CHILD_RESULT,
        }
        await task.sandbox.write_file(
            f"{SMOKE_OUTPUT_DIR}/{HANDOFF_RESOURCE_NAME}",
            json.dumps(payload, sort_keys=True),
        )
        await communication_service.save_message(
            CreateMessageRequest(
                sample_id=context.sample_id,
                task_attempt_id=context.execution_id,
                from_agent_id=f"leaf-{task_slug}",
                to_agent_id=f"leaf-{EXPECTED_RESOURCE_HANDOFF.consumer_slug}",
                thread_topic=SMOKE_THREAD_TOPIC,
                content=f"handoff ready: {HANDOFF_RESOURCE_NAME}",
            ),
        )

    async def _maybe_verify_source_handoff(self, *, context: WorkerContext) -> dict[str, Any]:
        task_slug = self._lookup_task_slug(context.task_id)
        if task_slug != EXPECTED_RESOURCE_HANDOFF.consumer_slug:
            return {"checked": False}

        deadline_resources = await context.resources(name=HANDOFF_RESOURCE_NAME)
        if not deadline_resources:
            return {"checked": True, "ok": False, "reason": "handoff resource missing"}
        payload = json.loads((await context.read_resource(deadline_resources[0].id)).decode())
        return {
            "checked": True,
            "ok": payload.get("consumer_slug") == EXPECTED_RESOURCE_HANDOFF.consumer_slug,
            "resource_name": deadline_resources[0].name,
            "producer_slug": payload.get("producer_slug"),
        }

    async def _run_builtin_toolkit_probe(
        self,
        *,
        task: Task,
        context: WorkerContext,
    ) -> dict[str, Any]:
        del context
        if self.toolkit_type is None:
            return {"toolkit": None, "ok": True}

        if self.toolkit_type.endswith(":ResearchRubricsToolkit"):
            from ergon_builtins.benchmarks.researchrubrics.toolkit import (
                ResearchRubricsToolkit,
            )

            toolkit = ResearchRubricsToolkit(
                enable_web_browse=False,
                workspace_root=SMOKE_WORKSPACE_DIR,
            )
            tools = {tool.name: tool for tool in toolkit.tools(task.sandbox, task)}
            write = await tools["write_report"].function(
                "tmp/toolkit_probe.md",
                "research toolkit smoke probe\n",
            )
            read = await tools["read_report"].function("tmp/toolkit_probe.md")
            return {
                "toolkit": self.toolkit_type,
                "ok": bool(write.ok and read.ok),
                "marker": "research-toolkit",
            }

        if self.toolkit_type.endswith(":MiniF2FToolkit"):
            from ergon_builtins.benchmarks.minif2f.toolkit import MiniF2FToolkit

            toolkit = MiniF2FToolkit()
            tools = {tool.name: tool for tool in toolkit.tools(task.sandbox, task)}
            path = f"{SMOKE_WORKSPACE_DIR}/toolkit_probe.lean"
            write = await tools["write_lean_file"].function(
                path,
                "theorem smoke_toolkit_probe : True := by trivial\n",
            )
            verify = await tools["verify_lean_proof"].function(path)
            return {
                "toolkit": self.toolkit_type,
                "ok": bool(write.success and verify.success and verify.verified),
                "marker": "lean-toolkit",
            }

        if self.toolkit_type.endswith(":SWEBenchToolkit"):
            from ergon_builtins.benchmarks.swebench_verified.toolkit import (
                SWEBenchToolkit,
            )

            await task.sandbox.run_command(f"mkdir -p {SMOKE_REPO_DIR}", timeout=10)
            toolkit = SWEBenchToolkit(repo_root=SMOKE_REPO_DIR)
            tools = {tool.name: tool for tool in toolkit.tools(task.sandbox, task)}
            edit = await tools["str_replace_editor"].function(
                command="create",
                path="toolkit_probe.py",
                file_text="def smoke_toolkit_probe():\n    return True\n",
            )
            bash = await tools["bash"].function(
                "python -m py_compile toolkit_probe.py",
                timeout_sec=60,
            )
            return {
                "toolkit": self.toolkit_type,
                "ok": bool(edit.ok and bash.exit_code == 0),
                "marker": "swebench-toolkit",
            }

        return {
            "toolkit": self.toolkit_type,
            "ok": True,
            "marker": "unprobed-toolkit",
        }

    async def _send_completion_message(
        self,
        context: WorkerContext,
        result: SubworkerResult,
    ) -> None:
        """Post one ThreadMessage on the ``smoke-completion`` thread.

        Structure asserted by ``_assert_thread_messages_ordered`` in the
        driver:

        - Thread topic: ``"smoke-completion"``
        - ``from_agent_id``: ``f"leaf-{task_slug}"`` — looked up from
          ``SampleGraphNode.task_slug`` by ``context.task_id``
        - ``to_agent_id``: ``"parent"``
        - 9 messages per happy run, sequence_num 1..9 per-thread-monotonic
        - 8 messages per sad run (environment-probe suppresses this call; metadata-validate is blocked)
        """
        task_slug = self._lookup_task_slug(context.task_id)
        await communication_service.save_message(
            CreateMessageRequest(
                sample_id=context.sample_id,
                task_attempt_id=context.execution_id,
                from_agent_id=f"leaf-{task_slug}",
                to_agent_id="parent",
                thread_topic="smoke-completion",
                content=(
                    f"{task_slug}: done exit={result.probe_exit_code} file={result.file_path}"
                ),
            ),
        )

    @staticmethod
    def _lookup_task_slug(task_id: UUID | None) -> str:
        """Resolve the leaf's ``task_slug`` from its ``SampleGraphNode``.

        ``WorkerContext`` exposes ``task_id`` but not ``task_slug``; the
        leaf's message needs the slug so observers can identify which
        leaf sent it without joining back to the graph table.  Fallback
        for the rare ``task_id is None`` case is a readable placeholder
        so messages still land rather than raising from test scaffolding.
        """
        if task_id is None:
            return "unknown"
        with get_session() as session:
            node = session.exec(
                select(SampleGraphNode).where(SampleGraphNode.task_id == task_id)
            ).first()
        return node.task_slug if node is not None else f"node-{task_id.hex[:8]}"


class _PublicSandboxFiles:
    def __init__(self, sandbox) -> None:
        self._sandbox = sandbox

    async def write(self, path: str, content: bytes | str) -> None:
        await self._sandbox.write_file(path, content)

    async def read(self, path: str) -> bytes:
        return await self._sandbox.read_file(path)


class _PublicSandboxCommands:
    def __init__(self, sandbox) -> None:
        self._sandbox = sandbox

    async def run(self, command: str, *, timeout: int | None = None) -> CommandResult:
        return await self._sandbox.run_command(command, timeout=timeout)


class _PublicSandboxAdapter:
    def __init__(self, sandbox) -> None:
        self.files = _PublicSandboxFiles(sandbox)
        self.commands = _PublicSandboxCommands(sandbox)

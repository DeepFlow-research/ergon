"""ReAct worker agent with ask_stakeholder and benchmark tools."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from litellm.cost_calculator import cost_per_token
from pydantic import BaseModel
from pydantic_ai import Agent
from pydantic_ai._agent_graph import CallToolsNode, ModelRequestNode
from pydantic_ai.exceptions import AgentRunError, UsageLimitExceeded
from pydantic_ai.messages import (
    ModelMessage,
    ModelRequest,
    ModelResponse,
    RetryPromptPart,
    TextPart,
    ThinkingPart,
    ToolCallPart,
    ToolReturnPart,
)
from pydantic_ai.usage import RunUsage
from pydantic_graph import End

from h_arcane.benchmarks.common.workers.config import WorkerConfig
from h_arcane.core._internal.agents.base import BaseToolkit, WorkerExecutionOutput
from h_arcane.core._internal.db.models import Action, ExecutionError
from h_arcane.core._internal.infrastructure.tracing import CompletedSpan
from h_arcane.core.task import Resource, Task
from h_arcane.core.worker import BaseWorker, WorkerContext, WorkerResult


class ReActWorker(BaseWorker):
    """ReAct-style worker with benchmark toolkit tools.

    Implements SDK BaseWorker protocol. Toolkit is read from WorkerContext.toolkit
    during execute().
    """

    # SDK BaseWorker required properties
    id: UUID
    name: str
    model: str
    tools: list
    system_prompt: str

    class _PendingToolCall(BaseModel):
        """Tracks when the model requested a tool call."""

        tool_call: ToolCallPart
        started_at: datetime

    def __init__(self, model: str, config: WorkerConfig):
        """
        Initialize ReAct worker.

        Args:
            model: LLM model to use
            config: WorkerConfig with system_prompt and max_questions
        """
        self.id = uuid4()
        self.name = "react_worker"
        self.model = model
        self.system_prompt = config.system_prompt
        self._config = config
        self.tools = []  # Will be populated from toolkit in execute()

    async def execute(self, task: Task, context: WorkerContext) -> WorkerResult:
        """
        Execute task using SDK types.

        Args:
            task: SDK Task with description and resources
            context: SDK WorkerContext with sandbox, run_id, toolkit, etc.

        Returns:
            WorkerResult with actions, outputs, and trace data

        Raises:
            ValueError: If toolkit not provided in context
        """
        # Get toolkit from context (self-configure pattern)
        if context.toolkit is None:
            raise ValueError("ReActWorker requires toolkit in context.toolkit")

        toolkit: BaseToolkit = context.toolkit
        self.tools = toolkit.get_tools()


        # Create agent with structured output type.
        # We keep the existing ReActWorker surface area and only swap the engine.
        agent = Agent(
            model=self.model,
            instructions=self.system_prompt,
            tools=self.tools,
            output_type=WorkerExecutionOutput,
        )

        # Format task prompt
        task_prompt = self._format_task(task.description, context.input_resources)

        # Run agent
        agent_run_started_at = datetime.now(timezone.utc)
        agent_run_context = self._child_trace_context(context, "agent.run")
        self._emit_trace_span(
            context=context,
            span_name="agent.run.started",
            span_key="agent.run.started",
            start_time=agent_run_started_at,
            end_time=agent_run_started_at,
            attributes={
                "tool_count": len(self.tools),
                "has_input_resources": bool(context.input_resources),
            },
        )
        try:
            agent_run = None
            node_count = 0
            async with agent.iter(task_prompt) as run_state:
                agent_run = run_state
                async for node in run_state:
                    node_count += 1
                    self._emit_agent_node_event(context, node_count, node)
                result = run_state.result
            if result is None:
                raise RuntimeError("Agent run ended without a final result")
        except Exception as exc:
            if agent_run is not None:
                return self._build_failed_worker_result(
                    context=context,
                    toolkit=toolkit,
                    agent_run=agent_run,
                    agent_run_started_at=agent_run_started_at,
                    node_count=node_count,
                    error=exc,
                )
            self._emit_trace_span(
                context=context,
                span_name="agent.run",
                span_key="agent.run",
                start_time=agent_run_started_at,
                end_time=datetime.now(timezone.utc),
                attributes={
                    "success": False,
                    "tool_count": len(self.tools),
                    "has_input_resources": bool(context.input_resources),
                    "node_count": node_count,
                },
                status_code="error",
                status_message=str(exc),
                trace_context=agent_run_context,
            )
            raise
        except BaseException as exc:
            if agent_run is not None:
                return self._build_failed_worker_result(
                    context=context,
                    toolkit=toolkit,
                    agent_run=agent_run,
                    agent_run_started_at=agent_run_started_at,
                    node_count=node_count,
                    error=exc,
                )
            self._emit_trace_span(
                context=context,
                span_name="agent.run",
                span_key="agent.run",
                start_time=agent_run_started_at,
                end_time=datetime.now(timezone.utc),
                attributes={
                    "success": False,
                    "tool_count": len(self.tools),
                    "has_input_resources": bool(context.input_resources),
                    "node_count": node_count,
                },
                status_code="error",
                status_message=str(exc),
                trace_context=agent_run_context,
            )
            raise

        agent_run_completed_at = datetime.now(timezone.utc)
        messages = result.new_messages()
        message_summary = self._summarize_messages(messages)
        self._emit_trace_span(
            context=context,
            span_name="agent.run",
            span_key="agent.run",
            start_time=agent_run_started_at,
            end_time=agent_run_completed_at,
            attributes={
                "success": True,
                "tool_count": len(self.tools),
                "has_input_resources": bool(context.input_resources),
                "node_count": node_count,
                **message_summary,
            },
            trace_context=agent_run_context,
        )

        # Extract actions from result with full context (run_id, agent_id)
        # Actions are now complete - no mutation needed by orchestration layer
        actions = self._extract_actions_from_messages(
            messages=messages,
            usage=result.usage(),
            context=context,
        )
        self._emit_trace_span(
            context=context,
            span_name="worker.actions_extracted",
            span_key="worker.actions_extracted",
            start_time=agent_run_completed_at,
            end_time=datetime.now(timezone.utc),
            attributes={
                **message_summary,
                "action_count": len(actions),
            },
        )

        # Extract structured output from result
        output_text = None
        reasoning = None
        if isinstance(result.output, WorkerExecutionOutput):
            output_text = result.output.output_text
            reasoning = result.output.reasoning

        # Get Q&A history from toolkit (now required by BaseToolkit protocol)
        qa_exchanges = toolkit.get_qa_history()

        result_built_at = datetime.now(timezone.utc)
        self._emit_trace_span(
            context=context,
            span_name="worker.result.build",
            span_key="worker.result.build",
            start_time=result_built_at,
            end_time=result_built_at,
            attributes={
                "action_count": len(actions),
                "question_count": len(qa_exchanges),
                "has_output_text": output_text is not None,
                "has_reasoning": reasoning is not None,
            },
        )

        return WorkerResult(
            success=True,
            output_text=output_text,
            reasoning=reasoning,
            actions=actions,  # Actions are now complete with run_id/agent_id
            qa_exchanges=qa_exchanges,  # Execution layer will persist
            outputs=[],  # Benchmark outputs tracked via sandbox
        )

    def _build_failed_worker_result(
        self,
        *,
        context: WorkerContext,
        toolkit: BaseToolkit,
        agent_run: Any,
        agent_run_started_at: datetime,
        node_count: int,
        error: BaseException,
    ) -> WorkerResult:
        """Serialize partial progress for terminal agent-run failures."""
        agent_run_context = self._child_trace_context(context, "agent.run")
        partial_messages = self._safe_agent_run_messages(agent_run)
        partial_usage = self._safe_agent_run_usage(agent_run)
        message_summary = self._summarize_messages(partial_messages)
        actions = self._extract_actions_from_messages(
            messages=partial_messages,
            usage=partial_usage,
            context=context,
        )
        qa_exchanges = toolkit.get_qa_history()
        error_label = self._classify_agent_run_error(error)

        self._emit_trace_span(
            context=context,
            span_name="agent.run",
            span_key="agent.run",
            start_time=agent_run_started_at,
            end_time=datetime.now(timezone.utc),
            attributes={
                "success": False,
                "tool_count": len(self.tools),
                "has_input_resources": bool(context.input_resources),
                "node_count": node_count,
                "error_type": error_label,
                "partial_message_count": len(partial_messages),
                **message_summary,
            },
            status_code="error",
            status_message=str(error),
            trace_context=agent_run_context,
        )
        self._emit_trace_span(
            context=context,
            span_name="worker.actions_extracted",
            span_key="worker.actions_extracted",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "action_count": len(actions),
                "success": False,
                "partial_result": True,
                **message_summary,
            },
        )
        self._emit_trace_span(
            context=context,
            span_name="worker.result.build",
            span_key="worker.result.build",
            start_time=datetime.now(timezone.utc),
            end_time=datetime.now(timezone.utc),
            attributes={
                "success": False,
                "partial_result": True,
                "action_count": len(actions),
                "question_count": len(qa_exchanges),
                "error_type": error_label,
            },
        )

        return WorkerResult(
            success=False,
            error=f"{error_label}: {error}",
            actions=actions,
            qa_exchanges=qa_exchanges,
            outputs=[],
            output_text=None,
            reasoning=None,
        )

    def _safe_agent_run_messages(self, agent_run: Any) -> list[ModelMessage]:
        """Best-effort access to partial message history from an interrupted run."""
        if agent_run is None:
            return []
        try:
            return agent_run.new_messages()
        except Exception:
            return []

    def _safe_agent_run_usage(self, agent_run: Any) -> RunUsage:
        """Best-effort access to partial usage from an interrupted run."""
        if agent_run is None:
            return RunUsage()
        try:
            return agent_run.usage()
        except Exception:
            return RunUsage()

    def _classify_agent_run_error(self, error: BaseException) -> str:
        """Map agent failures into stable trace categories."""
        if isinstance(error, UsageLimitExceeded):
            return "usage_limit_exceeded"
        if isinstance(error, AgentRunError):
            return "agent_run_error"
        return "agent_run_interrupted"

    def _child_trace_context(self, context: WorkerContext, span_key: str):
        """Build a child trace context when tracing is enabled."""
        if context.trace_sink is None or context.trace_context is None:
            return None
        return context.trace_sink.child_context(context.trace_context, span_key=span_key)

    def _emit_trace_span(
        self,
        *,
        context: WorkerContext,
        span_name: str,
        span_key: str,
        start_time: datetime,
        end_time: datetime,
        attributes: dict[str, Any],
        status_code: str = "ok",
        status_message: str | None = None,
        trace_context: Any | None = None,
    ) -> None:
        """Emit a small lifecycle span if tracing is enabled."""
        if context.trace_sink is None or context.trace_context is None:
            return
        resolved_context = trace_context or context.trace_sink.child_context(
            context.trace_context,
            span_key=span_key,
        )
        context.trace_sink.emit_span(
            CompletedSpan(
                name=span_name,
                context=resolved_context,
                start_time=start_time,
                end_time=end_time,
                attributes=attributes,
                status_code=status_code,
                status_message=status_message,
            )
        )

    def _summarize_messages(self, messages: list[ModelMessage]) -> dict[str, int]:
        """Produce bounded counts for worker lifecycle tracing."""
        summary = {
            "message_count": len(messages),
            "model_request_count": 0,
            "model_response_count": 0,
            "tool_call_count": 0,
            "tool_return_count": 0,
            "retry_prompt_count": 0,
            "text_part_count": 0,
            "thinking_part_count": 0,
        }

        for message in messages:
            if isinstance(message, ModelResponse):
                summary["model_response_count"] += 1
                for response_part in message.parts:
                    if isinstance(response_part, ToolCallPart):
                        summary["tool_call_count"] += 1
                    elif isinstance(response_part, TextPart):
                        summary["text_part_count"] += 1
                    elif isinstance(response_part, ThinkingPart):
                        summary["thinking_part_count"] += 1
            elif isinstance(message, ModelRequest):
                summary["model_request_count"] += 1
                for request_part in message.parts:
                    if isinstance(request_part, ToolReturnPart):
                        summary["tool_return_count"] += 1
                    elif isinstance(request_part, RetryPromptPart):
                        summary["retry_prompt_count"] += 1

        return summary

    def _emit_agent_node_event(self, context: WorkerContext, node_index: int, node: Any) -> None:
        """Emit a lightweight event for each observed agent graph node."""
        if context.trace_sink is None or context.trace_context is None:
            return

        attributes: dict[str, Any] = {
            "node_index": node_index,
            "node_type": type(node).__name__,
        }
        if isinstance(node, ModelRequestNode):
            attributes.update(self._summarize_model_request_node(node))
        elif isinstance(node, CallToolsNode):
            attributes.update(self._summarize_call_tools_node(node))
        if isinstance(node, End):
            attributes["is_end"] = True

        context.trace_sink.add_event(
            context.trace_context,
            "agent.node",
            attributes=attributes,
        )

    def _summarize_model_request_node(self, node: ModelRequestNode[Any, Any]) -> dict[str, Any]:
        """Summarize an outgoing model request without logging payload bodies."""
        tool_return_names: list[str] = []
        retry_prompt_count = 0
        tool_return_count = 0

        for part in node.request.parts:
            if isinstance(part, ToolReturnPart):
                tool_return_count += 1
                tool_return_names.append(part.tool_name)
            elif isinstance(part, RetryPromptPart):
                retry_prompt_count += 1

        return {
            "request_part_count": len(node.request.parts),
            "tool_return_count": tool_return_count,
            "tool_return_name_count": len(set(tool_return_names)),
            "tool_return_names": self._summarize_names(tool_return_names),
            "retry_prompt_count": retry_prompt_count,
            "is_resuming_without_prompt": bool(node.is_resuming_without_prompt),
        }

    def _summarize_call_tools_node(self, node: CallToolsNode[Any, Any]) -> dict[str, Any]:
        """Summarize a model response at the tool-processing boundary."""
        response = node.model_response
        tool_names = [part.tool_name for part in response.tool_calls]
        thinking_part_count = sum(1 for part in response.parts if isinstance(part, ThinkingPart))
        text_part_count = sum(1 for part in response.parts if isinstance(part, TextPart))

        return {
            "response_part_count": len(response.parts),
            "tool_call_count": len(tool_names),
            "tool_name_count": len(set(tool_names)),
            "tool_names": self._summarize_names(tool_names),
            "text_part_count": text_part_count,
            "text_chars": len(response.text or ""),
            "thinking_part_count": thinking_part_count,
            "thinking_chars": len(response.thinking or ""),
            "file_part_count": len(response.files),
            "finish_reason": response.finish_reason or "unknown",
        }

    def _summarize_names(self, names: list[str], limit: int = 5) -> str:
        """Return a bounded, stable summary of observed names."""
        unique_names = sorted(set(names))
        if not unique_names:
            return ""
        if len(unique_names) <= limit:
            return ",".join(unique_names)
        remaining = len(unique_names) - limit
        return f"{','.join(unique_names[:limit])},+{remaining}_more"

    def _format_task(self, task_description: str, input_resources: list[Resource]) -> str:
        """
        Format task description with input resources.

        Args:
            task_description: Task description
            input_resources: List of SDK Resources

        Returns:
            Formatted task prompt
        """
        lines = [f"Task: {task_description}", ""]

        if input_resources:
            lines.append("Input files:")
            for resource in input_resources:
                lines.append(
                    f"- {resource.name or resource.path} ({resource.mime_type or 'unknown'})"
                )
            lines.append("")
            lines.append(
                "These files are available in /inputs/ directory. Use the appropriate tools to read them."
            )

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────────
    # Action extraction logic (framework-specific, owned by this worker)
    # ─────────────────────────────────────────────────────────────────────────────

    def _extract_actions_from_messages(
        self, messages: list[ModelMessage], usage: RunUsage, context: WorkerContext
    ) -> list[Action]:
        """Extract actions from PydanticAI messages as complete Action objects."""
        actions: list[Action] = []
        action_num = 0

        run_id = context.run_id
        agent_id = context.agent_config_id
        agent_total_tokens = usage.input_tokens + usage.output_tokens
        agent_total_cost_usd = self._calculate_cost(usage)
        pending_tool_calls: dict[str, ReActWorker._PendingToolCall] = {}

        for message in messages:
            timestamp = message.timestamp or datetime.now(timezone.utc)
            if isinstance(message, ModelResponse):
                for response_part in message.parts:
                    if isinstance(response_part, ToolCallPart):
                        pending_tool_calls[response_part.tool_call_id] = self._PendingToolCall(
                            tool_call=response_part,
                            started_at=timestamp,
                        )
                        continue

                    response_action = self._process_response_part(
                        part=response_part,
                        action_num=action_num,
                        timestamp=timestamp,
                        agent_total_tokens=agent_total_tokens,
                        agent_total_cost_usd=agent_total_cost_usd,
                        run_id=run_id,
                        agent_id=agent_id,
                    )
                    if response_action:
                        actions.append(response_action)
                        action_num += 1
            elif isinstance(message, ModelRequest):
                for request_part in message.parts:
                    request_action = self._process_request_part(
                        part=request_part,
                        pending_tool_calls=pending_tool_calls,
                        action_num=action_num,
                        timestamp=timestamp,
                        agent_total_tokens=agent_total_tokens,
                        agent_total_cost_usd=agent_total_cost_usd,
                        run_id=run_id,
                        agent_id=agent_id,
                    )
                    if request_action:
                        actions.append(request_action)
                        action_num += 1

        return actions

    def _process_response_part(
        self,
        part: TextPart | ThinkingPart | ToolCallPart | Any,
        action_num: int,
        timestamp: datetime,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
        run_id: UUID,
        agent_id: UUID | None,
    ) -> Action | None:
        """Convert a model response part into an Action where applicable."""
        if isinstance(part, TextPart):
            return Action(
                run_id=run_id,
                agent_id=agent_id,
                action_num=action_num,
                started_at=timestamp,
                completed_at=timestamp,
                agent_total_tokens=agent_total_tokens,
                agent_total_cost_usd=agent_total_cost_usd,
                action_type="message",
                input=json.dumps({"type": "message"}),
                output=part.content,
            )

        if isinstance(part, ThinkingPart):
            return Action(
                run_id=run_id,
                agent_id=agent_id,
                action_num=action_num,
                started_at=timestamp,
                completed_at=timestamp,
                agent_total_tokens=agent_total_tokens,
                agent_total_cost_usd=agent_total_cost_usd,
                action_type="reasoning",
                input=json.dumps({"type": "reasoning"}),
                output=part.content,
            )

        return None

    def _process_request_part(
        self,
        part: ToolReturnPart | RetryPromptPart | Any,
        pending_tool_calls: dict[str, _PendingToolCall],
        action_num: int,
        timestamp: datetime,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
        run_id: UUID,
        agent_id: UUID | None,
    ) -> Action | None:
        """Convert a model request part into an Action where applicable."""
        if isinstance(part, ToolReturnPart):
            pending_tool_call = pending_tool_calls.pop(part.tool_call_id, None)
            tool_input = None
            tool_name = part.tool_name
            started_at = timestamp
            completed_at = part.timestamp
            if pending_tool_call is not None:
                tool_name = pending_tool_call.tool_call.tool_name
                tool_input = pending_tool_call.tool_call.args
                started_at = pending_tool_call.started_at
            duration_ms = self._compute_duration_ms(started_at, completed_at)

            output_str = self._serialize_content(part.content)
            error_dict = self._extract_error_from_output(part.content)

            return Action(
                run_id=run_id,
                agent_id=agent_id,
                action_num=action_num,
                started_at=started_at,
                completed_at=completed_at,
                duration_ms=duration_ms,
                agent_total_tokens=agent_total_tokens,
                agent_total_cost_usd=agent_total_cost_usd,
                action_type=tool_name,
                input=self._serialize_tool_args(tool_input),
                output=output_str,
                error=error_dict,
            )

        if isinstance(part, RetryPromptPart):
            pending_tool_call = pending_tool_calls.pop(part.tool_call_id, None)
            started_at = pending_tool_call.started_at if pending_tool_call is not None else timestamp
            return Action(
                run_id=run_id,
                agent_id=agent_id,
                action_num=action_num,
                started_at=started_at,
                completed_at=part.timestamp,
                duration_ms=self._compute_duration_ms(started_at, part.timestamp),
                agent_total_tokens=agent_total_tokens,
                agent_total_cost_usd=agent_total_cost_usd,
                action_type="retry_prompt",
                input=json.dumps(
                    {
                        "tool_name": part.tool_name,
                        "tool_call_id": part.tool_call_id,
                    }
                ),
                output=self._serialize_content(part.content),
            )

        return None

    def _serialize_tool_args(self, args: str | dict[str, Any] | None) -> str:
        """Serialize tool arguments to a stable JSON string."""
        if args is None:
            return json.dumps({})
        if isinstance(args, str):
            return args
        return json.dumps(args, default=str)

    def _compute_duration_ms(self, started_at: datetime, completed_at: datetime) -> int:
        """Return a non-negative elapsed duration in milliseconds."""
        return max(int((completed_at - started_at).total_seconds() * 1000), 0)

    def _serialize_content(self, content: Any) -> str:
        """Serialize arbitrary tool content for Action.output."""
        if isinstance(content, str):
            return content
        if isinstance(content, BaseModel):
            return json.dumps(content.model_dump(), indent=2, default=str)
        return json.dumps(content, indent=2, default=str)

    def _extract_error_from_output(self, output: Any) -> dict | None:
        """
        Extract error information from tool output if present.

        Tool outputs are typically Pydantic models or dicts with:
        - success: bool
        - error: str | None (error message)
        - exception_type: str | None (optional)
        - stack_trace: str | None (optional)

        Returns:
            ExecutionError as dict if error detected, None otherwise.
        """
        # Convert to dict if it's a Pydantic model
        if isinstance(output, BaseModel):
            output_dict = output.model_dump()
        elif isinstance(output, dict):
            output_dict = output
        else:
            return None

        # Check for failure indicators
        success = output_dict.get("success")
        error_message = output_dict.get("error")

        # If success is explicitly False or there's an error message
        if success is False or (error_message and success is not True):
            return ExecutionError(
                message=error_message or "Unknown error",
                exception_type=output_dict.get("exception_type"),
                stack_trace=output_dict.get("stack_trace"),
                details=None,
            ).model_dump()

        return None

    def _calculate_cost(self, usage: RunUsage) -> float:
        """Calculate cost from usage."""
        try:
            prompt_cost, completion_cost = cost_per_token(
                model=self.model,
                prompt_tokens=usage.input_tokens,
                completion_tokens=usage.output_tokens,
                cache_read_input_tokens=usage.cache_read_tokens,
                cache_creation_input_tokens=usage.cache_write_tokens,
            )
            return prompt_cost + completion_cost
        except Exception:
            return 0.0

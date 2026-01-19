"""ReAct worker agent with ask_stakeholder and benchmark tools."""

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel
from litellm.cost_calculator import cost_per_token

from agents import Agent, Runner, function_tool
from agents.items import (
    MessageOutputItem,
    ReasoningItem,
    RunItem,
    ToolCallItem,
    ToolCallOutputItem,
)
from agents.result import RunResult
from agents.usage import Usage
from openai.types.responses import ResponseFunctionToolCall, ResponseOutputText
from inngest_agents import as_step

from h_arcane.core.worker import BaseWorker, WorkerContext, WorkerResult
from h_arcane.core.task import Task, Resource
from h_arcane.core._internal.agents.base import BaseToolkit, WorkerExecutionOutput
from h_arcane.core._internal.db.models import Action, ExecutionError
from h_arcane.benchmarks.common.workers.config import WorkerConfig


class ReActWorker(BaseWorker):
    """ReAct-style worker with ask_stakeholder + benchmark tools.

    Implements SDK BaseWorker protocol. Toolkit is read from WorkerContext.toolkit
    during execute().
    """

    # SDK BaseWorker required properties
    id: UUID
    name: str
    model: str
    tools: list
    system_prompt: str

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

        # Build tools list with durability wrappers
        # Each tool call becomes an individual Inngest step via as_step()
        raw_tools = [
            self._make_ask_tool(toolkit),
            *toolkit.get_tools(),
        ]
        tools = [as_step(t) for t in raw_tools]

        # Create agent with structured output type
        # We use WorkerExecutionOutput for structured extraction, then convert to WorkerResult
        agent = Agent(
            name=self.name,
            model=self.model,
            instructions=self.system_prompt,
            tools=tools,
            output_type=WorkerExecutionOutput,
        )

        # Format task prompt
        task_prompt = self._format_task(task.description, context.input_resources)

        # Run agent
        result = await Runner.run(agent, task_prompt, max_turns=25)

        # Extract actions from result (framework-specific logic owned by this worker)
        actions = self._extract_actions_from_result(result)

        # Extract structured output from result
        output_text = None
        reasoning = None
        if result.final_output and isinstance(result.final_output, WorkerExecutionOutput):
            output_text = result.final_output.output_text
            reasoning = result.final_output.reasoning

        # Get Q&A history from toolkit (now required by BaseToolkit protocol)
        qa_exchanges = toolkit.get_qa_history()

        return WorkerResult(
            success=True,
            output_text=output_text,
            reasoning=reasoning,
            actions=actions,  # Execution layer will add run_id/agent_id and persist
            qa_exchanges=qa_exchanges,  # Execution layer will persist
            outputs=[],  # Benchmark outputs tracked via sandbox
        )

    def _make_ask_tool(self, toolkit: BaseToolkit):
        """Create ask_stakeholder tool function."""

        @function_tool
        async def ask_stakeholder(question: str) -> str:
            """
            Ask the stakeholder a clarification question about the task.

            Use this when you're uncertain about requirements, preferences, or how to proceed.

            Parameters:
                question (str): Your question for the stakeholder

            Returns:
                str: The stakeholder's answer

            Example:
                ```python
                answer = await ask_stakeholder("What format should the output be in?")
                ```
            """
            return await toolkit.ask_stakeholder(question)

        return ask_stakeholder

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

    def _extract_actions_from_result(self, result: RunResult) -> list[Action]:
        """
        Extract actions from RunResult without persisting them.

        Returns Action objects WITHOUT run_id/agent_id set - these should be
        added by the execution layer before persistence.

        Handles all item types:
        - MessageOutputItem: LLM text responses
        - ToolCallItem + ToolCallOutputItem: Tool calls with inputs/outputs
        - ReasoningItem: Reasoning/thinking steps
        - Other item types: Logged generically
        """
        actions = []
        action_num = 0

        # Step 1: Build map of call_id -> ToolCallItem for matching
        tool_calls: dict[str, ToolCallItem] = {}
        for item in result.new_items:
            if isinstance(item, ToolCallItem):
                raw = item.raw_item
                if isinstance(raw, ResponseFunctionToolCall):
                    tool_calls[raw.call_id] = item

        # Step 2: Calculate costs from usage (run-level, not per-action)
        usage = result.context_wrapper.usage
        agent_total_tokens = usage.input_tokens + usage.output_tokens
        agent_total_cost_usd = self._calculate_cost(usage)

        # Step 3: Process all items in order
        for item in result.new_items:
            action = self._process_item(
                item, tool_calls, action_num, agent_total_tokens, agent_total_cost_usd
            )
            if action:
                actions.append(action)
                action_num += 1

        return actions

    def _process_item(
        self,
        item: RunItem,
        tool_calls: dict[str, ToolCallItem],
        action_num: int,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
    ) -> Action | None:
        """Process a single RunItem and return Action object, or None to skip."""
        now = datetime.now(timezone.utc)

        match item:
            case MessageOutputItem():
                return self._extract_message(
                    item, action_num, now, agent_total_tokens, agent_total_cost_usd
                )
            case ToolCallOutputItem():
                return self._extract_tool_call_output(
                    item, tool_calls, action_num, now, agent_total_tokens, agent_total_cost_usd
                )
            case ReasoningItem():
                return self._extract_reasoning(
                    item, action_num, now, agent_total_tokens, agent_total_cost_usd
                )
            case ToolCallItem():
                # Skip - we handle these when processing ToolCallOutputItem
                return None
            case _:
                return self._extract_generic(
                    item, action_num, now, agent_total_tokens, agent_total_cost_usd
                )

    def _extract_message(
        self,
        item: MessageOutputItem,
        action_num: int,
        now: datetime,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
    ) -> Action:
        """Extract action record from MessageOutputItem."""
        text = self._extract_message_text(item)
        return Action(
            action_num=action_num,
            started_at=now,
            completed_at=now,
            agent_total_tokens=agent_total_tokens,
            agent_total_cost_usd=agent_total_cost_usd,
            action_type="message",
            input=json.dumps({"type": "message"}),
            output=text,
        )

    def _extract_tool_call_output(
        self,
        item: ToolCallOutputItem,
        tool_calls: dict[str, ToolCallItem],
        action_num: int,
        now: datetime,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
    ) -> Action:
        """Extract action record from ToolCallOutputItem."""
        raw = item.raw_item
        call_id = raw.get("call_id") if isinstance(raw, dict) else None

        if call_id and isinstance(call_id, str) and call_id in tool_calls:
            tool_call_item = tool_calls[call_id]
            tool_raw = tool_call_item.raw_item

            if isinstance(tool_raw, ResponseFunctionToolCall):
                # Format output
                output = item.output
                if isinstance(output, str):
                    output_str = output
                elif isinstance(output, BaseModel):
                    # Pydantic models
                    output_str = json.dumps(output.model_dump(), indent=2, default=str)
                else:
                    # Other types (dicts, lists, etc.)
                    output_str = json.dumps(output, indent=2, default=str)

                # Extract error if present in output
                error_dict = self._extract_error_from_output(output)

                return Action(
                    action_num=action_num,
                    started_at=now,
                    completed_at=now,
                    agent_total_tokens=agent_total_tokens,
                    agent_total_cost_usd=agent_total_cost_usd,
                    action_type=tool_raw.name,
                    input=tool_raw.arguments,  # Already JSON string from OpenAI
                    output=output_str,
                    error=error_dict,
                )

        # Orphan output - log anyway
        return Action(
            action_num=action_num,
            started_at=now,
            completed_at=now,
            agent_total_tokens=agent_total_tokens,
            agent_total_cost_usd=agent_total_cost_usd,
            action_type="tool_output",
            input=json.dumps({"call_id": call_id}),
            output=str(item.output),
        )

    def _extract_reasoning(
        self,
        item: ReasoningItem,
        action_num: int,
        now: datetime,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
    ) -> Action:
        """Extract action record from ReasoningItem."""
        text = ""
        if item.raw_item.summary:
            for summary in item.raw_item.summary:
                text += summary.text + "\n"

        return Action(
            action_num=action_num,
            started_at=now,
            completed_at=now,
            agent_total_tokens=agent_total_tokens,
            agent_total_cost_usd=agent_total_cost_usd,
            action_type="reasoning",
            input=json.dumps({"type": "reasoning"}),
            output=text.strip(),
        )

    def _extract_generic(
        self,
        item: RunItem,
        action_num: int,
        now: datetime,
        agent_total_tokens: int,
        agent_total_cost_usd: float,
    ) -> Action:
        """Extract action record from generic/unknown item types."""
        return Action(
            action_num=action_num,
            started_at=now,
            completed_at=now,
            agent_total_tokens=agent_total_tokens,
            agent_total_cost_usd=agent_total_cost_usd,
            action_type=item.type,
            input=json.dumps({"type": item.type}),
            output=str(item.raw_item),
        )

    def _extract_message_text(self, item: MessageOutputItem) -> str:
        """Extract text content from MessageOutputItem."""
        text_parts = []
        for content in item.raw_item.content:
            if isinstance(content, ResponseOutputText):
                text_parts.append(content.text)
        return "\n".join(text_parts)

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

    def _calculate_cost(self, usage: Usage) -> float:
        """Calculate cost from usage."""
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read = usage.input_tokens_details.cached_tokens
        cache_creation = usage.input_tokens - cache_read

        prompt_cost, completion_cost = cost_per_token(
            model=self.model,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cache_read_input_tokens=cache_read,
            cache_creation_input_tokens=cache_creation - cache_read,
        )
        return prompt_cost + completion_cost

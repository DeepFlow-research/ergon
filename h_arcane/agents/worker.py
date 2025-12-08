"""ReAct worker agent with ask_stakeholder and GDPEval tools."""

from datetime import datetime
from uuid import UUID
from pydantic import BaseModel, Field
import json

from agents import Agent, AgentHooks, Runner, RunContextWrapper, Tool, function_tool
from litellm.cost_calculator import cost_per_token


from h_arcane.agents.toolkit import WorkerToolkit
from h_arcane.db.models import Resource
from h_arcane.db.queries import queries
from h_arcane.tools.responses import ToolResult, ToolResponse


class WorkerContext(BaseModel):
    """Context passed to worker agent tools during execution."""

    run_id: UUID
    num_executed_tools: int = Field(default=0, description="Number of tools executed so far")
    model_name: str = Field(default="gpt-4o", description="Name of the model used")


class WorkerExecutionOutput(BaseModel):
    """Structured output from worker execution."""

    reasoning: str = Field(description="Explanation of approach and decisions made")
    output_text: str = Field(description="Text summary/output of what was accomplished")
    output_resource_ids: list[str] = Field(
        default_factory=list, description="UUIDs of resources created during execution"
    )


def _extract_tool_input(context: RunContextWrapper[WorkerContext], tool_name: str) -> str:
    """Extract tool call arguments from database messages.

    Queries the database for the most recent message containing a tool call
    matching the given tool name, then extracts and formats its arguments.
    """
    run_id = context.context.run_id
    
    # Get all messages for this run, ordered by sequence number (most recent last)
    messages = queries.messages.get_all(run_id, order_by="sequence_num")
    
    # Search messages in reverse (most recent first)
    for msg in reversed(messages):
        if not msg.content:
            continue
        
        # Try parsing as JSON first (for structured messages)
        content = None
        try:
            content = json.loads(msg.content) if isinstance(msg.content, str) else msg.content
        except json.JSONDecodeError:
            # Not JSON, might be plain text - skip for now
            continue
        
        if not isinstance(content, dict):
            continue
        
        # Check if this message has tool calls
        tool_calls = content.get("tool_calls")
        if not tool_calls or not isinstance(tool_calls, list):
            continue

        # Find matching tool call
        for tool_call in tool_calls:
            if not isinstance(tool_call, dict):
                continue

            func_info = tool_call.get("function", {})
            if not isinstance(func_info, dict):
                continue
                
            if func_info.get("name") != tool_name:
                continue

            # Parse arguments (may be string or dict)
            args = func_info.get("arguments", {})
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = {}
            elif not isinstance(args, dict):
                args = {}

            return json.dumps(args, indent=2, default=str)

    # No matching tool call found
    return json.dumps({}, indent=2)


class ActionLoggingHooks(AgentHooks):
    """AgentHooks that logs all tool calls to the database."""

    def __init__(self):
        """Initialize hooks with a cache for tool call arguments and start times."""
        self._tool_call_args: dict[str, str] = {}  # Maps (run_id, tool_name, action_num) -> args JSON
        self._tool_start_times: dict[str, datetime] = {}  # Maps (run_id, tool_name, action_num) -> start time

    async def on_tool_start(
        self,
        context: RunContextWrapper[WorkerContext],
        agent: Agent[WorkerContext],
        tool: Tool,
    ) -> None:
        """Capture tool call arguments and start time when tool starts."""
        worker_context = context.context
        run_id = worker_context.run_id
        tool_name = tool.name if hasattr(tool, "name") else str(tool)
        action_num = worker_context.num_executed_tools
        
        # Try to extract arguments from database messages
        tool_input = _extract_tool_input(context, tool_name)
        
        # Cache the arguments and start time for this tool call
        cache_key = f"{run_id}:{tool_name}:{action_num}"
        self._tool_call_args[cache_key] = tool_input
        self._tool_start_times[cache_key] = datetime.utcnow()

    async def on_tool_end(
        self,
        context: RunContextWrapper[WorkerContext],
        agent: Agent[WorkerContext],
        tool: Tool,
        result: ToolResult,
    ) -> None:
        """Log tool call completion to database."""
        # Get run_id and action_num from context
        worker_context = context.context
        run_id = worker_context.run_id
        action_num = worker_context.num_executed_tools
        worker_context.num_executed_tools += 1

        # Get tool name
        tool_name = tool.name if hasattr(tool, "name") else str(tool)

        # Try to get cached arguments from on_tool_start first
        cache_key = f"{run_id}:{tool_name}:{action_num}"
        tool_input = self._tool_call_args.get(cache_key)
        
        # Fallback to database lookup if not cached
        if tool_input is None:
            tool_input = _extract_tool_input(context, tool_name)
        
        # Clean up cache entry
        self._tool_call_args.pop(cache_key, None)

        # Format output (truncate if too long for database)
        # ToolResult is a union type, so we can use isinstance checks
        if isinstance(result, str):
            output_str = result
        elif isinstance(result, ToolResponse):
            # All ToolResponse subclasses have model_dump()
            output_str = json.dumps(result.model_dump(), indent=2, default=str)
        else:
            # Fallback for any other type (shouldn't happen with proper typing)
            output_str = json.dumps(result, indent=2, default=str)

        # Get start time and calculate duration
        cache_key = f"{run_id}:{tool_name}:{action_num}"
        started_at = self._tool_start_times.pop(cache_key, None)
        completed_at = datetime.utcnow()
        
        # Calculate duration if we have start time
        duration_ms = None
        if started_at:
            duration_delta = completed_at - started_at
            duration_ms = int(duration_delta.total_seconds() * 1000)
        
        # Use completed_at as started_at if we don't have start time (fallback)
        if started_at is None:
            started_at = completed_at

        # Extract token usage and calculate cost if available
        # Note: Tool executions don't directly consume tokens, but the LLM call
        # that invoked the tool might have usage info in the context
        usage = context.usage

        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        cache_read_input_tokens = usage.input_tokens_details.cached_tokens
        cache_creation_input_tokens = usage.input_tokens - cache_read_input_tokens

        prompt_cost, completion_cost = cost_per_token(
            model=worker_context.model_name,
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cache_read_input_tokens=cache_read_input_tokens,
            cache_creation_input_tokens=cache_creation_input_tokens - cache_read_input_tokens,
        )
        cost_usd = prompt_cost + completion_cost

        queries.actions.create(
            run_id=run_id,
            action_num=action_num,
            action_type=tool_name,
            input=tool_input or json.dumps({}, indent=2),
            output=output_str,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=duration_ms,
            tokens=input_tokens + output_tokens,
            cost_usd=cost_usd,
        )


REACT_WORKER_PROMPT = """
You are a skilled worker completing a task for a stakeholder.

You have access to tools including:
- `ask_stakeholder`: Ask clarification questions when uncertain
- Document tools: read_pdf, create_docx
- Spreadsheet tools: read_excel, create_excel, read_csv, create_csv
- Code execution: execute_python_code
- OCR: ocr_image

Use ask_stakeholder when you're uncertain about:
- What exactly the stakeholder wants
- How to interpret ambiguous requirements
- Preferences between different approaches

Think step by step. Complete the task to the best of your ability.

When you finish, provide:
1. Your reasoning: Explain your approach and key decisions
2. Output text: A summary or text output of what you accomplished
3. Output resource IDs: List UUIDs of all files/resources you created (these are automatically tracked)
"""


class ReActWorker:
    """ReAct-style worker with ask_stakeholder + GDPEval tools."""

    def __init__(self, model: str = "gpt-4o"):
        """
        Initialize ReAct worker.

        Args:
            model: LLM model to use (default: "gpt-4o")
        """
        self.model = model

    async def execute(
        self,
        run_id: UUID,
        task_description: str,
        input_resources: list[Resource],
        toolkit: WorkerToolkit,
    ) -> WorkerExecutionOutput:
        """
        Execute task, return structured output with reasoning and resources.

        Args:
            run_id: The run ID
            task_description: Task description
            input_resources: List of input resources
            toolkit: WorkerToolkit with tools

        Returns:
            WorkerExecutionOutput with reasoning, output_text, and output_resource_ids

        Example:
            ```python
            worker = ReActWorker(model="gpt-4o")
            output = await worker.execute(run_id, task_desc, input_resources, toolkit)
            print(output.reasoning)
            print(output.output_text)
            ```
        """
        # Build tools list
        tools = [
            self._make_ask_tool(toolkit),
            *toolkit.get_gdpeval_tools(),
        ]

        # Create context with run_id and tool execution tracking
        worker_context = WorkerContext(run_id=run_id, num_executed_tools=0)

        # Create hooks to log all tool calls
        hooks = ActionLoggingHooks()

        # Create agent with context type
        agent = Agent[WorkerContext](
            name="TaskWorker",
            model=self.model,
            instructions=REACT_WORKER_PROMPT,
            tools=tools,
            output_type=WorkerExecutionOutput,
            hooks=hooks,
        )

        # Format task prompt
        task_prompt = self._format_task(task_description, input_resources)

        # Run agent with context (Runner.run takes agent, input, and optional context)
        result = await Runner.run(agent, task_prompt, context=worker_context)

        # Extract structured output
        execution_output: WorkerExecutionOutput = result.final_output

        # Get actual resources from database to ensure they're up to date
        db_resources = queries.resources.get_all(run_id=run_id)

        # Update output_resource_ids with actual resource IDs from DB
        execution_output.output_resource_ids = [str(res.id) for res in db_resources]

        return execution_output

    def _make_ask_tool(self, toolkit: WorkerToolkit):
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
            input_resources: List of input resources

        Returns:
            Formatted task prompt
        """
        lines = [f"Task: {task_description}", ""]

        if input_resources:
            lines.append("Input files:")
            for resource in input_resources:
                lines.append(f"- {resource.name} ({resource.mime_type})")
                if resource.preview_text:
                    lines.append(f"  Preview: {resource.preview_text[:200]}...")
            lines.append("")
            lines.append(
                "These files are available in /inputs/ directory. Use the appropriate tools to read them."
            )

        return "\n".join(lines)

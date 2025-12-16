"""ReAct worker agent with ask_stakeholder and GDPEval tools."""

from uuid import UUID
from pydantic import BaseModel, Field

from agents import Agent, Runner, function_tool

from h_arcane.agents.tracing import log_actions_from_result
from h_arcane.benchmarks.base import BaseToolkit
from h_arcane.db.models import AgentConfig, Resource
from h_arcane.db.queries import queries
from h_arcane.schemas.base import WorkerConfig


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


class ReActWorker:
    """ReAct-style worker with ask_stakeholder + GDPEval tools."""

    def __init__(self, model: str, config: WorkerConfig):
        """
        Initialize ReAct worker.

        Args:
            model: LLM model to use
            config: WorkerConfig with system_prompt and max_questions
        """
        self.model = model
        self.config = config

    async def execute(
        self,
        run_id: UUID,
        task_description: str,
        input_resources: list[Resource],
        toolkit: BaseToolkit,
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
            worker = ReActWorker(model="gpt-4o", config=GDPEVAL_CONFIG)
            output = await worker.execute(run_id, task_desc, input_resources, toolkit)
            print(output.reasoning)
            print(output.output_text)
            ```
        """
        # Build tools list
        tools = [
            self._make_ask_tool(toolkit),
            *toolkit.get_tools(),
        ]

        # Create agent config record before running
        agent_config = queries.agent_configs.create(
            AgentConfig(
                run_id=run_id,
                name="TaskWorker",
                agent_type="react_worker",
                model=self.model,
                system_prompt=self.config.system_prompt,
                tools=[t.name if hasattr(t, "name") else str(t) for t in tools],
            )
        )

        # Create context with run_id
        worker_context = WorkerContext(run_id=run_id, num_executed_tools=0)

        # Create agent (no hooks needed - we'll log from RunResult)
        agent = Agent[WorkerContext](
            name="TaskWorker",
            model=self.model,
            instructions=self.config.system_prompt,
            tools=tools,
            output_type=WorkerExecutionOutput,
        )

        # Format task prompt
        task_prompt = self._format_task(task_description, input_resources)

        # Run agent with context
        result = await Runner.run(agent, task_prompt, context=worker_context, max_turns=25)

        # Log all actions from result
        log_actions_from_result(
            result=result,
            agent_id=agent_config.id,
            run_id=run_id,
            model_name=self.model,
        )

        # Extract structured output
        execution_output: WorkerExecutionOutput = result.final_output

        # Get actual resources from database to ensure they're up to date
        db_resources = queries.resources.get_all(run_id=run_id)

        # Update output_resource_ids with actual resource IDs from DB
        execution_output.output_resource_ids = [str(res.id) for res in db_resources]

        return execution_output

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

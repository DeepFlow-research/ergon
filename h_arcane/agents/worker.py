"""ReAct worker agent with ask_stakeholder and GDPEval tools."""

from uuid import UUID
from pydantic import BaseModel, Field

from agents import Agent, Runner, function_tool

from h_arcane.agents.toolkit import WorkerToolkit
from h_arcane.db.models import Resource
from h_arcane.db.queries import queries


class WorkerExecutionOutput(BaseModel):
    """Structured output from worker execution."""

    reasoning: str = Field(description="Explanation of approach and decisions made")
    output_text: str = Field(description="Text summary/output of what was accomplished")
    output_resource_ids: list[str] = Field(
        default_factory=list, description="UUIDs of resources created during execution"
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

        # Create agent
        agent = Agent(
            name="TaskWorker",
            model=self.model,
            instructions=REACT_WORKER_PROMPT,
            tools=tools,
            output_type=WorkerExecutionOutput,
        )

        # Format task prompt
        task_prompt = self._format_task(task_description, input_resources)

        # Run agent (Runner.run takes agent and input string or list of messages)
        result = await Runner.run(agent, task_prompt)

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

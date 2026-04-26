from typing import ClassVar

from ergon_core.api import Tool
from ergon_core.api.worker_context import WorkerContext

from ergon_builtins.tools.workflow_cli_tool import make_workflow_cli_tool
from ergon_builtins.workers.research_rubrics.researcher_worker import (
    _RESEARCHER_SYSTEM_PROMPT,
    ResearchRubricsResearcherWorker,
)

_WORKFLOW_PROMPT = (
    _RESEARCHER_SYSTEM_PROMPT
    + "\n\nYou also have a workflow(command) tool. Use it to inspect this run before "
    "deciding what context is missing. Useful commands include: "
    "`inspect task-tree`, `inspect resource-list --scope input`, "
    "`inspect resource-list --scope visible --limit 20`, "
    "`inspect next-actions`, and "
    "`manage materialize-resource --resource-id <id> --dry-run`. "
    "Use `--format json` when you need stable IDs. Resource copies are snapshots: "
    "materialized files become resources owned by this task, not edits to the source."
)


class ResearchRubricsWorkflowCliReActWorker(ResearchRubricsResearcherWorker):
    type_slug: ClassVar[str] = "researchrubrics-workflow-cli-react"

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.system_prompt = _WORKFLOW_PROMPT

    def _extra_tools(self, context: WorkerContext) -> list[Tool]:
        return [
            make_workflow_cli_tool(
                worker_context=context,
                sandbox_task_key=self.task_id,
                benchmark_type="researchrubrics",
            )
        ]

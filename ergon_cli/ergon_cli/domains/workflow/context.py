from uuid import UUID

from ergon_cli.domains.workflow.models import WorkflowCommandContext


def build_workflow_context(
    *,
    run_id: str,
    task_id: str,
    execution_id: str,
    sandbox_task_key: str,
    benchmark_type: str,
) -> WorkflowCommandContext:
    return WorkflowCommandContext(
        run_id=UUID(run_id),
        task_id=UUID(task_id),
        execution_id=UUID(execution_id),
        sandbox_task_key=UUID(sandbox_task_key),
        benchmark_type=benchmark_type,
    )

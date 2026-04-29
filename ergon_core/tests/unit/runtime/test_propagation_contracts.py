from ergon_core.core.persistence.graph import status_conventions as graph_status
from ergon_core.core.application.tasks import execution as task_execution_service
from ergon_core.core.application.workflows import service as workflow_service
from ergon_core.core.application.workflows.orchestration import PropagationResult
from ergon_core.core.application.graph import propagation as workflow_propagation_service


def _source(module: object) -> str:
    loader = getattr(module, "__loader__")
    source = loader.get_source(module.__name__)
    assert source is not None
    return source


def test_graph_writers_do_not_use_task_execution_status_for_node_status() -> None:
    modules = [
        task_execution_service,
        workflow_service,
        workflow_propagation_service,
    ]
    forbidden_snippets = (
        "new_status=TaskExecutionStatus.",
        "initial_node_status=TaskExecutionStatus.",
    )

    offenders = [
        f"{module.__name__}: {snippet}"
        for module in modules
        for snippet in forbidden_snippets
        if snippet in _source(module)
    ]

    assert offenders == []
    assert graph_status.READY == "ready"


def test_propagation_result_does_not_expose_invalidated_targets() -> None:
    assert "invalidated_targets" not in PropagationResult.model_fields

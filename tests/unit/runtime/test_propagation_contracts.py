from ergon_core.core.persistence.graph import status_conventions as graph_status
from ergon_core.core.runtime.execution import propagation
from ergon_core.core.runtime.services import task_execution_service, task_propagation_service
from ergon_core.core.runtime.services import workflow_initialization_service


def _source(module: object) -> str:
    loader = getattr(module, "__loader__")
    source = loader.get_source(module.__name__)
    assert source is not None
    return source


def test_graph_writers_do_not_use_task_execution_status_for_node_status() -> None:
    modules = [
        propagation,
        task_execution_service,
        task_propagation_service,
        workflow_initialization_service,
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

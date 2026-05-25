from ergon_core.core.persistence.graph.models import SampleGraphEdge, SampleGraphNode
from ergon_core.core.persistence.telemetry.models import (
    SampleRecord,
    SampleResource,
    SampleTaskAttempt,
    SampleTaskEvaluation,
)


def test_runtime_tables_use_sample_vocabulary() -> None:
    assert SampleRecord.__tablename__ == "samples"
    assert SampleTaskAttempt.__tablename__ == "sample_task_attempts"
    assert SampleTaskEvaluation.__tablename__ == "sample_task_evaluations"
    assert SampleResource.__tablename__ == "sample_resources"
    assert SampleGraphNode.__tablename__ == "sample_graph_nodes"
    assert SampleGraphEdge.__tablename__ == "sample_graph_edges"

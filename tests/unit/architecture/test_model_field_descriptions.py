"""Guards for model field docs that must survive schema export."""

from ergon_core.core.dashboard.event_contracts import DashboardContextEventEvent
from ergon_core.core.persistence.context.event_payloads import (
    AssistantTextPayload,
    ThinkingPayload,
    ToolCallPayload,
    ToolResultPayload,
    UserMessagePayload,
)
from ergon_core.core.persistence.context.models import RunContextEvent
from ergon_core.core.persistence.graph.models import (
    RunGraphAnnotation,
    RunGraphMutation,
    RunGraphNode,
)
from ergon_core.core.persistence.telemetry.models import RunResource
from ergon_core.core.runtime.services.graph_dto import (
    GraphAnnotationDto,
    GraphEdgeDto,
    GraphMutationDto,
    GraphNodeDto,
)
from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)
from pydantic import BaseModel


def _description(model: type[BaseModel], field_name: str) -> str | None:
    return model.model_fields[field_name].description


def test_context_event_payload_field_docs_are_schema_metadata() -> None:
    assert _description(UserMessagePayload, "from_worker_key")
    assert _description(AssistantTextPayload, "turn_id")
    assert _description(AssistantTextPayload, "turn_token_ids")
    assert _description(AssistantTextPayload, "turn_logprobs")
    assert _description(ToolCallPayload, "turn_id")
    assert _description(ToolCallPayload, "turn_token_ids")
    assert _description(ToolCallPayload, "turn_logprobs")
    assert _description(ToolResultPayload, "tool_call_id")
    assert _description(ToolResultPayload, "result")
    assert _description(ThinkingPayload, "turn_id")
    assert _description(ThinkingPayload, "turn_token_ids")
    assert _description(ThinkingPayload, "turn_logprobs")


def test_dashboard_context_event_field_docs_are_schema_metadata() -> None:
    assert _description(DashboardContextEventEvent, "id")
    assert _description(DashboardContextEventEvent, "task_node_id")
    assert _description(DashboardContextEventEvent, "payload")


def test_graph_dto_field_docs_are_schema_metadata() -> None:
    assert _description(GraphNodeDto, "status")
    assert _description(GraphEdgeDto, "status")
    assert _description(GraphAnnotationDto, "id")
    assert _description(GraphAnnotationDto, "target_id")
    assert _description(GraphMutationDto, "id")
    assert _description(GraphMutationDto, "target_id")


def test_sqlmodel_field_docs_are_schema_metadata() -> None:
    assert _description(RunGraphNode, "instance_key")
    assert _description(RunGraphNode, "task_slug")
    assert _description(RunGraphNode, "status")
    assert _description(RunGraphNode, "assigned_worker_slug")
    assert _description(RunGraphNode, "parent_node_id")
    assert _description(RunGraphNode, "level")
    assert _description(RunContextEvent, "event_type")
    assert _description(RunContextEvent, "payload")
    assert _description(RunGraphAnnotation, "target_type")
    assert _description(RunGraphMutation, "mutation_type")
    assert _description(RunGraphMutation, "target_type")
    assert _description(RunResource, "kind")


def test_builtin_task_schema_field_docs_are_schema_metadata() -> None:
    assert _description(SWEBenchInstance, "hints_text")
    assert _description(SWEBenchTaskPayload, "hints_text")

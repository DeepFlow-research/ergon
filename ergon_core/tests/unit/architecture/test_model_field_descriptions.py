"""Guards for model field docs that must survive schema export."""

from ergon_core.core.views.dashboard_events.contracts import DashboardContextEventEvent
from ergon_core.core.shared.context_parts import (
    AssistantTextPart,
    ContextPartChunkLog,
    ThinkingPart,
    ToolCallPart,
    ToolResultPart,
    UserMessagePart,
)
from ergon_core.core.persistence.context.models import SampleContextEvent
from ergon_core.core.persistence.graph.models import (
    SampleGraphAnnotation,
    SampleGraphMutation,
    SampleGraphNode,
)
from ergon_core.core.persistence.telemetry.models import SampleRecord, SampleResource
from ergon_core.core.application.runtime.models import (
    GraphAnnotationDto,
    GraphEdgeDto,
    GraphMutationRecordDto,
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
    assert _description(UserMessagePart, "content")
    assert _description(AssistantTextPart, "content")
    assert _description(ToolCallPart, "tool_call_id")
    assert _description(ToolCallPart, "args")
    assert _description(ToolResultPart, "tool_call_id")
    assert _description(ToolResultPart, "content")
    assert _description(ThinkingPart, "content")
    assert _description(ContextPartChunkLog, "worker_binding_key")
    assert _description(ContextPartChunkLog, "turn_id")
    assert _description(ContextPartChunkLog, "token_ids")
    assert _description(ContextPartChunkLog, "logprobs")


def test_dashboard_context_event_field_docs_are_schema_metadata() -> None:
    assert _description(DashboardContextEventEvent, "id")
    assert _description(DashboardContextEventEvent, "task_id")
    assert _description(DashboardContextEventEvent, "payload")


def test_graph_dto_field_docs_are_schema_metadata() -> None:
    assert _description(GraphNodeDto, "status")
    assert _description(GraphEdgeDto, "status")
    assert _description(GraphAnnotationDto, "id")
    assert _description(GraphAnnotationDto, "target_id")
    assert _description(GraphMutationRecordDto, "id")
    assert _description(GraphMutationRecordDto, "target_id")


def test_sqlmodel_field_docs_are_schema_metadata() -> None:
    assert _description(SampleGraphNode, "instance_key")
    assert _description(SampleGraphNode, "task_slug")
    assert _description(SampleGraphNode, "status")
    assert _description(SampleGraphNode, "assigned_worker_slug")
    assert _description(SampleGraphNode, "parent_task_id")
    assert _description(SampleGraphNode, "level")
    assert _description(SampleContextEvent, "event_type")
    assert _description(SampleContextEvent, "payload")
    assert _description(SampleGraphAnnotation, "target_type")
    assert _description(SampleGraphMutation, "mutation_type")
    assert _description(SampleGraphMutation, "target_type")
    assert "Canonical runtime" in (_description(SampleRecord, "definition_id") or "")
    assert "Optional v2 experiment grouping tag" in (_description(SampleRecord, "experiment") or "")
    assert "Compatibility/display-only" in (_description(SampleRecord, "worker_team_json") or "")
    assert "Compatibility/display-only" in (_description(SampleRecord, "evaluator_slug") or "")
    assert "Compatibility/display-only" in (_description(SampleRecord, "sandbox_slug") or "")
    assert "Compatibility/display-only" in (_description(SampleRecord, "dependency_extras_json") or "")
    assert _description(SampleResource, "kind")


def test_builtin_task_schema_field_docs_are_schema_metadata() -> None:
    assert _description(SWEBenchInstance, "hints_text")
    assert _description(SWEBenchTaskPayload, "hints_text")

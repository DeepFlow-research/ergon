"""Infrastructure domain - sandbox, Inngest client, and cleanup.

This domain handles:
- Sandbox management (BaseSandboxManager)
- Inngest client configuration
- Infrastructure cleanup (run_cleanup)

Structure:
- sandbox.py: BaseSandboxManager and related types
- inngest_client.py: Inngest client singleton
- inngest_functions.py: run_cleanup
- events.py: RunCleanupEvent

Note: Import inngest_functions directly to avoid circular imports:
    from h_arcane.core._internal.infrastructure.inngest_functions import run_cleanup
"""

# Only export non-circular imports at module level
from h_arcane.core._internal.infrastructure.events import RunCleanupEvent
from h_arcane.core._internal.infrastructure.inngest_client import inngest_client
from h_arcane.core._internal.infrastructure.sandbox import (
    BaseSandboxManager,
    DownloadedFile,
    DownloadedFiles,
)
from h_arcane.core._internal.infrastructure.tracing import (
    CompletedSpan,
    NoopTraceSink,
    OtelTraceSink,
    SpanEvent,
    TraceContext,
    TraceSink,
    evaluation_criterion_context,
    evaluation_task_context,
    get_trace_sink,
    persist_outputs_context,
    safe_json_attribute,
    sandbox_file_op_context,
    sandbox_setup_context,
    task_execute_context,
    tool_action_context,
    trace_id_from_run_id,
    truncate_text,
    workflow_root_context,
    workflow_start_context,
    workflow_terminal_context,
    worker_execute_context,
)

__all__ = [
    # Sandbox
    "BaseSandboxManager",
    "DownloadedFile",
    "DownloadedFiles",
    "CompletedSpan",
    "NoopTraceSink",
    "OtelTraceSink",
    "SpanEvent",
    "TraceContext",
    "TraceSink",
    # Inngest
    "inngest_client",
    # Events
    "RunCleanupEvent",
    "evaluation_criterion_context",
    "evaluation_task_context",
    "get_trace_sink",
    "persist_outputs_context",
    "safe_json_attribute",
    "sandbox_file_op_context",
    "sandbox_setup_context",
    "task_execute_context",
    "tool_action_context",
    "trace_id_from_run_id",
    "truncate_text",
    "workflow_root_context",
    "workflow_start_context",
    "workflow_terminal_context",
    "worker_execute_context",
]

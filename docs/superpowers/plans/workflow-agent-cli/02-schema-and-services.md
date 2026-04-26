# 02 — Schema and Services

## Schema

### Migration

Create:

```text
ergon_core/migrations/versions/<revision>_add_copied_from_resource_id.py
```

Migration behavior:

- `upgrade()` adds nullable `copied_from_resource_id` UUID column to `run_resources`
- creates a self-referential foreign key to `run_resources.id`
- creates an index on `run_resources.copied_from_resource_id`
- `downgrade()` drops index, foreign key, and column

### Model Updates

Modify `ergon_core/ergon_core/core/persistence/telemetry/models.py`:

```python
class RunResourceKind(StrEnum):
    OUTPUT = "output"
    REPORT = "report"
    ARTIFACT = "artifact"
    SEARCH_CACHE = "search_cache"
    NOTE = "note"
    IMPORT = "import"
    """Copied snapshot materialized from another RunResource into a task workspace."""

class RunResource(SQLModel, table=True):
    # ...
    copied_from_resource_id: UUID | None = Field(
        default=None,
        foreign_key="run_resources.id",
        index=True,
    )
```

Modify `ergon_core/ergon_core/core/persistence/queries.py`:

```python
def append(
    self,
    *,
    run_id: UUID,
    task_execution_id: UUID,
    kind: str,
    name: str,
    mime_type: str,
    file_path: str,
    size_bytes: int,
    error: str | None,
    content_hash: str | None,
    metadata: JsonObject | None = None,
    copied_from_resource_id: UUID | None = None,
) -> RunResource:
    ...
```

Pass `copied_from_resource_id` into `RunResource(...)`.

## DTOs

Create `ergon_core/ergon_core/core/runtime/services/workflow_dto.py` with frozen Pydantic models:

- `WorkflowTaskRef`
- `WorkflowExecutionRef`
- `WorkflowResourceRef`
- `WorkflowDependencyRef`
- `WorkflowBlockerRef`
- `WorkflowNextActionRef`
- `WorkflowMaterializedResourceRef`

`WorkflowResourceRef` includes:

```python
resource_id: UUID
run_id: UUID
task_execution_id: UUID | None
node_id: UUID | None
task_slug: str | None
kind: str
name: str
mime_type: str
size_bytes: int
file_path: str
content_hash: str | None = None
copied_from_resource_id: UUID | None = None
created_at: datetime
```

`WorkflowMaterializedResourceRef` includes:

```python
source_resource_id: UUID
copied_resource_id: UUID | None
copied_from_resource_id: UUID
source_name: str
copied_name: str
source_content_hash: str | None
copied_content_hash: str | None
sandbox_path: str
dry_run: bool = False
source_mutated: bool = False
```

## Workflow Service

Create `ergon_core/ergon_core/core/runtime/services/workflow_service.py`.

This single service owns both read-only inspection and resource materialization policy. Keep it as one file for v1 because resource reads, visibility checks, and materialization share the same scope logic. Split later only if the implementation becomes hard to hold in context.

Required methods:

```python
class WorkflowService:
    def list_tasks(self, session: Session, *, run_id: UUID, parent_node_id: UUID | None = None) -> list[WorkflowTaskRef]: ...
    def get_task(self, session: Session, *, run_id: UUID, node_id: UUID | None, task_slug: str | None) -> WorkflowTaskRef: ...
    def get_latest_execution(self, session: Session, *, node_id: UUID) -> RunTaskExecution | None: ...
    def list_dependencies(self, session: Session, *, run_id: UUID, node_id: UUID, direction: Literal["upstream", "downstream", "both"]) -> list[WorkflowDependencyRef]: ...
    def list_resources(self, session: Session, *, run_id: UUID, node_id: UUID | None, scope: Literal["input", "upstream", "own", "children", "descendants", "visible"], kind: str | None = None, max_depth: int = 3, limit: int = 50) -> list[WorkflowResourceRef]: ...
    def read_resource_bytes(self, session: Session, *, run_id: UUID, resource_id: UUID, max_bytes: int) -> bytes: ...
    def get_task_blockers(self, session: Session, *, run_id: UUID, node_id: UUID) -> list[WorkflowBlockerRef]: ...
    def get_next_actions(self, session: Session, *, run_id: UUID, node_id: UUID, manager_capable: bool) -> list[WorkflowNextActionRef]: ...
    async def materialize_resource(
        self,
        session: Session,
        *,
        run_id: UUID,
        current_node_id: UUID,
        current_execution_id: UUID,
        sandbox_task_key: UUID,
        benchmark_type: str,
        resource_id: UUID,
        destination: str | None,
        dry_run: bool,
    ) -> WorkflowMaterializedResourceRef: ...
```

For `input` and `upstream`, use incoming edges to the current node, get each source node's latest completed execution, then collect `RunResource` rows for those execution IDs.

For `visible`, list current-run resources allowed by policy, including resources from divergent DAG branches. This must still exclude eval/private/system resources and must be capped by `limit`.

`materialize_resource(...)` should use the benchmark's sandbox manager class and existing `BaseSandboxManager.upload_file(...)` to write into the live E2B sandbox. Do not create a new low-level E2B upload primitive.

The service must reject:

- resource IDs not in the injected current run
- invisible resources
- eval/private/system resources
- absolute destinations
- `..` path traversal
- symlink escapes
- paths outside `/workspace`
- destination collisions unless explicit versioning/overwrite behavior is implemented

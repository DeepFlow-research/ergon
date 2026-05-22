# PR 07: Sandbox Resource Publishing Boundary

## What

Split sandbox filesystem/blob adapters from application resource append/dedup
semantics.

## Why

`core/infrastructure/sandbox/resource_publisher.py` currently knows how to
read sandbox files, write blobs, and decide how `RunResource` rows are appended
or deduplicated. The first two are infrastructure adapter work. The resource
row policy is application behavior and should be shared by jobs and future
resource flows.

## How

- Keep filesystem/blob details in infrastructure:
  `_list_sandbox_dir()`, `_read_sandbox_file()`, `_write_blob()`, and
  `_blob_path()`.
- Create `core/application/ports/resources.py` for sandbox file/blob adapter
  protocols if the concrete infrastructure dependency would otherwise leak.
- Create `core/application/resources/publishing.py` with
  `RunResourcePublishService`.
- Move `RunResource` append/dedup writes from infrastructure into that service.
- Update `persist_outputs` job to call the application service with injected
  sandbox reader/blob writer implementations.
- Add architecture tests preventing infrastructure sandbox modules from adding
  `RunResource` rows directly.

## Plan

1. Add characterization tests for current `SandboxResourcePublisher.sync()` and
   `publish_value()` row behavior.
2. Add application service tests for resource append/dedup semantics.
3. Define narrow ports for listing/reading sandbox files and writing blobs.
4. Implement `RunResourcePublishService`.
5. Move DB writes out of infrastructure.
6. Update `application/jobs/persist_outputs.py` or the later job module to use
   the service.
7. Leave infrastructure sandbox code responsible only for filesystem/blob
   adapter behavior.
8. Add architecture test coverage for the boundary.

## Acceptance Criteria

- Sandbox infrastructure no longer appends `RunResource` rows directly.
- `RunResourcePublishService` owns resource append/dedup semantics.
- Persist-output behavior is unchanged.
- Infrastructure remains responsible for E2B/filesystem/blob operations.
- Architecture tests prevent resource persistence policy from moving back into
  infrastructure.

## Tests

```bash
pytest ergon_core/tests/unit/resources -q
pytest ergon_core/tests/unit/runtime/test_persist_outputs.py -q
pytest ergon_core/tests/unit/architecture -q
rg -n "RunResource\\(|session\\.add\\(.*RunResource|resource_publisher" ergon_core/ergon_core/core/infrastructure
```


# PRD 02: Shared Context Contract And Domain Package Deletion

## Goal

Delete the anemic `core/domain` package and move the context stream contract to
a narrow shared home.

## Target State

Context stream schemas live at:

```text
ergon_core/core/shared/context_parts.py
```

They are treated as a cross-cutting contract used by:

- public worker/API contracts;
- persistence context events;
- dashboard/schema generation;
- RL extraction;
- tests.

`core/domain/` does not exist unless a future RFC introduces real pure-domain
logic.

## Required Moves

- Move `core/domain/generation/context_parts.py` to
  `core/shared/context_parts.py`.
- Add `ContextEventType` to `core/shared/context_parts.py`.
- Delete `WorkerYield = ContextPartChunk` while moving the file. Worker stream
  annotations should use `ContextPartChunk` directly.
- Update imports from `ergon_core.core.domain.generation.context_parts` to
  `ergon_core.core.shared.context_parts`.
- Update imports from `ergon_core.core.persistence.context.event_payloads` to
  `ergon_core.core.shared.context_parts`.
- Replace every `ContextEventPayload` annotation with `ContextPartChunkLog`.
- Delete `core/domain/generation/__init__.py`, `core/domain/__init__.py`, and
  the `core/domain/` package after the move. The package has no source besides
  `generation/context_parts.py`.
- Delete `core/persistence/context/event_payloads.py`. It only re-exports the
  context payload alias and event type literal. The event type moves to shared;
  the payload alias dies.
- Update architecture tests to assert `core/domain` is absent or empty.

## Import Updates

Production imports that move to `core.shared.context_parts`:

- `api/worker/worker.py`
- `core/rl/extraction.py`
- `core/application/jobs/worker_execute.py`
- `core/application/context/events.py`
- `core/persistence/context/models.py`
- `core/application/read_models/models.py`
- `core/infrastructure/dashboard/event_contracts.py`
- `core/infrastructure/dashboard/emitter.py`

Test and fixture imports that move to `core.shared.context_parts`:

- `ergon_core/tests/unit/persistence/test_context_event_repository.py`
- `ergon_core/tests/unit/runtime/test_context_event_contracts.py`
- `ergon_core/tests/unit/architecture/test_model_field_descriptions.py`
- `ergon_core/tests/unit/runtime/test_import_boundaries.py`
- `ergon_core/tests/unit/runtime/test_worker_execute_stream_contract.py`
- `ergon_core/tests/unit/state/test_context_part_stream.py`
- `tests/fixtures/smoke_components/smoke_base/leaf_base.py`
- `tests/fixtures/smoke_components/smoke_base/recursive.py`
- `tests/fixtures/smoke_components/smoke_base/worker_base.py`

Architecture tests to update:

- `ergon_core/tests/unit/architecture/test_public_api_boundaries.py` should
  expect `core/shared/context_parts.py`.
- `ergon_core/tests/unit/architecture/test_core_schema_sources.py` should stop
  requiring `domain` as a layout root and should assert `core/domain` is absent.

## Non-Goals

- Do not change the serialized context event payload shape.
- Do not redesign worker context streaming.
- Do not move unrelated shared schemas into `core/shared`.

## Acceptance Criteria

- No production import references `core.domain.generation.context_parts`.
- No production or test code references `WorkerYield` or `ContextEventPayload`.
- `RunContextEvent.parsed_payload()` still validates persisted context payloads.
- Dashboard context event contracts still generate successfully.
- RL extraction tests still consume context events.
- Architecture tests prevent reintroducing a nominal `domain/` package for
  shared schemas.

## Evidence

- [`../audits/current-structure.md`](../audits/current-structure.md)
- [`../audits/persistence-boundary-audit.md`](../audits/persistence-boundary-audit.md)

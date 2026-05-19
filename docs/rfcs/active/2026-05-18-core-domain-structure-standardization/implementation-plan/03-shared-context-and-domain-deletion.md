# PR 03: Shared Context Contract And Domain Deletion

## What

Move context stream schemas from the nominal `core/domain` package into
`core/shared/context_parts.py`, delete redundant aliases, and remove the
`core/domain` package.

## Why

`core/domain` currently contains one shared contract and no real domain logic.
The context stream schema is used by public worker contracts, persistence,
dashboard events, RL extraction, and tests. `shared/` is the correct home, but
only if the aliases `WorkerYield` and `ContextEventPayload` die at the same
time.

## How

- Move `core/domain/generation/context_parts.py` to
  `core/shared/context_parts.py`.
- Move `ContextEventType` from
  `core/persistence/context/event_payloads.py` into
  `core/shared/context_parts.py`.
- Replace `WorkerYield` with `ContextPartChunk`.
- Replace `ContextEventPayload` with `ContextPartChunkLog`.
- Delete `core/persistence/context/event_payloads.py`.
- Delete `core/domain/generation/__init__.py`, `core/domain/__init__.py`, and
  the `core/domain/` package.

## Plan

1. Add an architecture test asserting `core/domain` does not exist.
2. Add a source test asserting `WorkerYield` and `ContextEventPayload` have no
   production or test references.
3. Move the context part models into `core/shared/context_parts.py`.
4. Update production imports from:
   - `core.domain.generation.context_parts`
   - `core.persistence.context.event_payloads`
5. Update test and fixture imports listed in PRD 02.
6. Replace type annotations that use aliases with the real model names.
7. Delete the old domain and persistence alias modules.
8. Regenerate dashboard/event schemas if the contract export path changes.

## Acceptance Criteria

- No import references `core.domain.generation.context_parts`.
- No import references `core.persistence.context.event_payloads`.
- No code references `WorkerYield` or `ContextEventPayload`.
- `RunContextEvent.parsed_payload()` still validates stored payloads.
- RL extraction still reads context events.
- `core/domain` is absent.

## Tests

```bash
pytest ergon_core/tests/unit/persistence/test_context_event_repository.py -q
pytest ergon_core/tests/unit/runtime/test_context_event_contracts.py -q
pytest ergon_core/tests/unit/runtime/test_worker_execute_stream_contract.py -q
pytest ergon_core/tests/unit/state/test_context_part_stream.py -q
pytest ergon_core/tests/unit/architecture -q
rg -n "domain\\.generation\\.context_parts|persistence\\.context\\.event_payloads|WorkerYield|ContextEventPayload" ergon_core tests
```


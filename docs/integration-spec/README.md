# Integration Test Specification

This folder defines the integration tier's intended behaviour as the authoritative source of truth for what the system must do. The workflow is: (1) violated assumptions and coverage gaps are identified here; (2) integration tests are written to match this spec — tests for known-broken behaviour are marked `xfail(strict=True)`; (3) production code is fixed until the xfail tests go green and the markers are explicitly removed; (4) E2E tests are updated to assert the same invariants in higher-fidelity environments.

## Folder Contents

| File | Description |
|------|-------------|
| `1-audit.md` | Audit of the current `tests/integration/` directory: what exists, what it actually tests, and its structural defects. |
| `2-control-flow-spec.md` | System model and the complete control-flow test specification: nine primary flows plus edge cases, with exact Postgres state assertions. |
| `3-structural-checks.md` | Static analysis, schema, registry, and infrastructure tests (categories 10–18) that verify structural correctness without running the full event pipeline. |
| `4-violated-assumptions.md` | Findings A–L: behaviours the production code implements incorrectly relative to the intended domain model, each with a fix and the integration test assertion that would catch it. |
| `5-test-harness.md` | Test harness design: stub workers, shared assertion helpers, fixture pattern, and xfail conventions. |

## Priority Order

| Priority | Category | Tier | Value |
|----------|----------|------|-------|
| 1 | Fix 3 uncollected tests (`testresolve_*`) | Integration | Critical bug — tests have never run |
| 2 | Event subscriber coverage | Unit | Catches live `criterion/evaluate` orphan |
| 3 | Nine control flows | Integration | Core runtime correctness, zero coverage today |
| 4 | Inngest catalog + registry integrity | Unit | Cheap, high signal |
| 5 | DB schema reflection | Integration | Catches migration drift |
| 6 | Event payload round-trips | Unit | Catches serialisation bugs before they hit wire |
| 7 | Toolkit tool name uniqueness | Unit | Prevents silent shadowing |
| 8 | ABC compliance | Unit | Catches broken registrations at test time |
| 9 | Concurrency race | Full-stack | Validates the system's critical idempotency guard |
| 10 | Container builds | Docker/nightly | Catches broken sandbox images before E2E |

## xfail Conventions

Tests for known-broken behaviours (violated assumptions) are marked:

```python
@pytest.mark.xfail(strict=True, reason="violated assumption X: <description>")
```

`strict=True` means if the test accidentally passes, CI turns it into an error — the marker must be explicitly removed once the fix is confirmed and the test is observed green on a clean run.

The reason string must cite the assumption letter (A–L) so it is traceable to `4-violated-assumptions.md`.

Example:

```python
@pytest.mark.xfail(strict=True, reason="violated assumption K: restart_task does not reset containment subtree")
def test_restart_resets_all_containment_children(): ...
```

## Current Status

- Real integration tests today: 1 (`test_smoke_harness` — HTTP status codes only, no Postgres state)
- Violated assumptions identified: 12 (A–L), all requiring either a production code fix, a schema migration, or both

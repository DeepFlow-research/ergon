# 07 — Test strategy

> The test surface that distinguishes "v2 implementation matches v2
> spec" from "v2 has the same kinds of drift v1 had". The audit failure
> mode v1 hit was: tests passed, the framework appeared to work, the
> non-functional code paths went undetected because nothing exercised
> them or guarded against their reintroduction. v2's test strategy
> closes that hole.
>
> Three kinds of tests, each owning a different invariant class:
> architecture-guard tests, the walkthrough integration test, and the
> regression net for v1 audit findings.
>
> See [`../2026-05-08-authoring-api-redesign/08-cleanup-audit.md`](../2026-05-08-authoring-api-redesign/08-cleanup-audit.md)
> for the full set of v1 findings; this doc spec'es the tests that
> would have caught each, and now keep them caught.

## Test layers

| Layer | Owns | Runs | Failure means |
|---|---|---|---|
| **Architecture guards** | "no module imports X"; "every public class has Y"; "deleted symbols are deleted" | unit suite, on every PR | a structural rule was violated |
| **XFail ledgers (executable program)** | landing-PR-keyed `xfail(strict=True)` cases for every v2 invariant and every v1 dead path; markers removed by the PR that lands the invariant | unit suite, on every PR | an invariant landed early without ledger update (XPASS) or regressed (FAIL) |
| **Walkthrough smoketests (observable effects)** | unit-level effect tests that drive a public entry point and assert resulting DB/event state matches the spec — outcomes only, never call-graph mocks | unit suite, on every PR | spec drifted from behaviour at the unit level |
| **Walkthrough integration** | end-to-end flow from author code through worker_execute to terminal state matches the canonical `04-walkthrough.md` step-by-step | integration suite, on every PR | runtime behaviour drifted from the spec |
| **Regression net (v1 audit)** | every concrete bug class the v1 audit found has a test that fails when reintroduced | unit suite | the same v1 bug is back |
| **Standard unit + integration tests** | per-module behavior of `prepare_run`, `worker_execute`, `WorkerContext`, etc. | unit + integration | normal regression |

Standard tests are out of scope for this doc — they're the same kind
the v1 implementation already had. This doc focuses on the layers v1
was *missing* that allowed drift to ship.

## §0 — The four-file ledger pattern

The v2 implementation program is encoded as four executable ledger files
landed in PR 0 and PR 1 alongside the existing transition guard. Each
later PR removes the appropriate `xfail` markers as it lands its
invariant; PR 11 verifies that all four ledgers are empty of pending
markers. Together they act as the machine-readable twin of the prose PR
plan in [`09-implementation-plan/`](09-implementation-plan/).

| File | Lands in | Asserts | Marker scheme |
|---|---|---|---|
| [`test_v2_transition_ledger.py`](09-implementation-plan/01-pr-00-transition-ledger.md) | PR 0 | Old symbols are still allowed (negative) | One row per symbol with `owner_pr` / `deletion_pr` |
| [`test_v2_final_state_ledger.py`](09-implementation-plan/01-pr-00-transition-ledger.md) | PR 0 | v2 invariants must hold at the end (positive) | `pytest.mark.xfail(reason="PR N", strict=True)` — markers in `_XFAIL_BY_NAME` |
| [`test_dead_path_audit.py`](09-implementation-plan/01-pr-00-transition-ledger.md) | PR 0 | v1 dead paths stay callerless until deleted | `pytest.mark.xfail(strict=True)` — markers in `_XFAIL_BY_SYMBOL` |
| [`test_repository_layer_conventions.py`](09-implementation-plan/01b-pr-0-5-repository-standard.md) | PR 0.5 | Repository class/file/method shape per § 0.5 | `pytest_collection_modifyitems` applies markers from `_KNOWN_VIOLATORS` |
| [`test_repository_companion_files.py`](09-implementation-plan/01b-pr-0-5-repository-standard.md) | PR 0.5 | `errors.py` + DTO location per § 0.5 | Same |
| [`test_no_dead_repository_methods.py`](09-implementation-plan/01b-pr-0-5-repository-standard.md) | PR 0.5 | Every public repo method has a production caller | `pytest.mark.xfail` — markers in `_KNOWN_UNUSED_FOR_NOW` |
| [`test_walkthrough_smoketest.py`](09-implementation-plan/02-pr-01-run-tier-task-snapshot.md) | PR 1 | Observable effects of the v2 happy path | `pytest.mark.xfail` per case, removed by landing PR |
| [`test_identity_invariants.py`](09-implementation-plan/02-pr-01-run-tier-task-snapshot.md) | PR 1 | `task_id`/`execution_id`/`sandbox_id` flow per §2 | `pytest.mark.xfail` per case, removed by landing PR |

**`strict=True` is load-bearing.** It surfaces unexpected passes — if a
refactor lands an invariant ahead of its scheduled PR, the ledger fails
and the author must update the marker dict in the same commit. Without
`strict`, drift between code and ledger is silent.

**Why effect-based smoketests, not call-graph mocks.** The audit failure
mode v1 hit ("this helper was supposed to be called, wasn't") is
tempting to catch with `mock.assert_called_with(...)` tests. We
deliberately don't. Call-graph mocks test how code is structured, not
whether it works; the moment someone extracts a helper or moves logic
between layers, the test breaks even though behaviour is unchanged.
Effect-based smoketests drive the public entry point and observe the
resulting database / event-bus state — they survive refactors, and they
read like prose for an engineer learning the topology.

**Why xfail(strict=True), not skip or markers-as-todo.** A skipped
test provides no signal until someone manually unskips it; an
`xfail(strict=True)` is *active* — every CI run rechecks whether the
invariant has been satisfied early, and an unexpected pass fails the
build. The ledger is the v2 program's progress meter, automated.

**The completion bar.** The v2 program is complete when both
`_XFAIL_BY_NAME` and `_XFAIL_BY_SYMBOL` are empty dicts and every case
in the walkthrough smoketest and identity invariants is unmarked. PR 11
adds two explicit assertions
(`test_no_v2_invariants_are_still_xfailed`,
`test_no_dead_paths_are_still_xfailed`) that fail the build until both
dicts are empty.

## §0.5 — Repository layer standard

Every data-access repository in `ergon_core/core/**` follows the same
file layout and naming conventions. The standard is enforced by three
architecture-guard tests that land in **PR 0.5**
(`01b-pr-0-5-repository-standard.md`); subsequent PRs flip the xfails
for the current violators.

### Package shape

```
<package>/
    __init__.py       # explicit __all__ re-exports
    repository.py     # the Repository class(es); data access only
    models.py         # SQLModel tables + Pydantic request/response DTOs
    errors.py         # custom exception classes (only if package raises)
    service.py        # optional: use-case orchestrator composing repo calls
```

### The 10 rules

1. **Class name ends with `Repository`** (e.g. `WorkflowGraphRepository`,
   not `GraphRepo` or `Graph`).
2. **File is `repository.py` (singular)**, even when multiple Repository
   classes share a file. The current `telemetry/repositories.py` is a
   known violator fixed by PR 1.
3. **Methods take `session` as the first non-self positional arg.**
   Consistent across the codebase already; the rule pins it.
4. **Write methods are async; reads may be sync.** Write-prefix
   heuristic: methods starting with `add_`, `update_`, `remove_`,
   `delete_`, `set_`, `create_`, `append_`, `insert_`, `persist_` are
   writes. Async reads are required only when the method performs
   genuine I/O — `graph_repo.node` after PR 5 attaches a live sandbox,
   which is the textbook case.
5. **Repositories never call `session.commit()`.** Transactions belong
   to the caller (the service or job body), not the data layer.
6. **Repositories never import from `core.infrastructure.*`.** The
   data layer stays framework-agnostic so it can be reused in training
   pipelines, replay systems, and test harnesses that don't run inside
   Inngest. See `graph/errors.py` docstring for the rationale.
7. **Repositories return typed views or domain objects, never
   `dict[str, Any]`.** The boundary type for serialized JSON is
   `TaskDefinitionJson = dict[str, JsonValue]` (see PR 2); after
   inflation, the repo returns the typed Pydantic object.
8. **Custom exceptions live in `errors.py`.** If any file in the
   package raises something beyond stdlib, `errors.py` must exist.
   Generic `raise ValueError(...)` in a repo is a typed-error gap
   — callers can't catch specifically. The current
   `experiments/repository.py` raises `ValueError`; PR 7 fixes it.
9. **Request/response DTOs (Pydantic BaseModels) live in `models.py`,
   not in `repository.py`.** The current `telemetry/repositories.py`
   defines `CreateTaskEvaluation` inline; PR 4 moves it.
10. **Every public Repository method must have a non-test production
    caller.** The dead-method audit catches v1's `Worker.from_buffer`
    failure mode scoped to the layer where it matters.

### Why scope dead-code detection to the repository layer

Tree-wide dead-code tooling (e.g. `vulture`) has decent precision but
trips repeatedly on Inngest functions registered by string, Pydantic
validators (`@field_validator`, `@model_serializer`), pytest fixtures,
and dynamic dispatch. The signal-to-noise tanks and the whitelist
drifts.

A hand-rolled "every public Repository method has a production caller"
test is scoped tightly to the layer where the v1 audit found real dead
helpers. It catches 80% of the value at 10% of the cost. If we later
want broader dead-code detection, a focused `vulture` config + `ruff`
rules is the path — but that's a separate decision.

## §0.6 — No type-checker circumventors

The v2 program treats type-laundering as a code smell. Three patterns
are banned in production code under `ergon_core`, `ergon_builtins`,
`ergon_cli`:

1. **`getattr(obj, "attribute_name", default)`** — string-based
   attribute access the type checker cannot reason about. If the
   attribute might not exist, the typing contract is wrong, not the
   call site. Fix the source: add the field with a typed default, or
   wrap the foreign object in a `Protocol`.

2. **`hasattr(obj, "attribute_name")`** — same shape, same reasoning.
   Use `isinstance(obj, SomeProtocol)` or split call sites by type.

3. **Untyped `dict.get("key")` chains for *structured* values** — e.g.
   `created_by=str(d.get("x")) if "x" in d else None`. If the framework
   cares about the field, it belongs as a first-class typed model
   field. `dict[str, Any]` metadata is for opaque user-provided
   payloads, not for fields the framework reads.

### Narrow exemptions (each requires a `# typing:` comment)

- **Dynamic qualname walking.** The `_import_component(path)` helper
  walks a string like `"module.sub:Class.Inner"` to resolve a class.
  The `getattr(obj, part)` call inside the walk is genuinely
  string-based because the path components are user-controlled
  discriminator values. Each line carries a
  `# typing: dynamic qualname walk` comment.

- **External library type-erasure boundaries.** When the foreign object
  comes from a third-party SDK whose interface we don't control (e2b
  `AsyncSandbox`, etc.), wrap it in a `Protocol` defined in
  `ergon_core/api/...` and pass *typed* objects across our layers. A
  `getattr` on the raw SDK object inside the wrapper is acceptable
  with a `# typing: <library> SDK boundary` comment.

- **Test code asserting symbol absence.** `assert not hasattr(Cls, "x")`
  in the dead-symbol guards is the load-bearing form of "this symbol
  is gone." Tests are exempt by path.

### Architecture guard

`ergon_core/tests/unit/architecture/test_no_type_circumventors.py`
lands in PR 0 (alongside the transition / final-state ledgers) and
greps production code for `getattr(` and `hasattr(`. Each hit must be
either:

- Inside a test file (path-exempt).
- Adjacent to a `# typing:` comment naming the exemption category.
- In `_KNOWN_EXEMPTIONS` with a one-line justification and a landing
  PR (mirror of `_XFAIL_BY_NAME`).

PR 11 asserts `_KNOWN_EXEMPTIONS` is empty of "to be removed" entries
— only the truly-legitimate exemptions remain.

## §1 — Architecture-guard tests

These run at unit-test speed (no DB, no sandbox) and enforce static
properties of the source tree. They live at
`ergon_core/tests/unit/architecture/`.

### `test_public_api_target_structure.py` — the public surface

Already exists in v1 in skeleton form. v2 hardens it.

Asserts:

- `ergon_core.api` re-exports exactly the types in
  [`01-api-surface.md`](01-api-surface.md) "Two surfaces, one public
  package" — no more, no less.
- Every type in `ergon_core.api` either *is* a `BaseModel` subclass
  with a `from_definition` classmethod, *or* is one of the listed
  exception classes.
- `WorkerContext` has exactly the curated method set listed in
  [`03-runtime.md` "The v1 WorkerContext surface"](03-runtime.md).
  Adding a method without a corresponding RFC update fails the test.

### `test_runtime_does_not_read_definition_tables.py` — the read boundary

Enforces [`02-persistence-layer.md` §4](02-persistence-layer.md):

```python
def test_runtime_does_not_import_definition_orm() -> None:
    """No module under ergon_core/core/application/runtime/ may import
    DefinitionRepository, ExperimentDefinitionTask, or any other
    definition-tier ORM class. The runtime reads exclusively from
    run-tier tables.

    Allowed exception: prepare_run.py — it's the boundary that copies
    definition→run at run-launch.
    """
    forbidden = {
        "DefinitionRepository",
        "ExperimentDefinitionTask",
        "ExperimentDefinition",
        "ExperimentDefinitionEdge",
    }
    runtime_root = Path("ergon_core/core/application/runtime/")
    for py_file in runtime_root.rglob("*.py"):
        if py_file.name == "prepare_run.py":
            continue
        text = py_file.read_text()
        for symbol in forbidden:
            assert symbol not in text, (
                f"{py_file} imports {symbol}; runtime must read run-tier only"
            )
```

The test is intentionally textual (substring match on imports) rather
than AST-based — false positives are unlikely (these names are
distinctive) and false negatives mean someone deliberately routed
around the rule, which the next code review should catch.

### `test_no_deleted_symbols.py` — the deletion floor

Every symbol the v2 audit deleted has a corresponding "this symbol
must not exist" assertion. The list:

```python
DELETED_SYMBOLS = {
    # v2 deletions per 09-implementation-plan.md
    "ergon_core.core.persistence.saved_specs": "package",
    "_persist_single_sample_workflow_definition": "function",
    "Worker.from_buffer": "classmethod",
    "CriterionExecutor": "Protocol",
    "InngestCriterionExecutor": "Protocol",
    "_prepare_definition": "function",
    "definition_task_id": "column",                 # checked via Alembic schema
    "ExperimentRecord": "ORM class",                # checked via SQLAlchemy registry
    "EvaluateTaskRunRequest": "dataclass",          # replaced by TaskEvaluateRequest
    "terminate_sandbox_by_id": "function",
}
# evaluate_task_run is intentionally NOT here — it survives reshaped per Δ.4.
KEPT_RESHAPED_SYMBOLS = {
    "evaluate_task_run": "Inngest function (thin id-only payload)",
    "TaskEvaluateRequest": "payload class",
}

def test_deleted_symbols_stay_deleted() -> None:
    """For every entry in DELETED_SYMBOLS, ensure no module under
    ergon_core, ergon_cli, ergon_builtins still defines or imports it."""
```

Each entry has its own targeted assertion that picks the right
inspection technique (import probe for packages/classes, source-text
search for functions, schema introspection for columns/tables).

### `test_cli_define_routes_through_persist_definition.py` — the CLI path

Enforces [`05-cli-authoring-interface.md`](05-cli-authoring-interface.md):

```python
def test_cli_define_calls_persist_definition() -> None:
    """ergon_cli.commands.define.define() must call
    persist_definition(experiment), not any helper function.

    Implementation: monkey-patch persist_definition with a recording
    spy, invoke define() against a known slug, assert the spy was
    called exactly once with an Experiment instance whose benchmark
    matches the slug factory's output.
    """

def test_cli_define_does_not_write_to_saved_specs() -> None:
    """Stronger: invoke define() against an in-memory test database
    and assert the saved_specs table either does not exist (preferred)
    or has zero rows after the call (acceptable transitional state).
    """
```

### `test_inngest_evaluate_task_run_thin_payload.py` — fanout shape

Enforces [`06-inngest-event-contracts.md`](06-inngest-event-contracts.md)
Δ.4 / Δ.5. The Inngest function registry **must** contain a function
handling `task/evaluate` events, and it must use the thin `TaskEvaluateRequest`
payload (not v1's `EvaluateTaskRunRequest`):

```python
def test_evaluate_task_run_is_registered_with_thin_payload() -> None:
    """The per-evaluator fanout target survives in v2 per Δ.4. It must
    be registered, and its payload must be the id-only TaskEvaluateRequest.
    """
    from ergon_core.runtime.inngest import registered_functions
    events = {f.event for f in registered_functions}
    assert "task/evaluate" in events, (
        "evaluate_task_run must remain registered — see Δ.4 in "
        "08-decisions-log.md"
    )
    payload_types = {f.payload_type.__name__ for f in registered_functions
                     if f.payload_type is not None}
    assert "TaskEvaluateRequest" in payload_types
    assert "EvaluateTaskRunRequest" not in payload_types  # v1 payload deleted


def test_worker_execute_fans_out_via_step_invoke() -> None:
    """Static check on worker_execute.py: must use ctx.step.invoke to
    fan out to evaluate_task_run, wrapped in asyncio.gather, with the
    sandbox release in finally."""
    body = read_source("ergon_core/core/application/jobs/worker_execute.py")
    assert "ctx.step.invoke" in body
    assert "evaluate_task_run" in body
    assert "asyncio.gather" in body
    assert "finally:" in body
```

### `test_sandbox_release_path.py` — the lifecycle owner

Enforces [`03-runtime.md` "Cross-job sandbox lifetime"](03-runtime.md):

```python
def test_worker_execute_releases_sandbox_in_finally() -> None:
    """Static check on worker_execute.py: the function body must
    contain a try/finally where the finally clause calls
    lifecycle_hub.release(sandbox).

    AST-based — locate the worker_execute function definition, walk
    to its try/finally, assert release(sandbox) is in the finally
    suite. (Brittle to refactoring but exactly what we want for an
    architecture rule that's load-bearing.)
    """

def test_no_other_release_callsites() -> None:
    """No module other than worker_execute.py and lifecycle.py itself
    may call lifecycle_hub.release(...). Guards against
    re-introduction of v1's per-run cleanup-as-primary-release path.
    """
```

## §2 — Walkthrough integration test

The single source of truth for "what running end-to-end looks like" is
[`04-walkthrough.md`](04-walkthrough.md). v2 ships *one* integration
test that executes that exact walkthrough end-to-end — author code,
real Postgres (via test container), real `worker_execute` body, real
`SandboxLifecycleHub`, fake `Sandbox` subclass with deterministic
behavior. If this test passes, the framework matches its spec.

```python
# tests/integration/test_walkthrough.py

@pytest.mark.integration
async def test_walkthrough_end_to_end(test_db, fake_sandbox_runtime) -> None:
    """Step-by-step replication of 04-walkthrough.md.

    Author-side:
      - Construct the same MiniBenchmark with 4 tasks, 1 criterion, fake sandbox.
      - Wrap in Experiment.
      - Call persist_definition(experiment).

    Framework-side:
      - Assert one row written to experiment_definitions.
      - Assert four rows written to experiment_definition_tasks.
      - Assert dependency edges match.

    Runtime:
      - Call launch_run(definition_id).
      - Drive the Inngest event loop synchronously (test driver).
      - Assert events fire in the expected order:
          workflow/started → 1× prepare_run
          task/ready × 1   (root task only — others depend)
          task/worker-execute × 1
          task/completed × 1
          task/ready × 3   (newly-ready dependents)
          ... etc., until all 4 tasks complete
          workflow/completed × 1

    Persistence:
      - For each task, assert run_graph_nodes row reaches RUNNING then
        SUCCEEDED, with task_json matching the definition copy.
      - For each task, assert exactly one task_executions row.
      - For each task, assert exactly one criterion_outcomes row.

    Sandbox lifecycle:
      - Assert acquire was called exactly 4 times (one per task).
      - Assert release was called exactly 4 times.
      - Assert each release happened AFTER the criterion outcome was
        persisted for the same (run_id, task_id).
      - Assert NO release was called from the run_cleanup path
        (cleanup is a no-op when worker_execute did its job).

    Final state:
      - runs.status == SUCCEEDED
      - all 4 run_graph_nodes are SUCCEEDED
    """
```

This test is verbose (it asserts O(20) properties), and that's
exactly the point — it pins the *flow*, not just the outcome. A
reviewer can mechanically diff the asserted sequence against
[`04-walkthrough.md`](04-walkthrough.md) and verify they match. Any
drift between spec and behavior shows up as a test failure with a
clear "expected event N, got event M" message.

### Variants

The same test scaffold parameterises four variants:

1. **Happy path** (above) — all 4 tasks succeed.
2. **Failure cascade** — task 2 fails; assert task 3 (which depends
   on task 2) is cancelled; assert run terminates with status FAILED.
3. **Dynamic spawn** — task 1 spawns task 1.a; assert 1.a is born
   into `run_graph_nodes` only (no `experiment_definition_tasks` row);
   assert it runs through the same worker_execute path; assert
   sandbox lifecycle is independent of parent.
4. **Restart task** — after task 1 succeeds, call
   `restart_task(task_1_id)`; assert a new `execution_id` is minted
   and a new sandbox is acquired/released.

Each variant is a parameterized version of the base test; the
parameterisation makes the variant-specific assertions explicit and
the shared assertions (sandbox lifecycle, no double-release) shared.

## §3 — Regression net for v1 audit findings

For every concrete bug class the v1 audit found, a unit test exists
that *fails when the bug is reintroduced*. The list maps 1:1 to v1
audit's `08-cleanup-audit.md` findings.

```python
# tests/unit/regression/test_v1_audit_findings.py

def test_no_double_path_to_persist_definition() -> None:
    """v1 had _persist_single_sample_workflow_definition writing to
    saved_specs in parallel with persist_definition writing to
    experiment_definitions. There must be exactly one persistence
    function reachable from authoring code."""

def test_run_graph_node_holds_inline_task_json() -> None:
    """v1 'works in spirit' but in practice the runtime resolved
    sandbox/worker by reading task_json from
    experiment_definition_tasks instead of run_graph_nodes. After
    prepare_run, the run row's task_json must be self-sufficient."""

def test_dynamic_subtask_has_no_definition_row() -> None:
    """v1 wrote a synthetic experiment_definition_tasks row when a
    worker spawned a subtask. v2 does not."""

def test_sandbox_released_after_inline_criteria() -> None:
    """v1 acquired sandbox in worker_execute, then split criteria into
    a separate Inngest function that did not have access to the
    sandbox at all. The release happened on a separate cleanup path
    that ran on every event-fire including ones that should not have
    released. v2: sandbox released in worker_execute's finally,
    after the synchronous fanout's asyncio.gather returns."""

def test_worker_has_no_from_buffer_constructor() -> None:
    """v1 had Worker.from_buffer(buffer: bytes) for protocol-buffer
    inflation. No callers ever existed. Deleted in v2."""

def test_no_criterion_executor_protocol() -> None:
    """v1 defined a CriterionExecutor Protocol with a single
    implementation. The indirection added no value; deleted in v2.
    Criteria are called directly via evaluator.evaluate()."""

def test_definition_task_id_column_does_not_exist() -> None:
    """v1 had a definition_task_id column on run_graph_nodes that
    duplicated task_id. Schema reset removes it."""

def test_experiment_record_table_does_not_exist() -> None:
    """v1 had ExperimentRecord and ExperimentDefinition as separate
    tables with 1:1 lifecycle. Schema reset collapses them."""
```

Each test is small (5-15 lines) and named so a regression failure
points directly at the v1 audit finding it guards.

## §4 — What's deliberately not tested

Per [`08-decisions-log.md`](08-decisions-log.md), the v2 design
accepts these tradeoffs and does not test them:

- **No public/internal boundary on `core.application.*` imports.**
  Toolkits and the workflow CLI are allowed to import services
  directly. There is no architecture guard preventing this; if a
  future refactor wants to enforce a public/internal boundary, it
  adds the guard then. Until then, the porousness is intentional.
- **No exhaustive payload-roundtrip test for every event.** The
  walkthrough integration test exercises every event in the happy
  path and the failure cascade; that's enough. We don't need a
  per-event JSON-schema-validation test for each.
- **No fuzz testing of `_type` discriminator resolution.** Pydantic's
  validation handles malformed JSON; we trust it.

## §5 — Running the suite

```sh
# Architecture guards (fast)
pytest ergon_core/tests/unit/architecture/

# Regression net (fast)
pytest ergon_core/tests/unit/regression/

# Walkthrough integration (slow — needs Postgres test container)
pytest -m integration ergon_core/tests/integration/test_walkthrough.py

# Everything
pytest ergon_core/
```

CI runs all three layers on every PR. The walkthrough integration test
is the slowest (~30s with test container spinup) and is the gating
test for "merge to main."

## Decisions locked at workshop `[v2: locked]`

- **Architecture-guard implementation** — **locked: textual.**
  `test_no_other_release_callsites` and similar guards stay as
  substring-style scans. We don't take the `grimp` dependency
  speculatively; revisit if/when a textual guard misses a real
  regression.
- **Walkthrough as living document** — **locked: hand-written
  pytest test that mirrors the walkthrough.** No markdown-to-test
  generator. The hand-written version forces a human to read both
  files and check they match — the point is the synchronization
  pressure, not the automation.
- **Regression-net scope** — **locked: 8 load-bearing findings
  only** (the list in §3). The other 24 fix-plan items from the v1
  audit are "delete this dead function" deletions whose
  reintroduction would be caught by the deletion-checklist tests
  in §1; no separate regression test per item.
- **Per-PR test budget** — **locked: run all 4 walkthrough
  variants sequentially.** ~2 min is acceptable for v2 launch.
  Revisit only if cumulative test wall time crosses 10 min.

### Follow-up after v2 lands

The v1 integration and end-to-end test suites need refresh after
v2 ships — they exercise paths v2 deletes (separate
`evaluate_task_run`, `saved_specs` writes, `_prepare_definition`).
That refresh is **not in v2's scope**; it's a follow-up PR sized
against whatever the test suite looks like once v2 is merged.
Tracked here so it doesn't get lost.

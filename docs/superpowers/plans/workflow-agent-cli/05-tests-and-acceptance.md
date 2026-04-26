# 05 — Tests and Acceptance

## Unit Tests

### Workflow Service

Create `tests/unit/runtime/test_workflow_service.py`.

Cover:

- `list_tasks(run_id)` returns all run nodes ordered by level/task slug
- `list_tasks(run_id, parent_node_id=...)` returns direct children only
- `list_dependencies(..., direction="upstream")` returns incoming edges with source/target summaries
- `list_resources(..., scope="input")` returns latest resources from immediate upstream nodes only
- `list_resources(..., scope="visible")` can include resources from divergent branches inside the same run
- `read_resource_bytes(...)` rejects resources outside the injected run
- blockers and next actions return useful suggested commands
- copied row has a new resource ID
- copied row has `kind="import"`
- copied row keeps the same `content_hash` and blob `file_path`
- copied row has `copied_from_resource_id=<source id>`
- source row is unchanged
- default name appends `(copy)`
- destination path is normalized under `/workspace`
- `dry_run=True` performs no DB or sandbox write
- absolute paths, `..`, cross-run resources, invisible resources, and destination collisions fail
- import manifest write is requested with source/copy/destination metadata

### CLI Parser and Handler

Create `tests/unit/cli/test_workflow_cli.py`.

Cover:

- `inspect task-list`
- `inspect task-details --include-output`
- `inspect task-dependencies --direction upstream`
- `inspect resource-list --scope input`
- `inspect resource-list --scope visible --limit 20`
- `inspect resource-content`
- `inspect task-blockers`
- `inspect next-actions`
- `manage materialize-resource --dry-run`
- every graph lifecycle `manage ... --dry-run`
- invalid UUID exits non-zero
- duplicate task slug exits non-zero with a helpful message
- JSON output has stable fields

### Agent Wrapper

Create `tests/unit/state/test_workflow_cli_tool.py`.

Cover:

- injects `run_id`
- injects `node_id`
- injects `execution_id`, `sandbox_id`, and `sandbox_task_key` for materialization
- denies user-supplied scope/context arguments
- allows `inspect resource-list --scope visible --limit 20`
- allows `manage materialize-resource ... --dry-run` for leaf wrappers
- denies graph lifecycle mutations for leaf wrappers
- allows graph lifecycle dry-runs for manager wrappers
- multiline/bad top-level commands fail structurally, not by subprocess shell behavior

### Worker Wiring

Modify `tests/unit/state/test_research_rubrics_workers.py`.

Cover:

- `researchrubrics-workflow-cli-react` is registered
- `ResearchRubricsWorkflowCliReActWorker` exposes `workflow`
- prompt recommends `inspect task-workspace`, `inspect resource-list --scope input`, `manage materialize-resource --dry-run`, and dry-run before graph lifecycle mutation
- existing `ResearchRubricsResearcherWorker` behavior remains unchanged

## Integration Tests

Yes, this feature needs integration tests because the unit tests can mock too much of the persistence/sandbox boundary.

Create:

```text
tests/integration/runtime/test_workflow_cli_materialize_resource.py
```

Use real Postgres and the normal SQLModel session setup for integration tests. Use a fake or stub sandbox manager registered for the test benchmark so the test can assert `upload_file(...)` calls without real E2B.

Cover:

- current-run invariant: a resource from another run cannot be listed, read, or materialized
- `visible` lists resources from divergent branches inside the same run
- `materialize-resource` creates a copied `RunResource` row and leaves the source unchanged
- copied row has `task_execution_id` for the consuming task
- copied row has `copied_from_resource_id`
- copied row reuses the same content-addressed blob path/hash
- sandbox upload receives the copied bytes and normalized `/workspace/...` destination
- import manifest update is attempted after the copied row exists
- failed sandbox upload does not append a copied resource row

Integration command:

```bash
pytest tests/integration/runtime/test_workflow_cli_materialize_resource.py -v
```

## E2E Tests

Do not add a fourth standalone e2e test file for this feature. The existing benchmark smoke e2e tests are already slow and already exercise the full orchestration path. Extend the existing stub/smoke workers and assertions instead.

Modify:

```text
tests/e2e/test_researchrubrics_smoke.py
tests/e2e/test_minif2f_smoke.py
tests/e2e/test_swebench_smoke.py
tests/e2e/_asserts.py
ergon-dashboard/tests/e2e/_shared/smoke.ts
ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts
ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts
ergon-dashboard/tests/e2e/swebench.smoke.spec.ts
```

The e2e smoke workers for each benchmark should receive the workflow CLI tool and perform a small deterministic workflow exercise during the existing run. Keep this no-LLM.

Recommended deterministic e2e behavior inside the existing smoke topology:

```text
producer leaf:
  publishes useful artifact

consumer leaf or parent smoke worker:
  calls workflow("inspect task-tree")
  calls workflow("inspect resource-list --scope visible --limit 20")
  calls workflow("manage materialize-resource --resource-id <producer-resource> --dry-run")
  calls workflow("manage materialize-resource --resource-id <producer-resource>")
  reads/edits the materialized workspace file
  publishes a consumer-owned artifact

manager-capable smoke path:
  calls one graph lifecycle command with --dry-run, such as create-task or create-dependency
  asserts dry-run returns the planned mutation without changing graph shape
```

Assertions:

- run reaches terminal status
- producer has original published `RunResource`
- consumer has `kind=import` copied `RunResource`
- copied row points to producer row via `copied_from_resource_id`
- consumer has a later output resource owned by consumer execution
- source producer row is unchanged
- context events include the `workflow` tool call and materialization result
- no control edge is added between producer and consumer unless explicitly in the test graph
- graph lifecycle dry-run command did not create nodes/edges
- existing smoke assertions still pass for all three benchmark e2e files

Playwright assertions:

- The run/task trace UI shows a `workflow` tool call made by the smoke worker.
- The visible trace includes command text for `inspect task-tree`.
- The visible trace includes command text for `inspect resource-list --scope visible`.
- The visible trace includes command text for `manage materialize-resource`.
- The visible trace shows a successful tool result for materialization.
- The UI does not need to render lineage-specific fields like `copied_from_resource_id` in v1; PG assertions own lineage correctness.

If the existing dashboard smoke spec already has a shared per-run assertion helper, add this as a small optional assertion there rather than duplicating per benchmark. If test IDs are missing, add stable test IDs around tool-call rows/results rather than relying on brittle text layout selectors.

E2E commands:

```bash
pytest tests/e2e/test_researchrubrics_smoke.py -v
pytest tests/e2e/test_minif2f_smoke.py -v
pytest tests/e2e/test_swebench_smoke.py -v
pnpm --dir ergon-dashboard test:e2e -- researchrubrics.smoke.spec.ts
pnpm --dir ergon-dashboard test:e2e -- minif2f.smoke.spec.ts
pnpm --dir ergon-dashboard test:e2e -- swebench.smoke.spec.ts
```

This saves a full extra e2e run while still proving the workflow CLI works through real orchestration, real sandbox execution, and each benchmark's smoke path.

## Input Resource Contract

Create `tests/unit/runtime/test_workflow_input_resource_semantics.py`.

Graph:

```text
d_root -> d_left
d_root -> d_right
d_left -> d_join
d_right -> d_join
l_1 -> l_2 -> l_3
```

Assert:

- `d_join` input resources are latest resources from `d_left` and `d_right`
- `l_3` input resources are latest resources from `l_2`, not `l_1`
- roots and singletons have empty input resources

This is separate from on-demand `materialize-resource`.

## Real-LLM Acceptance

Modify `tests/real_llm/benchmarks/test_researchrubrics.py` so the rollout can parameterize worker and sample limit:

```python
model = os.environ.get("ERGON_REAL_LLM_MODEL", _DEFAULT_MODEL)
benchmark = os.environ.get("ERGON_REAL_LLM_BENCHMARK", "researchrubrics")
worker = os.environ.get("ERGON_REAL_LLM_WORKER", "researchrubrics-researcher")
evaluator = os.environ.get("ERGON_REAL_LLM_EVALUATOR", "research-rubric")
limit = os.environ.get("ERGON_REAL_LLM_LIMIT", "1")
```

Final acceptance rollout:

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=5 \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s
```

Expected:

- real-LLM test reaches terminal status: `completed`, `failed`, or `cancelled`
- artifacts are written under `tests/real_llm/.rollouts/<timestamp>-<run_id>/`
- manifest records `worker=researchrubrics-workflow-cli-react` and `limit=5`
- report and dumped rows show whether the agent invoked `workflow(...)`
- report and dumped rows show whether it materialized copied resources
- reviewer can inspect whether CLI usage helped the agent orient around topology/resources

## Verification Bundle

Run focused tests:

```bash
pytest tests/unit/runtime/test_workflow_service.py tests/unit/cli/test_workflow_cli.py tests/unit/state/test_workflow_cli_tool.py -v
```

Run integration:

```bash
pytest tests/integration/runtime/test_workflow_cli_materialize_resource.py -v
```

Run e2e:

```bash
pytest tests/e2e/test_researchrubrics_smoke.py -v
pytest tests/e2e/test_minif2f_smoke.py -v
pytest tests/e2e/test_swebench_smoke.py -v
```

Run worker wiring:

```bash
pytest tests/unit/state/test_research_rubrics_workers.py -v
```

Run final real-LLM rollout on demand:

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=5 \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s
```

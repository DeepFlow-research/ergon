# 06 — Phases, Deliverables, Acceptance Gates

## Delivery Shape

One PR, layered so each phase is independently reviewable. Each phase should leave tests green before moving on.

## Phase A — Schema and Persistence

**Scope**

- Add `RunResourceKind.IMPORT`.
- Add `RunResource.copied_from_resource_id`.
- Extend `ResourcesQueries.append(...)`.
- Add migration `<revision>_add_copied_from_resource_id.py`.

**Acceptance Gate**

```bash
pytest tests/unit/runtime/test_workflow_service.py -v
```

At this phase, only schema/helper tests need to pass; workflow service tests can be marked/structured around the implemented subset.

## Phase B — Workflow DTOs and Read Service

**Scope**

- Create `workflow_dto.py`.
- Create `workflow_service.py`.
- Implement task listing, tree traversal, dependency inspection, resource scopes, blockers, next actions, and resource content reads.

**Acceptance Gate**

```bash
pytest tests/unit/runtime/test_workflow_service.py -v
```

## Phase C — Workflow Materialization

**Scope**

- Implement current-run resource resolution.
- Implement visible-resource policy.
- Normalize destinations under `/workspace`.
- Copy bytes into sandbox via existing `BaseSandboxManager.upload_file(...)`.
- Append current-task-owned `kind=import` resource row after successful upload.
- Update `/workspace/.ergon/resource_imports.json`.

**Acceptance Gate**

```bash
pytest tests/unit/runtime/test_workflow_service.py -v
pytest tests/integration/runtime/test_workflow_cli_materialize_resource.py -v
```

## Phase D — CLI Command Surface

**Scope**

- Create `ergon_cli/ergon_cli/commands/workflow.py`.
- Register `workflow` in `ergon_cli/ergon_cli/main.py`.
- Add all `inspect` commands.
- Add graph lifecycle `manage` commands.
- Add `manage materialize-resource`.
- Support `--format`, `--explain`, output caps, and `--dry-run`.

**Acceptance Gate**

```bash
pytest tests/unit/cli/test_workflow_cli.py -v
pytest tests/integration/runtime/test_workflow_cli_materialize_resource.py -v
```

## Phase E — Agent Wrapper

**Scope**

- Create `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`.
- Inject runtime scope from `WorkerContext`.
- Reject user-supplied scope/context arguments.
- Enforce leaf vs manager permissions.
- Capture stdout/stderr from in-process CLI calls.

**Acceptance Gate**

```bash
pytest tests/unit/state/test_workflow_cli_tool.py -v
```

## Phase F — ResearchRubrics POC Worker

**Scope**

- Create `ResearchRubricsWorkflowCliReActWorker`.
- Register `researchrubrics-workflow-cli-react`.
- Add prompt guidance for inspect/materialize/dry-run behavior.
- Keep existing `ResearchRubricsResearcherWorker` unchanged.

**Acceptance Gate**

```bash
pytest tests/unit/state/test_research_rubrics_workers.py -v
```

## Phase G — Deterministic E2E

**Scope**

- Extend the existing benchmark smoke e2e paths instead of adding a fourth e2e test file.
- Give the smoke/stub workers enough workflow CLI access to exercise `inspect`, `visible` resource discovery, `materialize-resource`, and graph lifecycle dry-run behavior.
- Add assertions to existing e2e test files/helpers for copied resources, lineage, tool-call context events, and unchanged graph shape after dry-runs.
- Extend the existing dashboard Playwright smoke specs to assert the workflow CLI tool calls/results are visible in the run/task trace UI.
- No real LLM.

**Acceptance Gate**

```bash
pytest tests/e2e/test_researchrubrics_smoke.py -v
pytest tests/e2e/test_minif2f_smoke.py -v
pytest tests/e2e/test_swebench_smoke.py -v
pnpm --dir ergon-dashboard test:e2e -- researchrubrics.smoke.spec.ts
pnpm --dir ergon-dashboard test:e2e -- minif2f.smoke.spec.ts
pnpm --dir ergon-dashboard test:e2e -- swebench.smoke.spec.ts
```

## Phase H — Real-LLM Rollout

**Scope**

- Parameterize `tests/real_llm/benchmarks/test_researchrubrics.py`.
- Run `researchrubrics-workflow-cli-react` for 5 samples.
- Inspect generated rollout artifacts.

**Acceptance Gate**

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=5 \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s
```

The run reaching terminal status is enough for the test harness. The product is the artifact bundle and review of actual agent behavior.

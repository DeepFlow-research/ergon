# RQ1 CLI Specialism Overnight Changelog

## Goal

Use the PR #39 workflow-CLI ResearchRubrics agent to produce rollout-card artifacts that support RQ1: returns remain a useful guardrail, but rollout cards preserve richer delegation and role-specialism behaviour that scalar returns discard.

## 2026-04-26 23:30 UTC+1 - Preflight

- Worktree: `/Users/charliemasters/Desktop/synced_vm_002/ergon/.worktrees/feature/finish-agent-workflow-cli`
- Branch: `feature/finish-agent-workflow-cli`
- PR: https://github.com/DeepFlow-research/ergon/pull/39
- Commit at start: `ae7a0a8 Finish agent workflow CLI task editing`
- PR checks: all current checks passing by `gh pr checks 39`:
  - `Integration tests (Python)`: pass
  - `Lint + type-check (Frontend)`: pass
  - `Lint + type-check (Python)`: pass
  - `Unit tests (Python)`: pass
  - `smoke [minif2f]`: pass
  - `smoke [researchrubrics]`: pass
  - `smoke [swebench-verified]`: pass
- Local `.env`: not present in the PR worktree. Real-LLM commands source `/Users/charliemasters/Desktop/synced_vm_002/ergon/.env` without copying it.
- Required keys after sourcing main `.env`: `OPENROUTER_API_KEY`, `EXA_API_KEY`, and `E2B_API_KEY` are set.
- Local services:
  - `docker compose ps` in the worktree showed no compose-owned services.
  - `http://127.0.0.1:3001/` responded.
  - `http://127.0.0.1:9000/` responded with HTTP 404, which still indicates a process is listening; harness fixture treats connection success as stack-up.

## Run Log

Runs append below. Each entry should include command, env knobs, rollout artifact path, run ID, terminal status, score notes, graph/subtask notes, and prompt/config changes.

## 2026-04-26 23:36 UTC+1 - Preflight Smoke Blocker

- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v -s --assume-stack-up`
- Result:
  - Failed during test collection before any benchmark/model spend.
- Root cause:
  - `telemetry.models` imports `ergon_core.api.json_types`, which executes `ergon_core.api.__init__`.
  - `ergon_core.api.__init__` eagerly imported `RunResourceView` from `api.run_resource`.
  - `api.run_resource` imports `RunResourceKind` from `telemetry.models` while `telemetry.models` is partially initialized.
- Fix:
  - Added `tests/unit/runtime/test_import_boundaries.py` as a regression.
  - Changed `ergon_core/ergon_core/api/__init__.py` to lazily expose `RunResourceKind` and `RunResourceView` via `__getattr__`.
- Verification:
  - `uv run pytest tests/unit/runtime/test_import_boundaries.py -q` -> `1 passed`
  - `uv run ruff format ergon_core/ergon_core/api/__init__.py tests/unit/runtime/test_import_boundaries.py && uv run ruff check ergon_core/ergon_core/api/__init__.py tests/unit/runtime/test_import_boundaries.py` -> `All checks passed`
- Commit:
  - `e23c276 Fix run resource API import boundary`

## 2026-04-26 23:45 UTC+1 - Stack Rebuild

- Rebuilt the shared `ergon` compose project from the PR #39 worktree:
  - `COMPOSE_PROJECT_NAME=ergon docker compose up -d --build --wait`
- Reason:
  - The running stack was built before PR #39, so the API/Inngest runtime might not know `researchrubrics-workflow-cli-react`.
- Result:
  - `ergon-api-1`, `ergon-dashboard-1`, `ergon-inngest-dev-1`, and `ergon-postgres-1` are running.
  - API root returns HTTP 404 but the process is reachable; the real-LLM fixture only requires connection success.

## 2026-04-26 23:47 UTC+1 - Baseline Workflow-CLI Batch 1

- Intent:
  - Run 5 ResearchRubrics samples with the current PR #39 workflow-CLI prompt.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Failed after creating run `2626bae9-b058-4b1b-9803-8e6186468023`.
- Failure:
  - Harness endpoint `GET /api/test/read/run/2626bae9-b058-4b1b-9803-8e6186468023/state` returned HTTP 500.
  - Local DB/API inspection showed `psycopg2.errors.UndefinedColumn: column run_resources.copied_from_resource_id does not exist`.
- Root cause:
  - The long-lived local Postgres DB was stamped at Alembic head `0a1b2c3d4e5f`, but was missing the already-existing migration `a2b3c4d5e6f7_add_copied_from_resource_id.py` effect. This is local schema drift, not a missing migration in the branch.
- Local repair:
  - Applied idempotent local DDL:
    - `ALTER TABLE run_resources ADD COLUMN IF NOT EXISTS copied_from_resource_id UUID NULL`
    - `CREATE INDEX IF NOT EXISTS ix_run_resources_copied_from_resource_id ON run_resources (copied_from_resource_id)`
    - Add FK constraint `fk_run_resources_copied_from_resource_id_run_resources` if absent.
  - Verification: information schema now reports one `copied_from_resource_id` column.
- Post-repair canary:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v -s --assume-stack-up`
  - Result: `1 passed` in 27.15s.

## 2026-04-26 23:45 UTC+1 - Baseline Workflow-CLI Batch 1b

- Intent:
  - Retry 5 ResearchRubrics samples after local schema repair.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Passed, but not useful for headline RQ1 evidence.
- Rollout:
  - Directory: `tests/real_llm/.rollouts/20260426T224530Z-3caf7e5c-e09f-47a8-8afb-58fd2693b761/`
  - Run ID: `3caf7e5c-e09f-47a8-8afb-58fd2693b761`
  - Wall clock: 235.6s
  - Budget: $0.477609
- Findings:
  - The hardcoded `researchrubrics` benchmark loaded only 2 private/default smoke rows: `smoke-001`, `smoke-002`.
  - Graph had 2 root nodes, 0 edges, 0 child subtasks, 2 resources, 1 evaluation.
  - Worker did call `workflow inspect task-tree` once per task, but did not spawn/coordinate specialist subtasks.
  - Evaluator returned score 0.0 because the API container did not have `OPENAI_API_KEY`.
- Fixes after analysis:
  - `ResearchRubricsBenchmark._payload_from_row` now accepts vanilla dataset rows with `prompt` when `ablated_prompt` is absent.
  - `tests/real_llm/benchmarks/test_researchrubrics.py` now honors `ERGON_REAL_LLM_BENCHMARK`, defaulting to `researchrubrics`.
  - `docker-compose.yml` now passes `OPENAI_API_KEY`, `EXA_API_KEY`, and `HF_API_KEY` to the API container alongside the existing E2B/OpenRouter keys.
  - Focused tests: `uv run pytest tests/unit/state/test_research_rubrics_benchmark.py -q` -> `10 passed`.
  - Vanilla load check: `ResearchRubricsVanillaBenchmark(limit=5)` -> 5 rows loaded.
  - Stack rebuilt with exported env; API container verified all provider keys present.

## 2026-04-27 00:00 UTC+1 - Vanilla 5-Sample Workflow-CLI Batch 1

- Intent:
  - Run the actual 5-row ScaleAI ResearchRubrics benchmark after enabling vanilla rows and backend evaluator env.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_BENCHMARK=researchrubrics-vanilla ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Run reached terminal `failed`, but pytest timed out waiting for resources/evaluations because all tasks failed before report persistence.
- Rollout:
  - Directory: `tests/real_llm/.rollouts/20260426T230154Z-ab57a0df-2a6d-4174-95f5-87185f717707/`
  - Run ID: `ab57a0df-2a6d-4174-95f5-87185f717707`
  - Row counts: 5 graph nodes, 0 graph edges, 25 mutations, 121 context events, 10 sandbox events, 0 resources, 0 evaluations.
- Findings:
  - This was the intended 5 real-row ScaleAI benchmark: five sample IDs were created.
  - Behavior was rich but not successful: 116 tool calls total, including 111 `exa_search` and 5 `workflow inspect task-tree`.
  - No task called `write_report_draft` or `final_result`; all failed with generic `Worker execution failed`.
  - Failure mode appears to be search-budget exhaustion / max-iteration behavior on large vanilla rubrics, not missing provider keys.
  - No child subtasks: the workflow tool was available but graph editing was not manager-capable, and the prompt only suggested inspection/resource-copying.
- Core/harness fixes:
  - `_wait_for_post_terminal_artifacts` now returns for terminal `failed`/`cancelled` runs with no running executions, so failed-before-output rollouts still dump artifacts.
  - `_require_keys` now includes `openai_api_key`.
  - Broke a context-event import cycle by storing context `turn_logprobs` as open JSON payloads instead of importing `TokenLogprob` from `ergon_core.api.generation`.
  - Added import-boundary coverage for context models.
  - Tests: `uv run pytest tests/unit/runtime/test_import_boundaries.py tests/unit/state/test_research_rubrics_benchmark.py -q` -> `12 passed`.

## 2026-04-27 00:04 UTC+1 - Prompt Hillclimb Variant 1

- Prompt/tool changes:
  - Workflow-CLI ReAct worker now passes `manager_capable=True` to `make_workflow_cli_tool`.
  - Prompt asks level-0 tasks to create exactly three specialist child tasks before research:
    - source scout
    - rubric compliance checker
    - synthesis reviewer
  - Prompt tells non-root tasks not to create recursive children.
  - Prompt caps own work to at most 6 `exa_search` calls before writing `final_output/report.md`.
- Verification:
  - `uv run pytest tests/unit/state/test_research_rubrics_workers.py tests/unit/state/test_workflow_cli_tool.py -q` -> `10 passed`.
  - API restarted; provider keys still present in container.
- Next run command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_BENCHMARK=researchrubrics-vanilla ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Diagnostic run:
  - Run ID: `4d3721d0-aacb-4f04-bea9-9217c0549f9e`
  - Stopped pytest manually after confirming it was polluted by the async workflow bridge bug.
  - Positive signal: at least one root task attempted the desired `workflow manage add-task` specialist pattern before searching:
    - source scout
    - rubric compliance checker
    - synthesis reviewer
  - Bug found: agent-side workflow manage commands called the sync CLI bridge, which used `asyncio.run()` inside an already-running event loop. API log showed `RuntimeWarning: coroutine '_handle_manage' was never awaited`.
- Core fix:
  - Added `execute_workflow_command_async(...)` in `ergon_cli.commands.workflow`.
  - `execute_workflow_command(...)` now remains a sync wrapper for CLI callers.
  - `make_workflow_cli_tool(...)` now awaits the async executor.
  - Tests: `uv run pytest tests/unit/cli/test_workflow_cli.py tests/unit/state/test_workflow_cli_tool.py -q` -> `10 passed`.

## 2026-04-27 00:13 UTC+1 - Prompt Hillclimb Variant 1b

- Intent:
  - Re-run Variant 1 with the fixed async workflow bridge.
- Status:
  - Cancelled after diagnostic success and provider failures.
- Diagnostic result:
  - Run ID: `9a83787a-dac2-45a1-9d3f-823f65984716`
  - Early poll showed 20 graph nodes: 5 roots + 15 level-1 specialist children.
  - Each root created source scout, rubric compliance, and synthesis reviewer children.
  - This is the desired RQ1 graph-specialism signal.
  - However, several roots failed on provider/schema errors (`finish_reason=None`) before reports/evaluations landed; remaining children were pending/blocked.
  - Cancelled run via `uv run ergon run cancel 9a83787a-dac2-45a1-9d3f-823f65984716`.

## 2026-04-27 00:22 UTC+1 - Prompt Hillclimb Variant 1c

- Intent:
  - Keep the specialist-subtask prompt, but switch from OpenRouter Sonnet to direct OpenAI to avoid the `finish_reason=None` OpenRouter/PydanticAI failure.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_MODEL=openai:gpt-4o-mini ERGON_REAL_LLM_BENCHMARK=researchrubrics-vanilla ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Cancelled after partial artifact dump.
- Rollout:
  - Directory: `tests/real_llm/.rollouts/20260426T232803Z-3b258073-ab38-4a22-ac18-766c27d8aa1e/`
  - Run ID: `3b258073-ab38-4a22-ac18-766c27d8aa1e`
  - Row counts: 11 graph nodes, 37 mutations, 90 context events, 3 resources, 2 evaluations.
- Findings:
  - Direct OpenAI avoided the OpenRouter `finish_reason=None` issue.
  - Two root tasks completed and produced evaluations:
    - score `0.11382113821138211`, passed `true`
    - score `0.014084507042253521`, passed `false`
  - Three roots failed before final output; two failed roots created specialist children, which were blocked by parent failure.
  - This is a partial "rich behavior vs return" data point: returns are low/partial, but rollout-card structure exposes role-specialist decomposition not captured by scalar return.

## 2026-04-27 00:29 UTC+1 - Prompt Hillclimb Variant 1d

- Intent:
  - Same specialist prompt, direct OpenAI, stronger model (`openai:gpt-4o`) to improve returns while preserving graph-specialism signal.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_MODEL=openai:gpt-4o ERGON_REAL_LLM_BENCHMARK=researchrubrics-vanilla ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Cancelled after partial artifact dump because dynamic child tasks remained pending.
- Rollout:
  - Directory: `tests/real_llm/.rollouts/20260426T233740Z-356b7189-229b-4ef4-849c-f3c87964feb4/`
  - Run ID: `356b7189-229b-4ef4-849c-f3c87964feb4`
  - Row counts: 20 graph nodes, 43 mutations, 62 context events, 5 resources, 4 evaluations.
- Findings:
  - Best evidence so far: 5 roots, 15 specialist children, 4/5 root reports completed, 4 evaluations landed.
  - Scores:
    - `0.1267605633802817`, passed `true`
    - `0.11382113821138211`, passed `true`
    - `0.07142857142857142`, passed `false`
    - `0.0`, passed `false`
  - Dynamic children remained `pending` rather than being scheduled after creation.
- Core fix:
  - `WorkflowService.add_task` now emits `task/ready` for the created dynamic node after commit.
  - Added an injectable task-ready dispatcher and unit test coverage.
  - Tests: `uv run pytest tests/unit/runtime/test_workflow_service.py tests/unit/cli/test_workflow_cli.py tests/unit/state/test_workflow_cli_tool.py -q` -> `22 passed`.

## 2026-04-27 00:38 UTC+1 - Prompt Hillclimb Variant 1e

- Intent:
  - Same GPT-4o specialist prompt, now with dynamic child scheduling fixed.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_MODEL=openai:gpt-4o ERGON_REAL_LLM_BENCHMARK=researchrubrics-vanilla ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Pytest artifact-dump wrapper passed, but run terminal status is `failed`.
- Rollout:
  - Directory: `tests/real_llm/.rollouts/20260426T233920Z-0700b668-a640-49f2-80f9-a5c87bc160a9/`
  - Run ID: `0700b668-a640-49f2-80f9-a5c87bc160a9`
  - Row counts: 20 graph nodes, 70 mutations, 257 context events, 5 resources, 5 evaluations, 20 executions.
  - Run summary: `final_score=0.7134802212615627`, `normalized_score=0.14269604425231255`, `evaluators_count=5`.
- Findings:
  - Scheduling fix worked: Inngest logs show dynamic `task/ready` events for child `node_id`s and `task-execute` initialized for those children.
  - Graph-specialism signal preserved: 5 roots and 15 specialist children.
  - Returns improved versus prior failed/partial variants: all 5 root tasks completed and all 5 root evaluations landed; 1/5 evaluations passed.
  - Remaining failure mode: most specialist children started and then failed generically (`Worker execution failed`), causing the overall run to fail even though root reports/evaluations landed.
  - Root cause for child recursion: the prompt told agents to inspect `task-tree`; child agents can see other level-0 roots in that output and at least one child incorrectly called `manage add-task`.
- Prompt fix for next run:
  - Delegation decision now uses only `workflow("inspect task-workspace --format json")` and `task_workspace.task.level`.
  - Prompt explicitly says to ignore level-0 tasks shown elsewhere in task-tree.
  - Non-root specialist children are told not to call `workflow("manage add-task`), to use at most 2 workflow inspections and 3 `exa_search` calls, and to write `final_output/report.md`.
- Verification:
  - Red test first: `uv run pytest tests/unit/state/test_research_rubrics_workers.py::TestResearcherWorker::test_workflow_cli_prompt_uses_current_task_level_for_delegation -q` failed on the missing `task-workspace --format json` instruction.
  - Green tests: `uv run pytest tests/unit/state/test_research_rubrics_workers.py tests/unit/state/test_workflow_cli_tool.py -q` -> `11 passed`.

## 2026-04-27 00:55 UTC+1 - Prompt Hillclimb Variant 1f

- Intent:
  - Same GPT-4o specialist prompt, but with delegation keyed to the current task workspace rather than global task-tree rows.
- Command:
  - `ERGON_REAL_LLM=1 ERGON_REAL_LLM_BUDGET_USD=50 ERGON_REAL_LLM_MODEL=openai:gpt-4o ERGON_REAL_LLM_BENCHMARK=researchrubrics-vanilla ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react ERGON_REAL_LLM_LIMIT=5 uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py -v -s --assume-stack-up`
- Status:
  - Pytest artifact-dump wrapper passed, but run terminal status is `failed`.
- Rollout:
  - Directory: `tests/real_llm/.rollouts/20260426T234424Z-7fc055f5-03c3-4cab-8117-04e844696482/`
  - Run ID: `7fc055f5-03c3-4cab-8117-04e844696482`
  - Row counts: 20 graph nodes, 70 mutations, 235 context events, 5 resources, 5 evaluations, 20 executions.
  - Run summary: `final_score=0.7597894539417135`, `normalized_score=0.1519578907883427`, `evaluators_count=5`.
- Findings:
  - Best overnight evidence so far.
  - Graph-specialism signal: 5 roots created exactly 15 specialist children; `manage add-task` appears exactly 15 times and no recursive child creation was observed.
  - Return guardrail: all 5 root tasks completed, all 5 root evaluations landed, and the aggregate normalized score improved slightly over 1e (`0.1519578907883427` vs `0.14269604425231255`).
  - Specialist execution improved but remains noisy: 5/15 children completed, 10/15 failed with generic `Worker execution failed`, so the run-level status is still `failed`.
  - This supports the RQ1 story: the scalar terminal status is poor, but the rollout card exposes a stable specialist-delegation pattern, role-specific child descriptions, root report completion, and recoverable child-worker behavior.
- Backend harness endpoint check:
  - `GET http://127.0.0.1:9000/api/test/read/run/7fc055f5-03c3-4cab-8117-04e844696482/state` returned HTTP 200 with `status=failed`, `graph_nodes=20`, `mutations=70`, `evaluations=5`, `executions=20`, `resource_count=5`, `context_event_count=235`.
  - The same path on dashboard port `3001` returned 404; the harness route is backend API, not dashboard.

## Morning Handoff Notes

- Best variant: Prompt Hillclimb Variant 1f.
- Best artifact path: `tests/real_llm/.rollouts/20260426T234424Z-7fc055f5-03c3-4cab-8117-04e844696482/`
- Candidate RQ1 headline evidence:
  - Returns/status alone: run is `failed`, but all 5 root tasks completed and all 5 evaluations landed.
  - Rollout-card structure: 5 root tasks, exactly 15 specialist child tasks, 70 graph mutations, 235 context events.
  - Specialism behavior: root tasks consistently decomposed into source-scout, rubric-checker/compliance, and synthesis-reviewer roles.
  - Cross-community analysis hook: this single rollout card supports post-hoc role-diversity / worker-specialism measurements that are invisible in terminal status or scalar return.
- Main residual issue:
  - Dynamic specialist children now schedule and some complete, but child failures still propagate run failure. Next core-code direction would be either (a) make advisory child tasks non-fatal for parent benchmark return, or (b) harden child-worker prompting/tooling so specialist children reliably write `final_output/report.md`.



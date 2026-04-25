# Karnas ResearchRubrics Rollout Experiment Log

Date: 2026-04-25
Branch: `experiments/karnas-researchrubrics-rollouts-main-20260425`
Base: `origin/main` at `4bb7be5`

## Purpose

Use the real-LLM ResearchRubrics rollout harness as a manual research/debug loop:
generate rollouts, read the persisted Postgres/dashboard state, debug Ergon core,
and extend the research agent action space where the evidence shows a real gap.

## Log

### 12:43 UTC+1 - Fresh branch setup

- Confirmed `origin/main` and local `main` both point to `4bb7be5`.
- Created `experiments/karnas-researchrubrics-rollouts-main-20260425` from fresh `main`.
- Abandoned the earlier stale-base experiment branch for this workflow.
- Left pre-existing untracked `ergon_paper_overleaf_edit/` untouched.
- Created this log as the tracked record of changes, rollout results, and decisions.

### 12:45 UTC+1 - Stack and harness preflight

- Started the full Docker Compose stack with `TEST_HARNESS_SECRET=real-llm-secret docker compose up -d --wait`.
- Compose reported Postgres, API, Inngest, and dashboard as healthy.
- Host reachability:
  - Dashboard is reachable at `http://127.0.0.1:3001/`.
  - Inngest is reachable at `http://127.0.0.1:8289/`.
  - API root returns `404`, which is expected for a FastAPI app with no `/` route once startup is complete.
- Credential preflight:
  - `.env` contains `OPENAI_API_KEY`, `EXA_API_KEY`, `E2B_API_KEY`, and `HF_API_KEY`.
  - `.env` does not contain `OPENROUTER_API_KEY` or `OPEN_ROUTER_API_KEY`.
- First canary attempt:
  - Command: `ERGON_REAL_LLM=1 ERGON_DASHBOARD_URL=http://127.0.0.1:3001 ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@127.0.0.1:5433/ergon uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v -rs --assume-stack-up`
  - Result: skipped with `OPENROUTER_API_KEY not set`.
  - Root cause: `tests/real_llm/fixtures/openrouter_budget.py` autoused the OpenRouter budget gate for every real-LLM test, including the zero-cost stub canary and non-OpenRouter model runs.
- Harness fixes applied:
  - Made `openrouter_budget` yield `None` when OpenRouter is not configured instead of skipping the whole tier.
  - Made the budget gate a no-op when no OpenRouter budget is available.
  - Changed Playwright's default real-LLM dashboard base URL from `3101` to Compose's actual `3001`.
  - Exported `OPENAI_API_KEY` from `settings.openai_api_key` the same way the code already exported `OPENROUTER_API_KEY`.
  - Made `test_researchrubrics_rollout` require provider-specific keys based on `ERGON_REAL_LLM_MODEL`, so this machine can run `openai:*` rollouts without OpenRouter.

### 12:49 UTC+1 - OpenRouter key added and services recreated

- User added `OPENROUTER_API_KEY` to `.env`.
- Verified through `uv run python` that settings now sees OpenRouter, OpenAI, Exa, E2B, and HF keys.
- Recreated API, dashboard, and Inngest containers with `TEST_HARNESS_SECRET=real-llm-secret docker compose up -d --wait --force-recreate api dashboard inngest-dev` so the API/Inngest runtime process receives the updated env.
- Normalized `.env.example` to include `OPENROUTER_API_KEY=` without a trailing space.

### 12:54 UTC+1 - Canary hang root cause

- Reran the real-LLM stub canary after installing Python Playwright and Chromium.
- Result: pytest hung for more than 180s before creating any `RunRecord`.
- Evidence:
  - Postgres query showed `runs 0`.
  - Process tree showed no `ergon benchmark` subprocess.
  - Process tree did show Playwright driver + Chromium children under pytest.
- Root cause: the canary was wedged before the test body, inside the Python Playwright fixture path. This is a harness robustness bug: dashboard capture is useful rollout signal, but it must not prevent rollout generation or DB capture.
- Fix applied:
  - Added bounded Playwright launch/context timeouts.
  - Made Python Playwright fixtures yield `None` when unavailable or wedged.
  - Made `capture_dashboard()` return an empty screenshot map when Playwright is unavailable.
  - Made the stub canary skip only its dashboard-content assertion when Playwright is unavailable, while still exercising CLI -> Postgres -> harness polling.

### 12:58 UTC+1 - Canary stale smoke slug

- Canary reached its CLI subprocess after the Playwright timeout fix.
- Result: CLI failed before dispatch with `KeyError: 'smoke-test'`.
- Root cause: the old `smoke-test` benchmark was retired in the canonical-smoke refactor; deterministic smoke now works by importing `tests.e2e._fixtures` with `ENABLE_TEST_HARNESS=1`, which replaces real benchmark loaders with test-owned benchmark roots.
- Fix applied:
  - `ergon_cli.composition.build_experiment()` now imports `tests.e2e._fixtures` only when `ENABLE_TEST_HARNESS=1`.
  - Retargeted the real-LLM canary to `researchrubrics --worker researchrubrics-smoke-worker --evaluator researchrubrics-smoke-criterion --model stub:constant`.
- Verification:
  - Command: `ERGON_REAL_LLM=1 ERGON_DATABASE_URL=postgresql://ergon:ergon_dev@127.0.0.1:5433/ergon uv run pytest tests/real_llm/benchmarks/test_smoke_stub.py -v -rs --assume-stack-up --timeout=240`
  - Result: passed in 25.96s.

### 13:02 UTC+1 - Research target

- Read the paper framing around the ResearchRubrics experiment.
- Target for rollouts: preserve enough run structure to recover worker-level role specialisation or duplication that a scalar rubric score would discard.
- Relevant paper claim: long-horizon web research rollouts scored by scalar rubrics can be re-analysed as per-worker streams, measuring whether spawned subagents specialised or duplicated each other's work.

### 13:06 UTC+1 - Real ResearchRubrics CLI pre-dispatch failure

- First real rollout harness attempt failed before creating a `RunRecord`.
- Evidence:
  - Harness failed at `_latest_run_id_since(started_at)` because no run existed after CLI invocation.
  - Direct CLI reproduction failed with `TypeError: ResearchRubricsRubric.__init__() missing 1 required keyword-only argument: 'rubric_criteria'`.
- Root cause:
  - The public evaluator contract instantiates evaluators as `evaluator_cls(name=...)` and then calls `criteria_for(task)`.
  - `ResearchRubricsRubric` instead required task-specific dataset criteria at construction time, so both CLI composition and runtime evaluator reconstruction could not instantiate it.
- Fix applied:
  - Made `ResearchRubricsRubric` constructible with only `name`.
  - Moved task-payload-driven criterion construction into `criteria_for(task)`.
  - Changed aggregation to use `CriterionResult.weight`, so dynamically constructed criteria and runtime result rows remain aligned.
  - Added unit coverage for no-criteria construction and weighted aggregation.
- Verification:
  - Command: `uv run pytest tests/unit/state/test_research_rubrics_benchmark.py -q`
  - Result: `7 passed`.

### 13:10 UTC+1 - Real rollout accidentally used smoke fixtures

- Reran the real ResearchRubrics harness after fixing evaluator construction.
- Result: harness passed, but the generated rollout is not useful for the paper experiment.
- Artifact path: `tests/real_llm/.rollouts/20260425T115729Z-8da9abdf-d1cd-4bcd-99ee-a768d48ef669/`.
- Evidence:
  - `RunRecord` completed, but had `evaluators_count: 0`.
  - DB rows: 1 task execution, 0 generation turns, 0 task evaluations, 0 resources, 1 sandbox event.
  - Sandbox ID was `smoke-sandbox-...`, proving execution used the smoke sandbox manager instead of the real ResearchRubrics E2B manager.
- Root cause:
  - `ENABLE_TEST_HARNESS=1` had two meanings inside the API container: expose `/api/test/read/*` endpoints and import `tests.e2e._fixtures`.
  - Importing `tests.e2e._fixtures` replaces the production `researchrubrics` benchmark/sandbox registry entries with deterministic smoke fixtures.
  - Real-LLM rollouts need the read-only harness endpoints, but must not replace production benchmark registries.
- Fix applied:
  - Added `ENABLE_SMOKE_FIXTURES` as a separate flag.
  - API includes the test harness router when `ENABLE_TEST_HARNESS=1`.
  - API imports smoke fixtures only when `ENABLE_SMOKE_FIXTURES=1` (defaulting to the old `ENABLE_TEST_HARNESS` value for existing e2e behavior).
  - CLI composition uses the same smoke-fixture flag.
  - The stub canary sets both flags; real rollouts will set `ENABLE_TEST_HARNESS=1 ENABLE_SMOKE_FIXTURES=0`.
- Recreated API/dashboard/Inngest with `ENABLE_TEST_HARNESS=1 ENABLE_SMOKE_FIXTURES=0 TEST_HARNESS_SECRET=real-llm-secret docker compose up -d --wait --force-recreate api dashboard inngest-dev`.
- Verified:
  - API harness endpoint still returns `200`.
  - Dashboard root returns `200`.
  - API container registry resolves `researchrubrics` to `ergon_builtins.benchmarks.researchrubrics.benchmark`.

### 13:17 UTC+1 - Real rollout card still missing outputs/evaluation

- Corrected-stack rollout completed and spent OpenRouter budget, but the card was incomplete.
- Artifact path: `tests/real_llm/.rollouts/20260425T120137Z-ad3ecb2d-e4b6-49a1-bb85-e214520ec7f0/`.
- Evidence:
  - 8 `run_context_events` captured the real agent's tool calls (`exa_search`, `exa_qa`, `exa_get_content`, `write_report_draft`, `final_result`).
  - 0 `run_resources`, 0 `run_task_evaluations`, 0 `run_generation_turns`.
  - `persist-outputs` had no live sandbox to publish because sandbox setup used the default manager, while `ResearchRubricsResearcherWorker` uses `ResearchRubricsSandboxManager` for `publisher_sync()`.
  - `evaluate_task_run()` reconstructed an empty `BenchmarkTask`, so task-payload-driven ResearchRubrics criteria had no rubrics.
- Fix applied:
  - Registered `ResearchRubricsSandboxManager` for `researchrubrics`, `researchrubrics-ablated`, and `researchrubrics-vanilla`.
  - Merged data registry sandbox managers into the composed builtin registry.
  - Reconstructed the real `BenchmarkTask` in `evaluate_task_run()` from `ExperimentDefinitionTask` and `ExperimentDefinitionInstance`, preserving description and `task_payload`.
- Verification:
  - Command: `uv run pytest tests/unit/state/test_research_rubrics_benchmark.py tests/unit/smoke_base/test_registry_smoke_entries.py -q`
  - Result: `13 passed`.
  - Command: `uv run python - <<'PY' ... print(SANDBOX_MANAGERS['researchrubrics'].__name__)`
  - Result: `ResearchRubricsSandboxManager`.

### 13:24 UTC+1 - Report tool still simulated, not sandbox-backed

- Ran another corrected-stack rollout (`6f454cb7-bbc8-460f-9572-9bce620c6976`).
- Result: harness passed, but still produced 0 resources and 0 evaluations.
- Evidence:
  - Context events captured `write_report_draft` and `final_result`.
  - No `file.write` sandbox events and no `RunResource` rows.
- Root cause:
  - `_run_skill.py` is explicitly a stub skill runner: it asks the model to fabricate structured responses instead of calling real tools.
  - Therefore `write_report_draft` could return `kind='success'` without actually writing `/workspace/final_output/report.md`.
- Fix applied:
  - `ResearchRubricsResearcherWorker` now intercepts `write_report_draft`, `edit_report_draft`, and `read_report_draft` and executes them against the live E2B sandbox.
  - The existing model-backed skill runner remains in place for Exa-style research calls for now.
  - Real rollout harness now waits up to 300s after terminal status for at least one resource and evaluation row before dumping artifacts, so post-completion evaluation/resource writes are included when they land.
- Verification:
  - Command: `uv run pytest tests/unit/state/test_research_rubrics_workers.py tests/unit/state/test_research_rubrics_benchmark.py -q`
  - Result: `9 passed`.

### 13:18 UTC+1 - First sandbox-backed report resource captured

- Ran real rollout `b4bb5efd-0900-4fd6-a01a-5b9daee010ea`.
- Result:
  - Harness passed: `1 passed, 6 warnings in 484.44s`.
  - Artifact directory: `tests/real_llm/.rollouts/20260425T121827Z-b4bb5efd-0900-4fd6-a01a-5b9daee010ea/`.
  - `RunResource` now contains `report.md`, `kind='report'`, `size_bytes=12476`, with `metadata_json.sandbox_origin='/workspace/final_output/report.md'`.
- Remaining issue:
  - `evaluate-task-run` was invoked but failed before persisting `RunTaskEvaluation`.
  - Because the error was only visible as an Inngest `function.failed` event, the rollout had no durable evaluator failure details.
- Fix applied:
  - Simplified `InngestCriterionExecutor` from `ctx.group.parallel(...)` to sequential `ctx.step.run(...)` execution, avoiding an unverified parallel step path while debugging.
  - `evaluate_task_run` now logs evaluator exceptions and persists a failed `RunTaskEvaluation` row containing the error type/message, so future rollout artifacts preserve evaluator failures instead of dropping them.
- Verification:
  - Command: `uv run pytest tests/unit/state/test_research_rubrics_benchmark.py tests/unit/state/test_research_rubrics_workers.py -q`
  - Result: `9 passed`.

### 13:25 UTC+1 - Evaluator registry and final output extraction fixed

- Root cause for missing `RunTaskEvaluation`:
  - Experiment definitions persist the evaluator class `type_slug`, `researchrubrics-rubric`.
  - The registry only exposed the CLI slug, `research-rubric`, so `evaluate-task-run` failed during evaluator lookup.
- Fix applied:
  - Added `researchrubrics-rubric` as an alias in `registry_data.EVALUATORS`.
  - Added regression coverage that both the CLI slug and persisted type slug resolve to `ResearchRubricsRubric`.
- Manual verification:
  - Re-sent `task/evaluate` for run `b4bb5efd-0900-4fd6-a01a-5b9daee010ea`.
  - Result: one `RunTaskEvaluation` row persisted and dashboard emitted `task.evaluation_updated`.
- New observation:
  - The evaluation scored 0 because `RunTaskExecution.final_assistant_message` was empty.
  - The ReAct agent emitted the final answer as a structured `final_result` tool call, not as an `assistant_text` event.
- Fix applied:
  - `ReActWorker.get_output()` now falls back to the latest `final_result.args.final_assistant_message` when no assistant-text event exists.
- Verification:
  - Command: `uv run pytest tests/unit/state/test_research_rubrics_benchmark.py tests/unit/state/test_research_rubrics_workers.py -q`
  - Result: `10 passed`.

### 13:35 UTC+1 - Final telemetry verification rollout

- Ran final full rollout `b395b9e7-b111-4f2d-9df2-49829d5dff75`.
- Result:
  - Harness passed: `1 passed, 6 warnings in 211.61s`.
  - Run summary now refreshes after evaluation:
    - `final_score=1.0`
    - `normalized_score=1.0`
    - `evaluators_count=1`
  - `RunResource` rows include:
    - `report.md`, `kind='report'`, `size_bytes=12896`, `sandbox_origin='/workspace/final_output/report.md'`
    - `worker_output`, `kind='output'`, `size_bytes=2189`
  - `RunTaskEvaluation` persisted:
    - score `1.0`, passed `True`
    - criterion 0 (`Response is non-empty`) passed with score `1.0`
    - criterion 1 (`Response is relevant`) passed with score `0.5`
  - Sandbox WAL now captures report file I/O:
    - `sandbox.created`
    - `files.write /workspace/final_output/report.md`
    - `sandbox.closed: completed`
- This is now a usable manual rollout artifact for debugging: context events, report resources, worker output, evaluation, run summary, and sandbox file-write telemetry all land in Postgres/artifacts.

### 13:30 UTC+1 - Complete rollout artifact verified

- Ran fresh full rollout `3c3cb9de-4c26-4624-9b6c-771e1a93b7f2`.
- Result:
  - Harness passed: `1 passed, 6 warnings in 201.77s`.
  - Artifact directory: `tests/real_llm/.rollouts/20260425T122920Z-3c3cb9de-4c26-4624-9b6c-771e1a93b7f2/`.
  - `RunTaskExecution.final_assistant_message` is populated (`2497` chars).
  - `RunResource` rows include:
    - `report.md`, `kind='report'`, `size_bytes=12383`, `sandbox_origin='/workspace/final_output/report.md'`.
    - `worker_output`, `kind='output'`, `size_bytes=2537`.
  - `RunTaskEvaluation` row persisted with score `1.0`, passed `True`, normalized score `0.6666666667`.
- Remaining polish:
  - `RunRecord.summary_json` is finalized before async evaluation lands, so the live row still reported `evaluators_count=0` after the run.
- Fix applied:
  - `evaluate_task_run` now refreshes `RunRecord.summary_json` after persisting successful or failed evaluator rows.
  - Sandbox-backed report read/write tools now emit WAL entries (`files.read ...`, `files.write ...`) and register created files, so future rollouts should show actual report I/O in sandbox command telemetry.
- Verification:
  - Command: `uv run pytest tests/unit/state/test_research_rubrics_benchmark.py tests/unit/state/test_research_rubrics_workers.py -q`
  - Result: `10 passed`.

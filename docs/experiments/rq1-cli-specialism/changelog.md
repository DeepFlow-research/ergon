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



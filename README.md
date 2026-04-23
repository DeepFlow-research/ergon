# Ergon

A research runtime for agentic reinforcement learning.

Ergon manages the full lifecycle: define benchmarks, run agent tasks in sandboxed environments, evaluate outputs with configurable judges, and feed results into RL training loops.

## Etymology

*Ergon* (ἔργον) — from Greek, meaning "characteristic function" or "purposeful work."

In Aristotle's *Nicomachean Ethics*, every agent has an *ergon* — the fullest expression of its capabilities. Reinforcement learning is the process by which agents discover and perfect their ergon: the actualization (*energeia*, ἐνέργεια — literally "the work within") of latent potential (*dynamis*) through purposeful action.

The word is the root of *energy* (en + ergon, "the work within"), *synergy* (syn + ergon, "working together"), and *ergodic* (exploring the full state space) — spanning single-agent training, multi-agent coordination, and exploration.

Ergon is the successor to [Manager Agent Gym (MA Gym)](link), redesigned as a modular, strongly-typed platform with distributed RL training, persistent state, and production orchestration.

## Architecture

UV workspace with four Python packages and a Next.js dashboard:

| Package | Description |
|---------|-------------|
| `ergon_core/` | Core library — FastAPI app, persistence, Inngest runtime, RL adapters, sandbox providers |
| `ergon_builtins/` | Built-in benchmarks, workers, evaluators, criteria, and rubrics |
| `ergon_cli/` | CLI (`ergon` command) — benchmark, train, run, eval |
| `ergon_infra/` | Infrastructure — TRL training runner, SkyPilot provisioning, deployment templates |
| `ergon-dashboard/` | Next.js frontend dashboard |

## Quickstart

**Prerequisites:** Python 3.13+, [uv](https://docs.astral.sh/uv/), Node.js 20+, [pnpm](https://pnpm.io/), Docker

```bash
# Clone and install
git clone https://github.com/DeepFlow-research/ergon.git
cd ergon
uv sync --all-packages --group dev

# Copy env and fill in your keys
cp .env.example .env

# Start the stack (Postgres, API, Inngest, dashboard)
docker compose up

# Run a benchmark
ergon benchmark run smoke_test
```

## Configuration

Copy `.env.example` to `.env` and set your provider keys:

- `OPENAI_API_KEY` — Required for LLM-based evaluation
- `E2B_API_KEY` — Required for sandboxed code execution
- `ERGON_DATABASE_URL` — Postgres connection string (default provided in docker-compose)

See `.env.example` for the full list.

## Development

```bash
# Lint, format, type-check (backend + frontend)
pnpm run check:fast

# Backend only
pnpm run check:be

# Tests
pnpm run test:be:fast       # Unit/state tests
pnpm run test:be:e2e        # E2E (requires Docker stack)

# Ruff autofix
uv run ruff check --fix ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
uv run ruff format ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
```

## Open refactors (to-do)

### Collapse `node_id` + `task_id` to a single runtime identity

**Problem.** Runtime DTOs and Inngest events carry both `task_id: UUID | None` and `node_id: UUID | None` — two fields that refer to the same thing in practice. Every graph-node IS a task; every task execution IS a node. The two identifiers exist because `task_id` historically meant "the static `ExperimentDefinitionTask` FK" while `node_id` meant "the runtime `RunGraphNode` PK." Dynamically-spawned subtasks (`add_subtask`) have no static FK, so `task_id` is `None` for them — which leaks through the type system as `UUID | None` on every downstream DTO and event.

This bit us on 2026-04-23: `PreparedTaskExecution.task_id: UUID` rejects `None` from a dynamic subtask, every subtask stays wedged in `RUNNING`, no `error_json` gets written (because the `except` handler has its own bug: references `prepared` before it's guaranteed bound). Full write-up: [`docs/bugs/open/2026-04-23-inngest-function-failures.md`](docs/bugs/open/2026-04-23-inngest-function-failures.md) § A.

**Fix.** One runtime identity, one field, always present:

```
task_id: UUID                     # THE identity — = run_graph_nodes.id
definition_task_id: UUID | None   # honestly nullable — FK to static declaration, absent for dynamic tasks
execution_id: UUID                # attempt-level (retries get new executions; task_id stays)
```

Changes:

1. **DTOs + events** (`orchestration_dto.py`, `task_events.py`): drop `node_id`, rename current `task_id: UUID | None` → `definition_task_id: UUID | None`, promote the runtime identity to `task_id: UUID` (non-null).
2. **Service layer** (`task_execution_service.py` + callers): read `task_id` where currently reading `node_id`; read `definition_task_id` only where the static FK is genuinely needed. `_emit_task_status`'s `if node_id is None: return` early-return disappears — the field can't be null.
3. **Dashboard emitters**: the `task_id=node_id` alias hack at `task_execution_service.py:53` goes away.
4. **DB columns** (optional second pass): `run_task_executions.node_id` → `run_task_executions.task_id` via Alembic. `run_graph_nodes.id` already serves as the task_id; `definition_task_id` already exists on both tables. Non-blocking — the rename is cosmetic/queryability-only.

**Separate smaller fix (do first).** The except handler in `execute_task.py:251-262` references `prepared` before assignment. Hoist `execution_id: UUID | None = None` and `node_id` above the `try` block so `finalize_failure` runs even when the prepare step is the thing that raised. This alone doesn't fix the stuck-task bug but it surfaces the real error in `error_json` + `TaskFailedEvent` on every future regression.

**Risk.** Event-shape change — old-shape events in the Inngest queue at cutover will fail. Mitigations: drain the queue before deploy, or accept both field names via `AliasChoices` + log-warn-on-old-name during the rollover window.

**Scope.** ~20-30 files. Mostly mechanical after the DTO changes — `ty` walks the rest.

## License

Apache 2.0 — see [LICENSE](LICENSE).

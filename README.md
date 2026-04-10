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

## License

Apache 2.0 — see [LICENSE](LICENSE).

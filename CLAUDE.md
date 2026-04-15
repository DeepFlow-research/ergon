# Ergon

Monorepo for the Ergon research runtime for agentic reinforcement learning.

## Environment setup

From the repo root, install the workspace and dev tools (including **slopcop** from PyPI, pinned in `uv.lock`):

```bash
uv sync --all-packages --group dev
```

Equivalent: `uv pip install slopcop` (or `pip install slopcop`) after activating the same venv; the lockfile pins `slopcop>=0.1.0` for reproducible CI.

Do not rely on a sibling `../slopcop` checkout or `cargo build` for slopcop; CI and `package.json` use `uv run slopcop`.

## Workspace structure

UV workspace with four Python packages and a Next.js dashboard:

- `ergon_core/` — Core library: public API types, FastAPI app, persistence, Inngest runtime, RL adapters, providers
- `ergon_builtins/` — Built-in benchmarks, workers, evaluators, criteria, rubrics, registries
- `ergon_cli/` — CLI (`ergon` command): benchmark, train, run, eval commands
- `ergon_infra/` — Infrastructure: TRL training runner, SkyPilot provisioning, deployment templates
- `ergon-dashboard/` — Next.js frontend dashboard (pnpm)
- `tests/` — Integration, e2e, and state tests
- `scripts/` — Standalone entrypoints (e.g. TRL GRPO training)

## Checks (`package.json`)

Commands wired at the repo root:

```bash
pnpm run check:be    # ruff lint + format + ty + slopcop
pnpm run check:fe    # eslint + tsc (ergon-dashboard)
pnpm run check:fast  # check:be then check:fe
```

CI runs the same steps as `pnpm run check:fast` (see `.github/workflows/ci-fast.yml`).

Individual backend scripts: `check:be:lint`, `check:be:fmt`, `check:be:type`, `check:be:slopcop`.

Ruff autofix:

```bash
uv run ruff check --fix ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
uv run ruff format ergon_core ergon_builtins ergon_cli ergon_infra tests scripts
```

## Tests

```bash
pnpm run test:be:fast   # Fast unit/state tests
pnpm run test:be:e2e    # E2E tests (requires Docker stack)
```

## Git workflow

**Trunk-based development on `main`.** Commit directly to `main` — do not create feature branches or git worktrees. No PRs unless explicitly requested.

When a feature branch is needed (e.g. for a PR review), use the `feature/<name>` prefix. PRs from `feature/*` branches automatically run the full E2B sandbox I/O test suite in CI.

## Key conventions

- Python 3.13+, line length 100
- Ruff for linting and formatting (no black/isort/flake8)
- `ty` for type checking (not mypy)
- New workspace members: add paths in `package.json` and `.github/workflows/ci-fast.yml`
- `slopcop`: `no-print` is ignored in CLI, infra, rendering, tests, and scripts (see `[tool.slopcop]` in `pyproject.toml`)

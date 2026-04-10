# Arcane Extension

Monorepo for the Arcane experiment orchestration platform.

## Environment setup

From the repo root, install the workspace and dev tools (including **slopcop** from PyPI, pinned in `uv.lock`):

```bash
uv sync --all-packages --group dev
```

Equivalent: `uv pip install slopcop` (or `pip install slopcop`) after activating the same venv; the lockfile pins `slopcop>=0.1.0` for reproducible CI.

Do not rely on a sibling `../slopcop` checkout or `cargo build` for slopcop; CI and `package.json` use `uv run slopcop`.

## Workspace structure

UV workspace with four Python packages and a Next.js dashboard:

- `h_arcane/` — Core library: public API types, FastAPI app, persistence, Inngest runtime, RL adapters, providers
- `arcane_builtins/` — Built-in benchmarks, workers, evaluators, criteria, rubrics, registries
- `arcane_cli/` — CLI (`arcane` command): benchmark, train, run, eval commands
- `arcane_infra/` — Infrastructure: TRL training runner, SkyPilot provisioning, deployment templates
- `arcane-dashboard/` — Next.js frontend dashboard (pnpm)
- `tests/` — Integration, e2e, and state tests
- `scripts/` — Standalone entrypoints (e.g. TRL GRPO training)

## Checks (`package.json`)

Commands wired at the repo root:

```bash
pnpm run check:be    # ruff lint + format + ty + slopcop
pnpm run check:fe    # eslint + tsc (arcane-dashboard)
pnpm run check:fast  # check:be then check:fe
```

CI runs the same steps as `pnpm run check:fast` (see `.github/workflows/ci-fast.yml`).

Individual backend scripts: `check:be:lint`, `check:be:fmt`, `check:be:type`, `check:be:slopcop`.

Ruff autofix:

```bash
uv run ruff check --fix h_arcane arcane_builtins arcane_cli arcane_infra tests scripts
uv run ruff format h_arcane arcane_builtins arcane_cli arcane_infra tests scripts
```

## Tests

```bash
pnpm run test:be:fast   # Fast unit/state tests
pnpm run test:be:e2e    # E2E tests (requires Docker stack)
```

## Key conventions

- Python 3.13+, line length 100
- Ruff for linting and formatting (no black/isort/flake8)
- `ty` for type checking (not mypy)
- New workspace members: add paths in `package.json` and `.github/workflows/ci-fast.yml`
- `slopcop`: `no-print` is ignored in CLI, infra, rendering, tests, and scripts (see `[tool.slopcop]` in `pyproject.toml`)

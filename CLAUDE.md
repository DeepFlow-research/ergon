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

When a feature branch is needed (e.g. for a PR review), use the `feature/<name>` prefix.

### Expensive E2E CI (`.github/workflows/e2e-benchmarks.yml`)

The `E2E Benchmarks` workflow spins up the full docker-compose stack and burns real LLM + E2B sandbox credits. It is deliberately **not** triggered on every push. Trigger posture:

- `pull_request: types: [opened, reopened, labeled]` — runs on PR creation and whenever the `run-e2e` label is added. Missing `synchronize` on purpose: pushes do **not** refire it.
- `workflow_dispatch` — manual dispatch from the Actions UI.

Branch protection on `main` requires `e2e-researchrubrics-demo` + `e2e-minif2f-demo` to have reported green *at some point* in the PR's history (`strict: false` — "require branches up to date" is off). A single pass is enough to unblock merge.

**Agent protocol when opening or updating PRs:**

1. **Substantive changes (any PR touching `ergon_core/`, `ergon_builtins/`, `ergon_cli/`, `ergon_infra/`, `tests/e2e/`, `docker-compose.ci.yml`, `Dockerfile`, or the workflow itself):** add the `run-e2e` label immediately after opening the PR so the e2e workflow runs at least once against the PR head:
   ```bash
   gh pr edit <num> -R DeepFlow-research/ergon --add-label run-e2e
   ```
   Docs-only / README / comment-only / CI-config-that-doesn't-affect-e2e PRs don't need the label.

2. **If the e2e job fails and you push a fix:** the push by itself will **not** re-run the workflow (no `synchronize`). Re-trigger one of these ways:
   - Remove and re-add the label:
     ```bash
     gh pr edit <num> -R DeepFlow-research/ergon --remove-label run-e2e
     gh pr edit <num> -R DeepFlow-research/ergon --add-label run-e2e
     ```
   - Or dispatch manually:
     ```bash
     gh workflow run "E2E Benchmarks" -R DeepFlow-research/ergon --ref <branch>
     ```
   Repeat until it passes against the current HEAD.

3. **Once it has passed once for a given PR, do not keep re-running it.** Subsequent small commits don't need fresh e2e runs — branch protection's `strict: false` means the original pass still counts. Only re-run if a later commit is itself substantive enough that the prior pass no longer represents the code being merged.

The goal: every merged PR has had at least one successful e2e run against code close to what's being merged, without paying for an e2e run on every commit.

## Key conventions

- Python 3.13+, line length 100
- Ruff for linting and formatting (no black/isort/flake8)
- `ty` for type checking (not mypy)
- New workspace members: add paths in `package.json` and `.github/workflows/ci-fast.yml`
- `slopcop`: `no-print` is ignored in CLI, infra, rendering, tests, and scripts (see `[tool.slopcop]` in `pyproject.toml`)

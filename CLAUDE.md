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

## Architecture docs (canonical reference)

Single source of truth on how the system works today: [`docs/architecture/`](docs/architecture/README.md).

Every feature PR either (a) **cites** the architecture section(s) it relies on, or
(b) **updates** those sections if it changes an invariant, adds an extension point,
or removes an anti-pattern offender. Cross-cutting changes (artifacts, sandbox
lifecycle, error propagation) must update `docs/architecture/cross_cutting/`
explicitly. PRs that break an invariant without updating the doc are NAK'd
regardless of test state.

## RFCs and bugs

**New feature or architectural change:**
  1. Pre-RFC brainstorm (optional) → `docs/superpowers/brainstorms/YYYY-MM-DD-<slug>.md` via `superpowers:brainstorming`.
  2. RFC → `docs/rfcs/active/YYYY-MM-DD-<slug>.md` using [`docs/rfcs/TEMPLATE.md`](docs/rfcs/TEMPLATE.md).
  3. Plan → `docs/superpowers/plans/YYYY-MM-DD-<slug>.md` via `superpowers:writing-plans`.
  4. On merge: move RFC `active/` → `accepted/`; update `docs/architecture/` if invariants changed.

**Bug report:**
  1. File at `docs/bugs/open/YYYY-MM-DD-<slug>.md` using [`docs/bugs/TEMPLATE.md`](docs/bugs/TEMPLATE.md).
  2. If the fix is non-trivial, promote to an RFC and link it in the bug's `related_rfc` field.
  3. On merge: move `open/` → `fixed/`, set `fixed_pr` in frontmatter.

**Superpowers skill outputs (these preferences override skill defaults):**
  - `superpowers:brainstorming` → `docs/superpowers/brainstorms/`
  - `superpowers:writing-plans` → `docs/superpowers/plans/` (skill default, unchanged)
  - `superpowers:debugging` → write RCAs into `docs/bugs/open/`; if the fix is non-trivial, follow with an RFC in `docs/rfcs/active/`.

**Status lives in the folder, not the frontmatter.** `ls docs/rfcs/active/`
and `ls docs/bugs/open/` are the canonical "what's in flight" queries. When an
RFC is accepted or a bug fixed, move the file — don't just flip a frontmatter
field.

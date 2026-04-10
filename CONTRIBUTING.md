# Contributing to Ergon

Thanks for your interest in contributing.

## Getting started

1. Fork the repo and clone your fork
2. Install dependencies: `uv sync --all-packages --group dev`
3. Copy `.env.example` to `.env` and fill in required keys
4. Run checks: `pnpm run check:fast`
5. Run tests: `pnpm run test:be:fast`

## Making changes

- Create a branch from `main`
- Keep PRs focused — one feature or fix per PR
- Add tests for new functionality
- Make sure `pnpm run check:fast` passes before opening a PR

## Code style

- Python 3.13+, line length 100
- Ruff for linting and formatting (no black/isort/flake8)
- `ty` for type checking (not mypy)
- `slopcop` for code quality checks

## Reporting issues

Open a GitHub issue with a clear description and steps to reproduce.

## Questions

Open a GitHub issue or reach out to the maintainer at cm2435@users.noreply.github.com.

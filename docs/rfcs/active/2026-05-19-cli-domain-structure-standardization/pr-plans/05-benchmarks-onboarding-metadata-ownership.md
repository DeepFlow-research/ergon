# PR 05: Benchmarks And Onboarding Metadata Ownership

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move benchmark setup/dependency/onboarding truth out of generic CLI
code and toward builtins-owned metadata.

**Architecture:** Builtins owns benchmark metadata. CLI consumes that metadata
through typed benchmark/onboarding domain services.

**Tech Stack:** Pydantic v2 metadata models, CLI domain services, pytest.

---

## Goal

Stop duplicating benchmark template, dependency, and onboarding metadata inside
generic CLI command code.

## Source PRDs

- `../README.md`
- `../01-smell-remediation-map.md`
- `../02-target-folder-shape.md`
- `../prds/00-cli-hygiene-audit.md`

## Scope

## Current State

Benchmark setup paths, benchmark dependencies, and onboarding env-key sections
are hardcoded in CLI modules. That creates drift between builtins, onboarding,
and benchmark setup commands.

## Target State For This PR

Builtins exposes benchmark metadata; CLI benchmark/onboarding domains consume
that metadata. Every env key has an owner category.

## Tasks

### Move benchmark metadata toward builtins ownership

Create or modify:

```text
ergon_builtins/ergon_builtins/benchmarks/catalog.py
ergon_builtins/ergon_builtins/benchmarks/<slug>/metadata.py
```

Modify:

```text
ergon_cli/ergon_cli/domains/benchmarks/
ergon_cli/ergon_cli/commands/benchmark.py
```

Work:

- [ ] **Step 1: Add builtins metadata model**

  Define a Pydantic model similar to:

  ```python
  class BenchmarkCliMetadata(BaseModel):
      model_config = ConfigDict(frozen=True)

      slug: str
      sandbox_template: Path | None = None
      required_packages: tuple[str, ...] = ()
      env_keys: tuple[str, ...] = ()
      supports_setup: bool = False
  ```

- [ ] **Step 2: Add catalogue access**

  Add a function such as:

  ```python
  def benchmark_cli_metadata() -> Mapping[str, BenchmarkCliMetadata]: ...
  ```

- [ ] **Step 3: Update CLI benchmark setup**

  Replace local template dictionaries with calls into the metadata catalogue.

Acceptance:

- Adding a benchmark sandbox template does not require editing generic CLI
  command handlers.
- CLI no longer needs benchmark-specific path arithmetic.

### Reconcile onboarding dependency metadata

Move or modify:

```text
ergon_cli/ergon_cli/onboarding/profile.py
ergon_cli/ergon_cli/domains/onboarding/profile.py
ergon_cli/ergon_cli/domains/onboarding/env_writer.py
```

Work:

- [ ] **Step 1: Verify package extras**

  Compare onboarding recommendations against actual package metadata.

- [ ] **Step 2: Classify env keys**

  Introduce owner categories:

  ```python
  EnvKeyOwner = Literal[
      "core-runtime",
      "model-provider-runtime",
      "benchmark-evaluation-runtime",
      "infra-training-runtime",
      "local-networking-dev",
  ]
  ```

- [ ] **Step 3: Decide Tailscale keys**

  Keep Tailscale keys only if they are explicitly classified as
  `local-networking-dev`; otherwise delete them.

- [ ] **Step 4: Update tests**

  Assert every written env key has an owner category.

Acceptance:

- Every env key written by onboarding has an owner category.
- Recommended extras install from the repo.
- Onboarding profile tests cover at least one infra/training selection.

### Move benchmark/onboarding domains into final shape

Create:

```text
ergon_cli/ergon_cli/domains/benchmarks/
  __init__.py
  parser.py
  commands.py
  models.py
  service.py
  templates.py

ergon_cli/ergon_cli/domains/onboarding/
  __init__.py
  parser.py
  commands.py
  service.py
  profile.py
  env_writer.py
  installer.py
  prompts.py
```

Work:

- [ ] **Step 1: Move files into domain package**

  Move onboarding implementation into `domains/onboarding/` and benchmark setup
  into `domains/benchmarks/`.

- [ ] **Step 2: Preserve command UX**

  Existing command names and prompts should continue to work.

- [ ] **Step 3: Remove redundant compatibility imports**

  Delete old top-level modules only when no production imports remain.

Acceptance:

- Benchmark and onboarding command code follows the typed command model pattern
  introduced in PR 03.

## Tests

Add or update:

- benchmark metadata/catalog tests
- benchmark setup tests
- onboarding profile tests
- env writer tests

Run:

```bash
uv run ruff check ergon_cli/ergon_cli ergon_builtins/ergon_builtins
uv run pytest ergon_cli/tests/unit/cli
uv run pytest ergon_builtins/tests/unit
```

## PR Ledger

- **Invariant landed:** benchmark setup/onboarding metadata is no longer owned
  by generic CLI command code.
- **Bridge code introduced:** builtins metadata catalogue.
- **Old path still intentionally alive:** any remaining compatibility import
  shims until PR 06.
- **Deletion gate:** PR 06 removes old onboarding/benchmark command paths.
- **Tests added or updated:** metadata catalogue, benchmark setup, onboarding
  profile/env writer tests.
- **Modules owned by this PR:** builtins benchmark metadata, CLI benchmark
  domain, CLI onboarding domain.

## Out Of Scope

- Full final deletion of all old compatibility packages.
- Runs/experiments service boundary.

## Depends On

- PR 03
- PR 04 optional, but recommended first if shared patterns are needed

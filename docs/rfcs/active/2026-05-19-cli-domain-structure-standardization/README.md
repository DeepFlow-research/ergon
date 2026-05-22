---
status: active
opened: 2026-05-19
author: codex
architecture_refs:
  - ../../../architecture/01_public_api.md
  - ../../../architecture/06_builtins.md
  - ../../../architecture/07_testing.md
supersedes: []
superseded_by: null
---

# RFC: CLI Domain Structure Standardization

## Problem

`ergon_cli` currently works, but its internal shape does not match the
standards that `ergon_core` and `ergon_builtins` are converging on.
The CLI package is organized as a flat `commands/` bag plus a large central
`main.py` parser. As a result, command modules mix argument parsing, domain
validation, direct database access, rendering, optional dependency handling,
and calls into `ergon_core`, `ergon_ingestion`, or `ergon_infra`.

That shape has several costs:

- `argparse.Namespace` travels too far into the implementation, so command
  inputs stay weakly typed.
- `main.py` knows every flag for every command, turning the entrypoint into a
  central registry and making unrelated changes conflict-prone.
- Some commands reach directly into SQLModel sessions and persistence models,
  rather than going through core views/runtime services.
- Output formatting is interleaved with query and mutation logic.
- CLI-local concerns such as Docker Compose startup, `.env` writing, and E2B
  template setup sit beside observation commands with no shared boundary
  language.

This is not just aesthetic debt. The rest of the repo is moving toward explicit
domain boundaries, typed public contracts, architecture tests, and thin
adapters. The CLI should follow the same direction: it is an inbound terminal
adapter, not an alternate domain layer.

## Proposal

Restructure `ergon_cli` into domain-sliced packages. Each CLI domain owns its
parser registration, typed command/result models, command translation, and
thin service wrapper. Shared cross-domain utilities live under `shared/`.

Target structure:

```text
ergon_cli/
  ergon_cli/
    main.py
    app.py

    shared/
      env.py
      errors.py
      exit_codes.py
      output.py
      parsing.py

    domains/
      benchmarks/
        parser.py
        commands.py
        service.py
        models.py
        templates.py

      doctor/
        parser.py
        commands.py
        checks.py
        models.py

      eval/
        parser.py
        commands.py
        service.py
        models.py

      experiments/
        parser.py
        commands.py
        service.py
        models.py

      ingestion/
        parser.py
        commands.py

      onboarding/
        parser.py
        commands.py
        service.py
        profile.py
        env_writer.py
        installer.py
        prompts.py

      runs/
        parser.py
        commands.py
        service.py
        models.py

      stack/
        parser.py
        commands.py
        service.py
        models.py

      training/
        parser.py
        commands.py
        service.py
        models.py

      workflow/
        parser.py
        commands.py
        context.py
        executor.py
        models.py
```

`main.py` should become a composition root. It should build the top-level
parser, call per-domain parser registration functions, dispatch to per-domain
command handlers, and contain no domain-specific flags.

Sketch:

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ergon",
        description="Ergon experiment orchestration",
    )
    subparsers = parser.add_subparsers(dest="command")

    register_benchmark_parser(subparsers)
    register_doctor_parser(subparsers)
    register_eval_parser(subparsers)
    register_experiment_parser(subparsers)
    register_ingestion_parser(subparsers)
    register_onboarding_parser(subparsers)
    register_run_parser(subparsers)
    register_stack_parser(subparsers)
    register_training_parser(subparsers)
    register_workflow_parser(subparsers)

    return parser
```

Each domain follows the same four-file pattern unless it is genuinely tiny:

- `parser.py` registers argparse subcommands for that domain only.
- `commands.py` translates `argparse.Namespace` into typed command models and
  calls the domain service.
- `service.py` performs CLI-local work or delegates to the relevant
  `ergon_core`, `ergon_ingestion`, or `ergon_infra` API.
- `models.py` defines Pydantic models or dataclasses for command input and
  rendered result views.

The conversion from `Namespace` to typed command models happens at the domain
boundary. No service or lower-level helper accepts `argparse.Namespace`.

Example shape for `ergon run status <run-id>`:

```text
argparse.Namespace
  -> RunStatusCommand(run_id=UUID(...))
  -> RunsCliService.status(command)
  -> RunStatusView
  -> shared.output renders text/json/table
```

## Domain Boundaries

### `domains/runs`

Owns:

- `ergon run list`
- `ergon run status`
- `ergon run cancel`

The domain should not issue SQLModel queries directly. Read paths should call
`ergon_core.core.views.runs` services. Cancellation should continue to call the
core runtime cancellation function so event emission remains in one place.

### `domains/experiments`

Owns:

- `ergon experiment list`
- `ergon experiment show`
- `ergon experiment tags`
- `ergon experiment by-tag`

Experiment observation should be backed by
`ergon_core.core.views.experiments.service.ExperimentReadService` or a small
views-side method for tag queries. The CLI should not own the SQL shape of
experiment definition or run tables.

### `domains/benchmarks`

Owns:

- `ergon benchmark list`
- `ergon benchmark setup <slug>`

Template setup is legitimately CLI-local because it builds E2B templates and
writes local config under the user's environment. The benchmark catalogue
should not drift from builtins/onboarding metadata. If benchmark requirements
are declared on the `Benchmark` subclass, the CLI should consume that typed
source instead of maintaining a second static list.

### `domains/workflow`

Owns contextual workflow inspection commands, if the human CLI keeps them for
operator debugging:

- resource listing and reading
- task tree and dependency inspection
- next-action inspection

Workflow management commands such as task creation, dependency mutation,
restart/abandon actions, and sandbox resource materialization are not a human
CLI domain. The CLI-shaped management grammar belongs in `ergon_builtins` as an
agent toolkit over `WorkerContext`.

If workflow inspection remains in `ergon_cli`, it deserves strong typing because
it has nested command parsing and injected context. The injected context should
be represented as a typed `WorkflowCliContext` model. Nested workflow commands
must not be allowed to override injected runtime scope.

### `domains/onboarding`

Owns interactive setup, `.env` writing, and extras installation.
This domain already has useful internal concepts (`OnboardProfile`,
`write_env`, prompt helpers); move them under the domain folder and tighten the
typed contract around benchmark/provider requirements.

### `domains/doctor`

Owns environment health checks. Checks should return typed `DoctorCheckResult`
models, and rendering should happen separately. This makes doctor output stable
while keeping individual checks small and testable.

### `domains/stack`

Owns `ergon start` and `ergon stop`. This is a CLI-local adapter around Docker
Compose. It should remain simple, but service methods should return typed
results rather than directly mixing subprocess orchestration and printing.

### `domains/eval`

Owns checkpoint evaluation commands. It should remain a thin adapter around
`ergon_core.core.rl.eval_runner`, with typed command inputs for checkpoint
paths, benchmark slugs, evaluator slugs, model bases, limits, polling
intervals, and optional checkpoint hooks.

### `domains/training`

Owns training commands. Optional dependency checks for `ergon_infra` belong at
this boundary. The service should translate CLI flags into
`ergon_infra.training.config.TrainingConfig` and then delegate.

### `domains/ingestion`

Owns the CLI mounting point for ingestion. Short term, this can remain a thin
delegation adapter to `ergon_ingestion.cli.handle_ingest`. Long term, if
`ergon_ingestion` exposes typed command APIs, this domain can translate CLI
input into those APIs. Do not duplicate ingestion internals inside
`ergon_cli`.

## Invariants affected

This RFC introduces these CLI invariants:

- The CLI is an inbound adapter. It translates terminal input into typed
  command models and delegates domain behavior to CLI-local services or core
  views/runtime services.
- `argparse.Namespace` does not cross beyond `domains/*/commands.py`.
- `main.py` is a composition root. It does not contain domain-specific flags,
  SQL queries, output formatting, Docker orchestration, template setup, or
  optional dependency logic.
- `ergon_cli` does not directly query or mutate persistence state. It uses
  `ergon_core` views/runtime services or a narrow core API function.
- CLI services return typed result/view models. Rendering lives in
  `ergon_cli.shared.output`.
- Authoring remains Python-only. CLI observation commands must not reintroduce
  `ergon experiment define`, `ergon experiment run`, or equivalent flag-based
  authoring surfaces.
- CLI-local infrastructure commands (`start`, `stop`, `doctor`, `onboard`,
  `benchmark setup`) may perform local machine effects, but those effects are
  isolated to their domain services and are represented by typed command
  models.

These invariants align with:

- `docs/architecture/01_public_api.md`: contributor-facing authoring goes
  through typed API objects, not through a growing CLI flag surface.
- `docs/architecture/06_builtins.md`: built-in benchmark authoring is
  benchmark-owned and object-bound; CLI commands are observation/setup
  surfaces.
- `docs/architecture/07_testing.md`: architecture tests should enforce
  package boundaries and keep test fixtures out of production packages.

## Migration

Migrate in small PRs. Mechanical moves should be separated from behavior
changes.

### PR 1: Shared CLI primitives

Add:

- `ergon_cli/shared/output.py`
- `ergon_cli/shared/errors.py`
- `ergon_cli/shared/exit_codes.py`
- `ergon_cli/shared/parsing.py`
- `ergon_cli/domains/__init__.py`

Move table rendering from `ergon_cli/rendering` into `shared.output`, keeping a
compatibility import if needed for one PR.

### PR 2: Parser registration slices

Move parser registration out of `main.py` one domain at a time. Preserve the
same public CLI syntax. `main.py` should call each domain's
`register_<domain>_parser(...)`.

Acceptance:

- `ergon --help` and all existing subcommand helps remain equivalent.
- `main.py` no longer contains subcommand-specific arguments.

### PR 3: Typed command models

Introduce command models for each domain. Convert `Namespace` to a command
model in `commands.py` before calling services.

Acceptance:

- No service method accepts `argparse.Namespace`.
- Domain tests validate UUID/path/enum coercion at the command boundary.

### PR 4: Remove direct DB access from CLI

Move direct SQLModel queries out of `ergon_cli` for runs and experiments.
Add or reuse core views/runtime services for:

- experiment tags
- definitions by experiment tag
- run listing filters
- run listing by definition id
- run status detail

Acceptance:

- `rg "get_session|session.exec|session.get|select\\(" ergon_cli/ergon_cli`
  returns no offenders, except tests if needed.

### PR 5: Workflow domain cleanup

Move workflow command parsing/execution into `domains/workflow`. Fix typed
context handling and keep the nested parser isolated from top-level scope
flags.

Acceptance:

- Nested workflow commands reject user-supplied context flags.
- `WorkflowCliContext` is the only source of run/task/execution/sandbox scope.
- Existing workflow CLI tests move with the domain.

### PR 6: Architecture tests and docs

Add architecture tests that enforce the new boundary:

- `argparse.Namespace` appears only in `domains/*/commands.py` and parser
  modules.
- `main.py` imports only app/parser composition and dispatch helpers.
- no direct SQLModel session/query access in `ergon_cli`.
- no CLI authoring commands are registered.
- every domain has `parser.py` and `commands.py`; larger domains also have
  `service.py` and `models.py`.

Update `docs/architecture/` with a CLI inbound-adapter section or add a new
CLI-focused architecture page if the architecture tree wants that layer
explicitly documented.

## Alternatives considered

### Keep the flat `commands/` package and only split `main.py`

Rejected as insufficient. Moving parser registration out of `main.py` reduces
one source of chaos, but it leaves weak typing, direct DB access, and mixed
rendering/behavior inside command modules.

### Use horizontal packages: `parsers/`, `services/`, `models/`, `commands/`

Rejected for this repo. Horizontal layers scatter one domain across multiple
top-level directories. The rest of Ergon is moving toward domain ownership:
benchmarks own their task schemas, sandboxes, toolkits, worker factories,
criteria, and rubrics. The CLI should mirror that shape.

### Move all CLI behavior into `ergon_core`

Rejected. `ergon_core` should not learn about terminal concerns, Docker
Compose commands, prompt UX, `.env` writing, or E2B template setup. The right
direction is for CLI services to call core views/runtime services through
typed APIs, not for core to absorb CLI-specific responsibilities.

### Switch from `argparse` to Typer or Click

Deferred. A framework switch may improve ergonomics later, but it would not
fix the underlying boundary problem. The first refactor should keep public CLI
syntax stable and make the current argparse implementation clean and typed.

## Open questions

1. Should `ergon_cli` get its own `docs/architecture/09_cli.md`, or should CLI
   invariants live inside existing public API / builtins docs?
2. Should CLI result models be Pydantic models everywhere, or should simple
   dataclasses be allowed for purely internal views?
3. Should `benchmark list` consume benchmark metadata from
   `Benchmark.onboarding_deps` / builtins discovery instead of a CLI-local
   static table in the first migration stack, or should that wait for a
   follow-up?
4. Should ingestion continue delegating to `ergon_ingestion.cli` indefinitely,
   or should `ergon_ingestion` expose a typed command API for the CLI domain to
   consume?
5. Should architecture tests impose a line-count or complexity budget per CLI
   module, or is the domain layout plus lint/type rules enough?

## On acceptance

When this RFC moves from `active/` to `accepted`, also:

- update `docs/architecture/` with the accepted CLI inbound-adapter invariants;
- write an implementation plan under `docs/superpowers/plans/`;
- add architecture tests for the invariants listed above;
- decide whether the first PR stack should include the no-direct-DB-access
  move or leave that as the second stack after mechanical package cleanup.

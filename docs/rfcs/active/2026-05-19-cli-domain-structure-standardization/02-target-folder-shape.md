# Target CLI Folder Shape

This document records the intended `ergon_cli` source and test layout after
the CLI domain refactor. Paths are repo-relative from `ergon/`.

## Source Tree

```text
ergon_cli/
  pyproject.toml

  ergon_cli/
    __init__.py
    main.py
    app.py

    shared/
      __init__.py
      dependencies.py
      env.py
      errors.py
      exit_codes.py
      logging.py
      output.py
      parsing.py

    domains/
      __init__.py

      benchmarks/
        __init__.py
        commands.py
        models.py
        parser.py
        service.py
        templates.py

      doctor/
        __init__.py
        checks.py
        commands.py
        models.py
        parser.py
        service.py

      eval/
        __init__.py
        commands.py
        models.py
        parser.py
        service.py

      experiments/
        __init__.py
        commands.py
        models.py
        parser.py
        service.py

      ingestion/
        __init__.py
        commands.py
        parser.py

      onboarding/
        __init__.py
        commands.py
        env_writer.py
        installer.py
        models.py
        parser.py
        profile.py
        prompts.py
        service.py

      runs/
        __init__.py
        commands.py
        models.py
        parser.py
        service.py

      stack/
        __init__.py
        commands.py
        models.py
        parser.py
        service.py

      training/
        __init__.py
        commands.py
        models.py
        parser.py
        service.py

      workflow/
        __init__.py
        commands.py
        context.py
        executor.py
        models.py
        parser.py
```

## File Responsibilities

### Entrypoint

```text
ergon_cli/ergon_cli/main.py
```

Console script target. It should call `asyncio.run(app.run(argv))` and contain
no domain-specific parser registration or command behavior.

```text
ergon_cli/ergon_cli/app.py
```

Composition root. Owns:

- top-level parser construction;
- domain parser registration list;
- handler dispatch;
- async/sync handler invocation;
- top-level `CliError` rendering.

It should not contain subcommand-specific flags or business logic.

### Shared

```text
ergon_cli/ergon_cli/shared/dependencies.py
```

Optional dependency checks, such as `require_module("ergon_infra", ...)`.

```text
ergon_cli/ergon_cli/shared/env.py
```

Small environment/file helpers shared by CLI domains. Domain-specific `.env`
writing remains in onboarding.

```text
ergon_cli/ergon_cli/shared/errors.py
```

Shared `CliError` hierarchy.

```text
ergon_cli/ergon_cli/shared/exit_codes.py
```

`ExitCode` enum and constants.

```text
ergon_cli/ergon_cli/shared/logging.py
```

CLI logging setup for diagnostics. User-facing output should go through
`shared/output.py`.

```text
ergon_cli/ergon_cli/shared/output.py
```

Table, key-value, JSON, and error renderers.

```text
ergon_cli/ergon_cli/shared/parsing.py
```

Reusable parser helpers: UUID coercion, positive integer validation, output
format enums, and common argparse helpers.

### Domain File Contract

For each domain:

```text
ergon_cli/ergon_cli/domains/<domain>/parser.py
```

Registers argparse subcommands for that domain and sets handler callables.

```text
ergon_cli/ergon_cli/domains/<domain>/commands.py
```

Accepts `argparse.Namespace`, converts it to typed command models, calls the
domain service, invokes shared renderers, and returns an exit code.

```text
ergon_cli/ergon_cli/domains/<domain>/models.py
```

Typed command models and typed result/view models.

```text
ergon_cli/ergon_cli/domains/<domain>/service.py
```

CLI-domain behavior and delegation into `ergon_core`, `ergon_builtins`,
`ergon_ingestion`, or `ergon_infra`.

## Domain-Specific Notes

### Benchmarks

```text
ergon_cli/ergon_cli/domains/benchmarks/templates.py
```

E2B template specs and setup helpers for `ergon benchmark setup <slug>`.
This remains CLI-local because it builds local/remote template artifacts and
writes user config.

Longer-term, benchmark listing should consume a typed builtins catalogue rather
than a CLI-local static table.

### Doctor

```text
ergon_cli/ergon_cli/domains/doctor/checks.py
```

Pure-ish health check functions returning typed check results. Rendering lives
outside this file.

### Ingestion

```text
ergon_cli/ergon_cli/domains/ingestion/
```

This domain intentionally has no `service.py` or `models.py` in the first
target shape. It is a mounting/delegation adapter for
`ergon_ingestion.cli.handle_ingest`. Add models/service only if
`ergon_ingestion` later exposes typed command APIs.

### Onboarding

```text
ergon_cli/ergon_cli/domains/onboarding/profile.py
ergon_cli/ergon_cli/domains/onboarding/env_writer.py
ergon_cli/ergon_cli/domains/onboarding/installer.py
ergon_cli/ergon_cli/domains/onboarding/prompts.py
```

These are moved from the current `ergon_cli/onboarding/` package. They remain
domain-local because interactive prompts, `.env` writing, and `uv pip install`
are CLI setup concerns.

### Workflow

```text
ergon_cli/ergon_cli/domains/workflow/context.py
```

Typed injected workflow context: run id, node id, execution id,
sandbox-task key, and benchmark type.

```text
ergon_cli/ergon_cli/domains/workflow/executor.py
```

Nested workflow command executor. Should be async and should not call
`asyncio.run`.

```text
ergon_cli/ergon_cli/domains/workflow/models.py
```

Nested workflow command models and output models.

## Compatibility Modules To Delete

These current paths should disappear by the end of the refactor:

```text
ergon_cli/ergon_cli/bootstrap.py
ergon_cli/ergon_cli/commands/
ergon_cli/ergon_cli/discovery/
ergon_cli/ergon_cli/onboarding/
ergon_cli/ergon_cli/rendering/
```

If compatibility imports are needed during migration, keep them for one PR
only and delete them in the next slice.

## Test Tree

```text
ergon_cli/
  tests/
    unit/
      architecture/
        __init__.py
        test_domain_layout.py
        test_main_is_composition_root.py
        test_namespace_boundary.py
        test_no_cli_authoring_surface.py
        test_no_nested_asyncio_run.py
        test_no_persistence_access.py
        test_rendering_boundary.py

      domains/
        __init__.py

        benchmarks/
          __init__.py
          test_benchmark_commands.py
          test_benchmark_setup.py
          test_benchmark_parser.py

        doctor/
          __init__.py
          test_doctor_checks.py
          test_doctor_commands.py
          test_doctor_parser.py

        eval/
          __init__.py
          test_eval_commands.py
          test_eval_parser.py

        experiments/
          __init__.py
          test_experiment_commands.py
          test_experiment_parser.py

        ingestion/
          __init__.py
          test_ingestion_parser.py

        onboarding/
          __init__.py
          test_env_writer.py
          test_onboard_profile.py
          test_onboarding_commands.py
          test_onboarding_parser.py

        runs/
          __init__.py
          test_run_commands.py
          test_run_parser.py

        stack/
          __init__.py
          test_stack_commands.py
          test_stack_parser.py

        training/
          __init__.py
          test_training_commands.py
          test_training_parser.py

        workflow/
          __init__.py
          test_workflow_commands.py
          test_workflow_executor.py
          test_workflow_parser.py

      shared/
        __init__.py
        test_dependencies.py
        test_errors.py
        test_output.py
        test_parsing.py
```

## Final Import Shape

The intended high-level dependency direction is:

```text
main.py
  -> app.py
      -> domains/*/parser.py
      -> domains/*/commands.py
          -> domains/*/models.py
          -> domains/*/service.py
          -> shared/output.py
          -> shared/errors.py
              -> ergon_core / ergon_builtins / ergon_ingestion / ergon_infra
```

Forbidden directions:

```text
shared/ -> domains/*
domains/*/models.py -> ergon_core persistence models
domains/*/parser.py -> ergon_core persistence models
domains/*/service.py -> argparse.Namespace
main.py -> domains/*/models.py
main.py -> domains/*/service.py
```

Allowed direct external dependencies:

- `domains/runs/service.py` may call `ergon_core` run read/cancel APIs.
- `domains/experiments/service.py` may call `ergon_core` experiment read APIs.
- `domains/benchmarks/service.py` may call `ergon_builtins` catalogue APIs and
  the E2B SDK through `templates.py`.
- `domains/eval/service.py` may call `ergon_core.core.rl.eval_runner`.
- `domains/training/service.py` may import `ergon_infra` after an optional
  dependency check.
- `domains/ingestion/commands.py` may delegate to `ergon_ingestion.cli` until
  a typed ingestion API exists.

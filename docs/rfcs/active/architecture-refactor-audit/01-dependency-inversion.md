---
status: active
opened: 2026-04-27
author: GPT-5.5
architecture_refs:
  - docs/architecture/01_public_api.md
  - docs/architecture/03_providers.md
  - docs/architecture/06_builtins.md
supersedes: []
superseded_by: null
---

# RFC: Dependency Inversion And Package Boundaries

## Problem

The declared package graph says `ergon_core` is the reusable runtime and public
API, `ergon_builtins` supplies default implementations, `ergon_cli` adapts user
commands, and `ergon_infra` handles training/provisioning helpers. The source
graph is messier. Core runtime code imports the builtins registry, builtins
tooling imports CLI command modules, and test harness paths pull CLI
composition back into core.

These dependencies work in the workspace, but they blur ownership. A reader
cannot easily tell which package owns composition, which APIs are stable, or
how to add a new benchmark/worker without coupling to the current default
registry.

## Current findings

### Core runtime imports builtins registry

Runtime paths resolve slugs by importing `ergon_builtins.registry` directly.
This appears in Inngest handlers and services such as worker execution,
benchmark-run startup, evaluator dispatch, sandbox setup, output persistence,
and workflow initialization. The practical result is that core is not only a
runtime contract package; it also knows about the default plugin bundle.

### Builtins registry reaches into core internals

`ergon_builtins.registry` implements public `ergon_core.api` contracts, but it
also imports provider internals for model backend registration and sandbox
manager types. Some of this may be unavoidable today, but it should be named as
an extension boundary rather than an incidental import path.

### Builtins tooling imports CLI command code

`ergon_builtins.tools.workflow_cli_tool` imports `WorkflowCommandContext`,
`WorkflowCommandOutput`, and `execute_workflow_command` from
`ergon_cli.commands.workflow`. That makes an agent-facing builtin tool depend
on the CLI command layer instead of a shared application/service API.

### Core test harness imports CLI composition

`ergon_core.core.api.test_harness` imports `ergon_cli.composition` when the
test harness is enabled. The flag keeps this out of production by default, but
the import direction is still surprising for a core package.

### CLI composition contains example-specific branches

`ergon_cli.composition.build_experiment` performs registry lookup and then
branches for smoke workers and `researchrubrics-workflow-cli-react`. Those
branches may encode real composition needs, but they live in the generic CLI
composition path rather than behind benchmark/worker-owned composition hooks.

## Target shape

The target dependency direction should be:

```text
ergon_core.api        <- implemented by builtins and custom packages
ergon_core.runtime    <- depends on injected registries/services, not builtins
ergon_builtins        <- default implementation bundle
ergon_cli             <- adapter that wires a registry bundle into core services
ergon_infra           <- training/provisioning adapter over public/core services
ergon-dashboard       <- frontend over HTTP/event contracts
```

Core may define protocols and service interfaces. Builtins may implement them.
CLI and application startup may choose the default builtins registry. Runtime
code should receive a resolver or registry interface rather than importing the
default bundle.

## Standards proposed

- Public contracts belong under `ergon_core.api` or a deliberately named core
  interface module.
- A package should not import an adapter layer that is higher-level than
  itself. In particular, builtins should not import `ergon_cli.commands.*`.
- Runtime services should depend on protocols such as `WorkerResolver`,
  `BenchmarkResolver`, `EvaluatorResolver`, `SandboxManagerResolver`, or one
  combined `RuntimeRegistry`.
- Example-specific composition should be owned by the benchmark/worker bundle
  that requires it, or represented as data on the public API.
- Test-only composition should enter through explicit startup/plugin hooks, not
  direct core-to-cli imports.

## Candidate fixes

Each candidate below should be treated as a small implementation plan, not an
idea bucket. A follow-up implementation plan may split these into separate PRs,
but each candidate already names the files, steps, tests, and acceptance gate
expected before the work is considered real.

### DI-1: Add a runtime registry protocol in core

**Issue fixed:** Core runtime code cannot express "I need a worker/benchmark/evaluator
resolver" without importing the concrete builtins registry, so dependency
direction is encoded as an implementation detail instead of a contract.

Create a small protocol owned by core that contains the lookup methods runtime
code actually needs:

- `get_worker(slug)`
- `get_benchmark(slug)`
- `get_evaluator(slug)`
- `get_sandbox_manager(slug)`
- optional install-hint lookup for user-facing errors

Candidate location: `ergon_core.api.registry` if this becomes public extension
surface, or `ergon_core.core.runtime.registry` if it stays internal. The first
implementation can be an adapter around `ergon_builtins.registry`, preserving
all current slug names and optional-extra behavior.

Files:

- Create: `ergon_core/ergon_core/api/registry.py` or
  `ergon_core/ergon_core/core/runtime/registry.py`.
- Create: `ergon_builtins/ergon_builtins/runtime_registry.py`.
- Modify: `ergon_builtins/ergon_builtins/registry.py` only if the adapter needs
  a stable export.
- Test: `tests/unit/runtime/test_runtime_registry_contract.py`.

Sketch:

```python
from typing import Protocol

class RuntimeRegistry(Protocol):
    def get_worker(self, slug: str): ...
    def get_benchmark(self, slug: str): ...
    def get_evaluator(self, slug: str): ...
    def get_sandbox_manager(self, slug: str): ...
    def install_hint_for(self, slug: str) -> str | None: ...
```

Steps:

- [ ] Add the protocol and a typed missing-slug error or document that `KeyError`
      remains the compatibility behavior.
- [ ] Add a builtins-backed adapter over the existing registry dictionaries.
- [ ] Preserve model backend registration side effects at builtins registry
      import time.
- [ ] Add a fake in-memory registry for tests that should not import builtins.
- [ ] Keep existing public imports of `ergon_builtins.registry` working.

Verification:

- Unit tests for successful and missing slug lookup.
- Characterization test that CLI defaults still resolve the same worker,
  benchmark, evaluator, and sandbox manager classes.
- `python -c "from ergon_builtins.registry import WORKERS, BENCHMARKS"` still
  succeeds in the workspace environment.

Acceptance gate:

- [ ] Registry contract tests pass for both the fake registry and builtins
      adapter.
- [ ] No runtime behavior changes: current benchmark, worker, evaluator, and
      sandbox slugs resolve to the same objects.
- [ ] Architecture docs mention where registry protocols live.

### DI-2: Stop importing `ergon_builtins.registry` from core runtime modules

**Issue fixed:** `ergon_core` is declared as the reusable runtime package, but
runtime modules currently depend on the default builtins bundle at import time.
That makes builtins a hidden runtime prerequisite and prevents fake/custom
registries from being injected cleanly.

Replace direct registry imports in core runtime paths with an injected resolver
or application-level registry object. Initial target modules include:

- `core/runtime/inngest/benchmark_run_start.py`
- `core/runtime/inngest/worker_execute.py`
- `core/runtime/inngest/evaluate_task_run.py`
- `core/runtime/inngest/sandbox_setup.py`
- `core/runtime/inngest/persist_outputs.py`
- `core/runtime/services/workflow_initialization_service.py`
- `core/api/app.py`

The first pass can use a default registry provider at process startup so
behavior stays identical while import direction improves.

Files:

- Modify: `ergon_core/ergon_core/core/runtime/inngest/benchmark_run_start.py`.
- Modify: `ergon_core/ergon_core/core/runtime/inngest/worker_execute.py`.
- Modify: `ergon_core/ergon_core/core/runtime/inngest/evaluate_task_run.py`.
- Modify: `ergon_core/ergon_core/core/runtime/inngest/sandbox_setup.py`.
- Modify: `ergon_core/ergon_core/core/runtime/inngest/persist_outputs.py`.
- Modify:
  `ergon_core/ergon_core/core/runtime/services/workflow_initialization_service.py`.
- Modify: `ergon_core/ergon_core/core/api/app.py`.
- Test: `tests/unit/architecture/test_package_boundaries.py`.

Steps:

- [ ] Add a process-level registry provider or dependency accessor in core.
- [ ] Configure the builtins-backed registry from CLI/API startup.
- [ ] Convert each runtime module from `from ergon_builtins.registry import ...`
      to the registry accessor.
- [ ] Keep error messages for unknown slugs at least as clear as today.
- [ ] Remove any import-time builtins dependency from core runtime modules.

Verification:

- Architecture test that `ergon_core.core.runtime` does not import
  `ergon_builtins`.
- Existing benchmark/run tests continue to pass without slug changes.
- `rg "ergon_builtins.registry" ergon_core/ergon_core/core/runtime` returns no
  matches.

Acceptance gate:

- [ ] Direct runtime imports of `ergon_builtins.registry` are gone.
- [ ] Unknown-slug behavior is characterized and preserved or deliberately
      improved in a documented way.
- [ ] CLI/API startup still wires the default builtins registry.

### DI-3: Move workflow command execution out of the CLI command module

**Issue fixed:** Builtin agent tools reuse workflow behavior by importing
`ergon_cli.commands.workflow`, which makes a non-CLI package depend on CLI
command parsing/rendering code.

Extract the command parsing/execution core from `ergon_cli.commands.workflow`
into a shared service module that has no CLI rendering dependency. The CLI
command should parse argv and render output; builtin tools should call the same
shared executor directly.

Candidate owner: `ergon_core.core.runtime.services.workflow_command_service` if
the command surface is runtime-owned, or `ergon_cli.workflow_application` if it
is intentionally an application-layer adapter. The key rule is that
`ergon_builtins` should not import `ergon_cli.commands.*`.

Verification:

- Existing `tests/unit/cli/test_workflow_cli.py` still validates CLI behavior.
- New builtin-tool test imports the shared executor without importing the CLI
  command module.
- Architecture test blocks `ergon_builtins -> ergon_cli.commands`.

Files:

- Create:
  `ergon_core/ergon_core/core/runtime/services/workflow_command_service.py`
  or a similarly named shared application module.
- Modify: `ergon_cli/ergon_cli/commands/workflow.py`.
- Modify: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`.
- Test: `tests/unit/cli/test_workflow_cli.py`.
- Test: `tests/unit/state/test_workflow_cli_tool.py` or equivalent builtin
  tool test.

Steps:

- [ ] Identify the current command parser/executor/renderer responsibilities in
      `ergon_cli.commands.workflow`.
- [ ] Move parser and executor into the shared module without changing command
      strings.
- [ ] Leave stdout/stderr formatting and argparse integration in CLI.
- [ ] Update the builtin workflow tool to call the shared executor.
- [ ] Add an import-boundary test that prevents future builtin imports from
      `ergon_cli.commands`.

Acceptance gate:

- [ ] CLI workflow tests pass with unchanged expected output.
- [ ] Builtin workflow tool tests pass without importing CLI command modules.
- [ ] `rg "ergon_cli.commands" ergon_builtins/ergon_builtins/tools` returns no
      matches, except an explicit migration allowlist if needed.

### DI-4: Replace special-case CLI experiment branches with composition descriptors

**Issue fixed:** Generic CLI experiment composition contains hard-coded
knowledge of specific worker families, so every new example with special
bindings risks adding another `if worker_slug == ...` branch.

Move the smoke-worker and `researchrubrics-workflow-cli-react` branch knowledge
out of generic `build_experiment`. Candidate shape:

- Workers or benchmarks may expose an optional composition descriptor.
- The descriptor declares extra worker bindings, evaluator bindings, and static
  assignment strategy.
- `build_experiment` applies descriptors generically after registry lookup.

This keeps current behavior while making future examples add data rather than a
new `if worker_slug == ...` branch.

Verification:

- Characterization tests for smoke worker composition.
- Characterization tests for research-rubrics workflow composition.
- A test that a synthetic descriptor can add an extra worker binding without
  editing `ergon_cli.composition`.

Files:

- Modify: `ergon_cli/ergon_cli/composition/__init__.py`.
- Add: a composition descriptor type under `ergon_core.api` or
  `ergon_cli.composition`.
- Modify smoke fixture registration under
  `ergon_core/ergon_core/test_support/smoke_fixtures/`.
- Modify research-rubrics worker/benchmark registration under
  `ergon_builtins/ergon_builtins/workers/research_rubrics/` or
  `ergon_builtins/ergon_builtins/registry_data.py`.
- Test: `tests/unit/cli/test_build_experiment_composition.py`.

Current branches to eliminate from generic composition:

- `_is_smoke_worker(worker_slug)`.
- `worker_slug == "researchrubrics-workflow-cli-react"`.
- suffix parsing for `-smoke-worker` and `-sadpath-smoke-worker`.
- direct imports of smoke timing criteria from generic CLI composition.

Sketch:

```python
class ExperimentCompositionDescriptor(BaseModel):
    extra_workers: dict[str, WorkerSpec]
    extra_evaluators: dict[str, Evaluator]
    static_assignments: dict[str, list[str]]
```

Steps:

- [ ] Add the descriptor type and a no-op default descriptor.
- [ ] Teach `build_experiment` to ask the selected worker/benchmark registry
      entry for a descriptor.
- [ ] Move smoke leaf/recursive/failing-leaf bindings into smoke fixture-owned
      descriptor code.
- [ ] Move research-rubrics manager/researcher bindings into
      research-rubrics-owned descriptor code.
- [ ] Add an architecture test that blocks new hard-coded worker slug branches
      in `ergon_cli.composition`.

Acceptance gate:

- [ ] No generic composition branch checks a concrete worker slug.
- [ ] Existing smoke and research-rubrics composition behavior is unchanged.
- [ ] A synthetic descriptor test proves new special composition can be added
      without editing `build_experiment`.

### DI-5: Route smoke/test harness composition through startup plugins

**Issue fixed:** Test harness and smoke-fixture setup rely on direct imports
that blur production startup, CLI composition, and test-support registration.

Replace direct core-to-CLI composition imports in test-harness paths with the
same registry/composition extension point used by production startup. Smoke
fixtures can still be opt-in, but the opt-in should register providers through
a plugin hook rather than teaching core about CLI composition.

Verification:

- Test harness remains disabled by default.
- With `ENABLE_TEST_HARNESS=1`, smoke fixtures still register and run.
- Architecture test documents the only allowed test-support imports.

Files:

- Modify: `ergon_core/ergon_core/core/api/test_harness.py`.
- Modify: `ergon_core/ergon_core/core/api/app.py`.
- Modify or use existing startup plugin settings in
  `ergon_core/ergon_core/core/settings.py`.
- Test: `tests/unit/architecture/test_smoke_fixture_package_boundary.py`.
- Test: harness tests that currently exercise `ENABLE_TEST_HARNESS`.

Steps:

- [ ] Inventory current `ENABLE_TEST_HARNESS` and `ENABLE_SMOKE_FIXTURES`
      behavior.
- [ ] Define the plugin hook that can register smoke fixtures or experiment
      builders.
- [ ] Move test-harness composition to the plugin path.
- [ ] Preserve disabled-by-default behavior.
- [ ] Add an architecture allowlist for the few remaining test-support imports,
      if any.

Acceptance gate:

- [ ] Test harness smoke behavior still works under explicit opt-in.
- [ ] Core app startup no longer needs to know smoke fixture implementation
      modules by name.
- [ ] Architecture tests fail if new production runtime modules import
      `ergon_core.test_support`.

## Migration / risk

The risk is not algorithmic behavior; it is import-time behavior. The current
registry performs eager optional-capability imports and model backend
registration. Moving this behind protocols must preserve:

- Existing CLI defaults and slug names.
- Optional extras behavior and install hints.
- Model backend registration side effects.
- Test harness smoke fixture behavior under explicit flags.

The first implementation step should be characterization tests around registry
resolution and CLI experiment construction before import paths are changed.

## Open questions

- Should the registry protocol live in `ergon_core.api`, `ergon_core.core`, or
  a new package such as `ergon_runtime_contracts`?
- Should CLI remain the primary composition root, or should FastAPI startup and
  CLI share a new composition module?
- Do existing consumers import `ergon_builtins.registry` directly, and if so do
  those imports need compatibility wrappers?

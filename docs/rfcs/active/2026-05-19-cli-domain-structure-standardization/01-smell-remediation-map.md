# CLI Smell Remediation Map

This document expands the CLI domain RFC into concrete cleanup items. Each item
is written as:

- problem;
- solution;
- proposed code;
- proposed location / domain.

It is intentionally implementation-facing, but not yet a step-by-step plan.
Once the RFC is accepted, this file should become the input to the
implementation plan under `docs/superpowers/plans/`.

## 1. Direct Persistence Access In CLI Commands

### Problem

`ergon_cli` currently reaches into SQLModel sessions and persistence tables for
some observation commands. This makes the CLI a second read-model layer and
couples terminal output to persistence internals.

Current examples:

- `ergon_cli/commands/run.py` imports `ensure_db`, `get_session`,
  `BenchmarkDefinitionRecord`, `RunRecord`, and `select`.
- `ergon_cli/commands/experiment.py` imports `get_session`,
  `BenchmarkDefinitionRecord`, and `select`.

This violates the desired boundary: CLI should translate terminal input into
typed calls, while `ergon_core` owns views/runtime services and persistence
shape.

### Solution

Move read/query behavior into `ergon_core` views services and runtime services.
The CLI domain services should call those services and render typed DTOs.

### Proposed code

Core-side service targets after
[DeepFlow-research/ergon#91](https://github.com/DeepFlow-research/ergon/pull/91):

```text
ergon_core/ergon_core/core/views/runs/service.py
ergon_core/ergon_core/core/views/experiments/service.py
ergon_core/ergon_core/core/application/runtime/run_records.py
```

Possible typed APIs:

```python
class RunListFilter(BaseModel):
    limit: int = 20
    status: str | None = None
    experiment: str | None = None


class RunReadService:
    def list_runs(self, filters: RunListFilter) -> tuple[RunSummaryDto, ...]: ...
    def get_run(self, run_id: UUID) -> RunDetailDto | None: ...
```

```python
class ExperimentReadService:
    def list_tags(self) -> tuple[str, ...]: ...
    def list_definitions_by_tag(self, tag: str) -> tuple[ExperimentDefinitionRowDto, ...]: ...
```

CLI-side domain service:

```python
class RunsCliService:
    def list(self, command: RunListCommand) -> RunListView: ...
    def status(self, command: RunStatusCommand) -> RunStatusView: ...
    def cancel(self, command: RunCancelCommand) -> RunCancelView: ...
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/domains/runs/models.py
ergon_cli/ergon_cli/domains/runs/service.py
ergon_cli/ergon_cli/domains/experiments/models.py
ergon_cli/ergon_cli/domains/experiments/service.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_no_persistence_access.py
```

The guard should fail on direct `get_session`, `session.exec`, `session.get`,
`select(`, or persistence model imports inside `ergon_cli/ergon_cli`.

## 2. `argparse.Namespace` As Domain Data

### Problem

Command handlers accept raw `argparse.Namespace` values and pass them into
logic. That keeps command inputs weakly typed and allows UUID parsing, enum
validation, default handling, and optional fields to happen ad hoc.

This is how bugs like parser/executor naming drift happen. Before the PR #91
base, `workflow.py` had parser/handler drift around parent graph identity. On
the PR #91 base, the CLI uses task identity, so the regression guard should be
for `--parent-task-id` and `args.parent_task_id`.

### Solution

Convert `Namespace` into typed command models immediately inside
`domains/*/commands.py`. Domain services and lower helpers should accept only
typed command objects.

### Proposed code

Example:

```python
class RunStatusCommand(BaseModel):
    run_id: UUID


def handle_status(args: argparse.Namespace, service: RunsCliService) -> int:
    command = RunStatusCommand(run_id=args.run_id)
    view = service.status(command)
    render_key_values(view)
    return ExitCode.OK
```

For workflow:

```python
class WorkflowTaskTreeCommand(BaseModel):
    parent_task_id: UUID | None = None
    wait_seconds: float = 0
    output_format: OutputFormat = OutputFormat.TEXT
```

### Proposed location / domain

Every domain:

```text
ergon_cli/ergon_cli/domains/<domain>/models.py
ergon_cli/ergon_cli/domains/<domain>/commands.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_namespace_boundary.py
```

The guard should allow `argparse.Namespace` only in `parser.py`,
`commands.py`, and tests.

## 3. Mixed Rendering And Behavior

### Problem

Handlers often fetch data, perform mutations, format rows, and print output in
one function. This makes tests rely on captured stdout and makes JSON output or
alternate renderers harder to add later.

### Solution

Domain services return typed view/result models. Shared renderers print those
views. Command modules coordinate service + renderer + exit code.

### Proposed code

Shared output primitives:

```python
class TableView(BaseModel):
    headers: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]


def render_table(view: TableView) -> None: ...
def render_key_values(view: KeyValueView) -> None: ...
def render_json(value: BaseModel | Mapping[str, object]) -> None: ...
```

Domain view example:

```python
class RunStatusView(BaseModel):
    run_id: UUID
    status: str
    benchmark_type: str
    workflow_definition_id: UUID
    instance_key: str
    evaluator_slug: str | None = None
    model_target: str | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str | None = None
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/shared/output.py
ergon_cli/ergon_cli/domains/*/models.py
ergon_cli/ergon_cli/domains/*/service.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_rendering_boundary.py
```

The guard should allow `print(` only in `shared/output.py`, prompt modules,
and explicitly local streaming code such as E2B build log callbacks.

## 4. Static Duplicated Catalogues

### Problem

The CLI has static catalogue data in `ergon_cli/discovery/__init__.py` for
benchmarks, workers, and evaluators. Onboarding separately carries benchmark
requirements. Builtins also declare benchmark metadata on benchmark classes.

These sources can drift.

### Solution

Prefer one typed source of truth. For benchmarks, consume metadata from
`Benchmark` subclasses: `type_slug`, name/description metadata, and
`onboarding_deps` / `BenchmarkRequirements`. For workers and evaluators, either
define an explicit builtins metadata API or move the static listing into
`ergon_builtins` so the CLI is only a renderer.

### Proposed code

Builtins catalogue API:

```python
class BenchmarkCatalogueEntry(BaseModel):
    slug: str
    name: str
    description: str
    requirements: BenchmarkRequirements


def list_builtin_benchmarks() -> tuple[BenchmarkCatalogueEntry, ...]: ...
```

CLI service:

```python
class BenchmarkCliService:
    def list(self) -> BenchmarkListView:
        entries = list_builtin_benchmarks()
        return BenchmarkListView.from_entries(entries)
```

### Proposed location / domain

Core/builtins source:

```text
ergon_builtins/ergon_builtins/benchmarks/catalogue.py
```

CLI consumer:

```text
ergon_cli/ergon_cli/domains/benchmarks/service.py
ergon_cli/ergon_cli/domains/benchmarks/models.py
```

Onboarding consumer:

```text
ergon_cli/ergon_cli/domains/onboarding/profile.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_no_static_builtin_catalogue.py
```

## 5. `main.py` As A Central Knowledge Dump

### Problem

`main.py` currently defines parser flags for every command and owns dispatch
maps. This turns it into a command registry, parser catalogue, and entrypoint
all at once.

### Solution

Make `main.py` and optional `app.py` composition roots. Each domain registers
its own parser and handler.

### Proposed code

```python
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(...)
    subparsers = parser.add_subparsers(dest="command")
    for registrar in DOMAIN_REGISTRARS:
        registrar(subparsers)
    return parser
```

```python
DOMAIN_REGISTRARS = (
    register_benchmark_parser,
    register_doctor_parser,
    register_eval_parser,
    register_experiment_parser,
    register_ingestion_parser,
    register_onboarding_parser,
    register_run_parser,
    register_stack_parser,
    register_training_parser,
    register_workflow_parser,
)
```

Each parser should set a callable on the parsed namespace:

```python
parser.set_defaults(handler=handle_run_status)
```

Then dispatch becomes:

```python
handler = getattr(args, "handler", None)
if handler is None:
    parser.print_help()
    return ExitCode.OK
return await maybe_await(handler(args))
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/main.py
ergon_cli/ergon_cli/app.py
ergon_cli/ergon_cli/domains/*/parser.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_main_is_composition_root.py
```

The guard should fail on domain-specific `add_argument` calls in `main.py`.

## 6. Thin Bootstrap No-Ops And Legacy Names

### Problem

`ergon_cli/bootstrap.py` contains a no-op
`register_and_publish_builtins()`, and `main.py` conditionally calls it. The
name implies registry publishing still exists, even though object-bound
definitions no longer require it.

This is compatibility-shaped code without behavior.

### Solution

Delete the no-op if no command needs it. If some command does need preparation,
replace it with an explicit command preparation hook whose name describes the
current behavior.

### Proposed code

Preferred deletion:

```text
delete ergon_cli/ergon_cli/bootstrap.py
remove calls from main.py
```

If preparation is needed:

```python
class CliRuntimePreparation(BaseModel):
    needs_builtin_catalogue: bool = False
    needs_database: bool = False


def prepare_runtime(preparation: CliRuntimePreparation) -> None: ...
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/app.py
ergon_cli/ergon_cli/shared/runtime.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_no_dead_bootstrap.py
```

## 7. Inconsistent Sync / Async Boundaries

### Problem

The CLI entrypoint runs through `asyncio.run`, but some lower-level helpers
also call `asyncio.run` internally. The workflow command currently bridges
async manage actions from sync dispatch code. This can break if reused inside
an existing event loop and obscures which command paths are async.

### Solution

Make async boundaries explicit at the command dispatch layer. Domain handlers
may be sync or async, but lower-level domain executors should not call
`asyncio.run`.

### Proposed code

Shared dispatch helper:

```python
async def invoke_handler(handler: CliHandler, args: argparse.Namespace) -> int:
    result = handler(args)
    if inspect.isawaitable(result):
        return await result
    return result
```

Workflow executor:

```python
async def execute_workflow_command(
    command: str,
    *,
    context: WorkflowCliContext,
    session_factory: Callable[[], Session],
    service: WorkflowService,
) -> WorkflowCommandOutput:
    ...
    return await dispatch_workflow_command(...)
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/app.py
ergon_cli/ergon_cli/domains/workflow/executor.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_no_nested_asyncio_run.py
```

Allow `asyncio.run` only in `main.py`.

## 8. Workflow Parser / Executor Naming Drift

### Problem

The workflow parser and handler have already shown naming drift around parent
graph identity:

- older parser code defined `--parent-node-id`;
- handler code read `args.parent_task_id`;
- PR #91 standardizes the human CLI surface on `--parent-task-id`.

This is exactly the kind of bug typed command models prevent.

### Solution

Split workflow into:

- top-level injected context model;
- nested parser;
- nested command models;
- async executor.

Every parser action should map to a typed command object before execution.

### Proposed code

```python
class WorkflowCliContext(BaseModel):
    run_id: UUID
    node_id: UUID
    execution_id: UUID
    sandbox_task_key: UUID
    benchmark_type: str
```

```python
class WorkflowInspectTaskTreeCommand(BaseModel):
    parent_task_id: UUID | None = None
    wait_seconds: float = 0
    output_format: OutputFormat = OutputFormat.TEXT
```

```python
async def inspect_task_tree(
    command: WorkflowInspectTaskTreeCommand,
    *,
    context: WorkflowCliContext,
    session: Session,
    service: WorkflowService,
) -> WorkflowCommandOutput: ...
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/domains/workflow/context.py
ergon_cli/ergon_cli/domains/workflow/models.py
ergon_cli/ergon_cli/domains/workflow/parser.py
ergon_cli/ergon_cli/domains/workflow/executor.py
```

Tests:

```text
ergon_cli/tests/unit/domains/workflow/test_parser_models.py
ergon_cli/tests/unit/domains/workflow/test_executor.py
```

## 9. Optional Dependency Handling Inline In Commands

### Problem

`train.py` probes for `ergon_infra` and then imports training modules inside
the handler. The delayed import is justified because `ergon_infra` is optional,
but this pattern will become scattered if more optional domains appear.

### Solution

Centralize optional dependency checks in a shared helper that produces typed
CLI errors. Keep the actual optional imports at the domain service boundary.

### Proposed code

```python
class MissingOptionalDependency(CliError):
    package: str
    install_hint: str
```

```python
def require_module(module_name: str, *, install_hint: str) -> None:
    if importlib.util.find_spec(module_name) is None:
        raise MissingOptionalDependency(
            package=module_name,
            install_hint=install_hint,
        )
```

Training service:

```python
class TrainingCliService:
    def train_local(self, command: TrainLocalCommand) -> TrainLocalResult:
        require_module("ergon_infra", install_hint="pip install ergon-cli[training]")
        from ergon_infra.training.config import TrainingConfig
        from ergon_infra.training.trl_runner import run_trl_training
        ...
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/shared/dependencies.py
ergon_cli/ergon_cli/shared/errors.py
ergon_cli/ergon_cli/domains/training/service.py
```

## 10. Local Machine Effects Are Not Modeled

### Problem

`stack`, `doctor`, `onboard`, and `benchmark setup` perform real local effects:

- subprocess execution;
- `.env` writes;
- E2B template builds;
- Docker daemon checks;
- TCP health checks;
- optional package installation.

Today much of that code prints as it goes and returns bare exit codes.

### Solution

Represent local effects and their outcomes as typed result models. Streaming
output is still allowed for long-running operations such as E2B builds, but
the command should also return a structured final result.

### Proposed code

```python
class StackStartResult(BaseModel):
    compose_file: Path
    services: tuple[ServiceEndpoint, ...]
    exit_code: int
```

```python
class DoctorReport(BaseModel):
    checks: tuple[DoctorCheckResult, ...]

    @property
    def ok(self) -> bool:
        return all(check.status == CheckStatus.PASS for check in self.checks)
```

```python
class BenchmarkTemplateSetupResult(BaseModel):
    slug: str
    template_name: str
    template_id: str
    build_id: str
    built_at: datetime
    registry_path: Path
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/domains/stack/models.py
ergon_cli/ergon_cli/domains/doctor/models.py
ergon_cli/ergon_cli/domains/benchmarks/models.py
ergon_cli/ergon_cli/domains/onboarding/models.py
```

## 11. Ad Hoc Error Handling And Exit Codes

### Problem

Commands mix several error strategies:

- print usage and return `1`;
- raise `SystemExit`;
- print to stderr and return a code;
- log an error;
- catch broad exceptions in domain code.

This makes behavior inconsistent and makes command tests focus on incidental
output rather than expected failure modes.

### Solution

Use shared CLI error and exit-code models. Command modules catch known
`CliError` subclasses and render them uniformly.

### Proposed code

```python
class ExitCode(IntEnum):
    OK = 0
    ERROR = 1
    USAGE = 2
    DEPENDENCY = 3
```

```python
class CliError(Exception):
    exit_code: ExitCode = ExitCode.ERROR


class UsageError(CliError):
    exit_code = ExitCode.USAGE


class DependencyMissingError(CliError):
    exit_code = ExitCode.DEPENDENCY
```

```python
def render_error(error: CliError) -> None: ...
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/shared/errors.py
ergon_cli/ergon_cli/shared/exit_codes.py
ergon_cli/ergon_cli/shared/output.py
ergon_cli/ergon_cli/app.py
```

## 12. Logging Versus Printing Is Inconsistent

### Problem

Some commands use `print`, others use logging for user-facing CLI output.
For a CLI, direct terminal output is fine, but it should be centralized and
deliberate.

### Solution

Use logging for diagnostics and debug logs. Use shared renderers for
user-facing command output.

### Proposed code

```python
def render_view(view: CliView, *, format: OutputFormat = OutputFormat.TEXT) -> None:
    ...
```

Command modules:

```python
view = service.status(command)
render_view(view, format=command.output_format)
return ExitCode.OK
```

### Proposed location / domain

```text
ergon_cli/ergon_cli/shared/output.py
ergon_cli/ergon_cli/shared/logging.py
```

Architecture guard may be combined with the rendering-boundary guard.

## 13. Command Vocabulary Lags Current Architecture

### Problem

The CLI still has some vocabulary that feels inherited from older shapes:

- `experiment` exists as a command group, while authoring is Python-only;
- `worker list` and `evaluator list` are static views;
- `benchmark setup` only covers a subset of template-bearing benchmarks;
- no clear naming distinction exists between observe/setup/admin surfaces and
  authoring surfaces.

This does not mean the command names are wrong, but it should be explicit that
they are observation/setup/admin commands, not authoring commands.

### Solution

Document CLI command intent by domain:

- observe: `run`, `experiment`, workflow inspect commands;
- setup: `onboard`, `doctor`, `benchmark setup`, `start`, `stop`;
- runtime/admin: `run cancel`;
- agent toolkit only: workflow manage commands, owned by `ergon_builtins`;
- delegated tools: `ingest`, `eval`, `train`.

Do not introduce CLI authoring aliases.

### Proposed code

Domain metadata:

```python
class CliDomainMetadata(BaseModel):
    name: str
    kind: Literal["observe", "setup", "admin", "delegated"]
    authoring_surface: bool = False
```

Parser registration can expose this metadata for architecture tests and
potential help grouping later.

### Proposed location / domain

```text
ergon_cli/ergon_cli/domains/<domain>/metadata.py
ergon_cli/ergon_cli/app.py
```

Architecture guard:

```text
ergon_cli/tests/unit/architecture/test_no_cli_authoring_surface.py
```

## 14. CLI Tests Lack Architecture Guardrails

### Problem

The CLI has useful unit tests, but it lacks the density of architectural
guardrails present in `ergon_core`. Without tests, cleanup rules can regress
silently.

### Solution

Add CLI architecture tests as part of the refactor, not after.

### Proposed code

Test files:

```text
ergon_cli/tests/unit/architecture/test_domain_layout.py
ergon_cli/tests/unit/architecture/test_main_is_composition_root.py
ergon_cli/tests/unit/architecture/test_namespace_boundary.py
ergon_cli/tests/unit/architecture/test_no_persistence_access.py
ergon_cli/tests/unit/architecture/test_no_nested_asyncio_run.py
ergon_cli/tests/unit/architecture/test_no_cli_authoring_surface.py
ergon_cli/tests/unit/architecture/test_rendering_boundary.py
```

Suggested assertions:

- `main.py` has no domain-specific `add_argument` calls.
- `argparse.Namespace` appears only in parser/command boundary modules.
- `ergon_cli` does not import persistence models or session helpers.
- `asyncio.run` appears only in `main.py`.
- user-facing `print` appears only in shared renderers, prompts, and explicit
  streaming exceptions.
- no deleted authoring commands return.
- every domain has `parser.py` and `commands.py`.

### Proposed location / domain

```text
ergon_cli/tests/unit/architecture/
```

## Priority Order

Recommended implementation order:

1. Split parser registration out of `main.py`.
2. Add typed command/result models.
3. Centralize output, errors, and exit codes.
4. Move direct DB access into core views/runtime services.
5. Clean workflow parser/executor typing.
6. Delete no-op bootstrap compatibility code.
7. Consolidate benchmark/onboarding/discovery catalogues.
8. Add architecture tests as each rule becomes true.

This order gives quick improvements to code shape while delaying the most
behavior-sensitive work, namely replacing direct CLI queries with core
views/runtime services.

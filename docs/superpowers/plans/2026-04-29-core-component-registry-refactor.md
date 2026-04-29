# Core Component Registry Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move component registration ownership into `ergon_core` public API so core never imports `ergon_builtins`, builtins/tests explicitly register components, and experiment definition/runtime have a clear slug-to-component mental model.

**Architecture:** Add a Pydantic-based `ComponentRegistry` and process-global `registry` under `ergon_core.api.registry`. Builtins, optional builtins capabilities, and tests contribute components through explicit registration functions. Core application/runtime code resolves persisted slugs through the core registry only.

**Tech Stack:** Python, Pydantic models, pytest, Inngest job handlers, FastAPI startup, existing Ergon public APIs.

---

## Mental Model To Preserve

The final model should be easy to explain to students:

1. Components are Python classes/functions: `Benchmark`, `Worker`, `Evaluator`/`Rubric`, `BaseSandboxManager`.
2. Registration says which component slugs are available in this process.
3. Experiment authoring passes concrete objects/specs into `Experiment`.
4. Persistence stores only stable identities: benchmark slug, worker slug, evaluator slug, sandbox slug, model target.
5. Runtime jobs turn those stored slugs back into Python classes/functions via `ergon_core.api.registry.registry`.

The registry is not the main experiment authoring API. It is the catalog that validates slugs and rehydrates persisted definitions across process boundaries.

## File Structure

- Create `ergon_core/ergon_core/api/registry.py`
  - Defines `WorkerFactory`, `ComponentRegistry`, `registry`, duplicate handling, `require_*` lookup helpers, and reset/snapshot helpers for tests.
- Modify `ergon_core/ergon_core/api/__init__.py`
  - Re-export `ComponentRegistry`, `WorkerFactory`, and `registry`.
- Modify `ergon_builtins/ergon_builtins/registry_core.py`
  - Replace exported dict ownership with `register_core_builtins(target=registry)`.
- Modify `ergon_builtins/ergon_builtins/registry_data.py`
  - Replace exported dict ownership with `register_data_builtins(target=registry)`.
- Modify `ergon_builtins/ergon_builtins/registry_local_models.py`
  - Replace exported dict ownership with `register_local_model_builtins(target=registry)` or a returned model backend mapping, depending on model backend constraints.
- Modify `ergon_builtins/ergon_builtins/registry.py`
  - Becomes explicit composition function `register_builtins(target=registry)`.
  - Optional: keep backwards-compatible module attributes temporarily only if necessary for existing tests, but core must not use them.
- Modify core runtime imports in:
  - `ergon_core/ergon_core/core/application/jobs/worker_execute.py`
  - `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`
  - `ergon_core/ergon_core/core/application/jobs/persist_outputs.py`
  - `ergon_core/ergon_core/core/application/jobs/sandbox_setup.py`
  - `ergon_core/ergon_core/core/application/experiments/launch.py`
  - `ergon_core/ergon_core/core/application/experiments/service.py`
  - `ergon_core/ergon_core/core/application/workflows/service.py`
  - `ergon_core/ergon_core/core/application/tasks/management.py`
  - `ergon_core/ergon_core/core/domain/experiments/worker_spec.py`
  - `ergon_core/ergon_core/core/rest_api/app.py`
- Move test-only smoke fixture component definitions from:
  - `ergon_core/ergon_core/test_support/smoke_fixtures/**`
  - into `tests/e2e/fixtures/smoke_components/**` or `tests/fixtures/smoke_components/**`.
- Modify E2E/test startup:
  - `tests/e2e/conftest.py`
  - current startup plugin module(s) referenced by `ERGON_STARTUP_PLUGINS`
  - tests currently importing `ergon_core.test_support.smoke_fixtures`
- Modify unit tests:
  - `tests/unit/registry/test_builtin_pairings.py`
  - add `tests/unit/registry/test_component_registry.py`
  - add/adjust core tests that assert no `ergon_core` file imports `ergon_builtins.registry`.

---

### Task 1: Add Core Public Component Registry

**Files:**
- Create: `ergon_core/ergon_core/api/registry.py`
- Modify: `ergon_core/ergon_core/api/__init__.py`
- Test: `tests/unit/registry/test_component_registry.py`

- [ ] **Step 1: Write failing registry unit tests**

Create `tests/unit/registry/test_component_registry.py`:

```python
import pytest

from ergon_core.api import Benchmark, Rubric, Worker
from ergon_core.api.registry import ComponentRegistry
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager


class ExampleWorker(Worker):
    type_slug = "example-worker"


class ReplacementWorker(Worker):
    type_slug = "example-worker"


class ExampleBenchmark(Benchmark):
    type_slug = "example-benchmark"


class ExampleRubric(Rubric):
    type_slug = "example-rubric"


class ExampleSandboxManager(BaseSandboxManager):
    pass


def test_registers_components_by_explicit_or_type_slug() -> None:
    registry = ComponentRegistry()

    registry.register_worker(ExampleWorker.type_slug, ExampleWorker)
    registry.register_benchmark(ExampleBenchmark)
    registry.register_evaluator(ExampleRubric)
    registry.register_sandbox_manager("example-benchmark", ExampleSandboxManager)

    assert registry.require_worker("example-worker") is ExampleWorker
    assert registry.require_benchmark("example-benchmark") is ExampleBenchmark
    assert registry.require_evaluator("example-rubric") is ExampleRubric
    assert registry.sandbox_managers["example-benchmark"] is ExampleSandboxManager


def test_duplicate_slug_rejects_different_object() -> None:
    registry = ComponentRegistry()
    registry.register_worker("example-worker", ExampleWorker)

    with pytest.raises(ValueError, match="Duplicate worker slug 'example-worker'"):
        registry.register_worker("example-worker", ReplacementWorker)


def test_duplicate_slug_allows_idempotent_registration() -> None:
    registry = ComponentRegistry()
    registry.register_worker("example-worker", ExampleWorker)
    registry.register_worker("example-worker", ExampleWorker)

    assert registry.require_worker("example-worker") is ExampleWorker


def test_unknown_slug_error_lists_registered_values() -> None:
    registry = ComponentRegistry()
    registry.register_worker("example-worker", ExampleWorker)

    with pytest.raises(
        ValueError,
        match="Unknown worker slug 'missing-worker'; registered workers: example-worker",
    ):
        registry.require_worker("missing-worker")
```

- [ ] **Step 2: Run failing registry tests**

Run:

```bash
pytest tests/unit/registry/test_component_registry.py -q
```

Expected: FAIL because `ergon_core.api.registry` does not exist.

- [ ] **Step 3: Implement `ergon_core.api.registry`**

Create `ergon_core/ergon_core/api/registry.py`:

```python
"""Public process-level component registry.

The registry maps stable slugs stored in experiment definitions back to the
Python classes/factories needed by runtime jobs. Packages such as
``ergon_builtins`` and test fixtures contribute components explicitly during
startup; ``ergon_core`` never imports those packages to discover components.
"""

from collections.abc import Callable, Mapping
from typing import TypeVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.rubric import Evaluator
from ergon_core.api.worker import Worker
from ergon_core.core.infrastructure.sandbox.manager import BaseSandboxManager
from pydantic import BaseModel, ConfigDict, Field

WorkerFactory = Callable[..., Worker]
T = TypeVar("T")


class ComponentRegistry(BaseModel):
    """Catalog of component types available in the current Python process."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    workers: dict[str, WorkerFactory] = Field(default_factory=dict)
    benchmarks: dict[str, type[Benchmark]] = Field(default_factory=dict)
    evaluators: dict[str, type[Evaluator]] = Field(default_factory=dict)
    sandbox_managers: dict[str, type[BaseSandboxManager]] = Field(default_factory=dict)

    def register_worker(self, slug: str, factory: WorkerFactory) -> None:
        self._register(self.workers, "worker", slug, factory)

    def register_benchmark(self, benchmark_cls: type[Benchmark], slug: str | None = None) -> None:
        self._register(self.benchmarks, "benchmark", slug or benchmark_cls.type_slug, benchmark_cls)

    def register_evaluator(self, evaluator_cls: type[Evaluator], slug: str | None = None) -> None:
        self._register(self.evaluators, "evaluator", slug or evaluator_cls.type_slug, evaluator_cls)

    def register_sandbox_manager(
        self,
        slug: str,
        manager_cls: type[BaseSandboxManager],
    ) -> None:
        self._register(self.sandbox_managers, "sandbox manager", slug, manager_cls)

    def require_worker(self, slug: str) -> WorkerFactory:
        return self._require(self.workers, "worker", slug)

    def require_benchmark(self, slug: str) -> type[Benchmark]:
        return self._require(self.benchmarks, "benchmark", slug)

    def require_evaluator(self, slug: str) -> type[Evaluator]:
        return self._require(self.evaluators, "evaluator", slug)

    def _register(self, target: dict[str, T], kind: str, slug: str, value: T) -> None:
        existing = target.get(slug)
        if existing is not None and existing is not value:
            raise ValueError(f"Duplicate {kind} slug {slug!r}")
        target[slug] = value

    def _require(self, target: Mapping[str, T], kind: str, slug: str) -> T:
        try:
            return target[slug]
        except KeyError:
            known = ", ".join(sorted(target)) or "<none>"
            raise ValueError(
                f"Unknown {kind} slug {slug!r}; registered {kind}s: {known}"
            ) from None


registry = ComponentRegistry()
```

- [ ] **Step 4: Re-export the registry from public API**

Modify `ergon_core/ergon_core/api/__init__.py`:

```python
"""Beginner-facing Ergon authoring API surface."""

from ergon_core.api.benchmark import Benchmark, BenchmarkRequirements, EmptyTaskPayload, Task
from ergon_core.api.criterion import (
    Criterion,
    CriterionContext,
    CriterionEvidence,
    CriterionOutcome,
    EvidenceMessage,
    ScoreScale,
)
from ergon_core.api.errors import CriterionCheckError
from ergon_core.api.registry import ComponentRegistry, WorkerFactory, registry
from ergon_core.api.rubric import Rubric, TaskEvaluationResult
from ergon_core.api.worker import Worker, WorkerContext, WorkerOutput, WorkerStreamItem

__all__ = [
    "Benchmark",
    "BenchmarkRequirements",
    "ComponentRegistry",
    "Criterion",
    "CriterionCheckError",
    "CriterionContext",
    "CriterionEvidence",
    "CriterionOutcome",
    "EmptyTaskPayload",
    "EvidenceMessage",
    "Rubric",
    "ScoreScale",
    "Task",
    "TaskEvaluationResult",
    "Worker",
    "WorkerContext",
    "WorkerFactory",
    "WorkerOutput",
    "WorkerStreamItem",
    "registry",
]
```

- [ ] **Step 5: Run registry tests**

Run:

```bash
pytest tests/unit/registry/test_component_registry.py -q
```

Expected: PASS.

---

### Task 2: Convert Builtins Registry To Explicit Registration

**Files:**
- Modify: `ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon_builtins/ergon_builtins/registry_data.py`
- Modify: `ergon_builtins/ergon_builtins/registry_local_models.py`
- Modify: `ergon_builtins/ergon_builtins/registry.py`
- Test: `tests/unit/registry/test_builtin_pairings.py`

- [ ] **Step 1: Update builtin pairing tests to register into a fresh registry**

Modify `tests/unit/registry/test_builtin_pairings.py` so tests no longer import dicts from `ergon_builtins.registry_core` or `ergon_builtins.registry`. Use a fresh `ComponentRegistry`:

```python
"""Documented built-in benchmark pairings are explicit and registered."""

import pytest

from ergon_core.api.registry import ComponentRegistry


CORE_PAIRINGS = [
    {
        "benchmark": "minif2f",
        "worker": "minif2f-react",
        "evaluator": "minif2f-rubric",
        "sandbox": "minif2f",
        "extras": ("none",),
    },
    {
        "benchmark": "swebench-verified",
        "worker": "swebench-react",
        "evaluator": "swebench-rubric",
        "sandbox": "swebench-verified",
        "extras": ("ergon-builtins[data]",),
    },
]

DATA_PAIRINGS = [
    {
        "benchmark": "gdpeval",
        "worker": "gdpeval-react",
        "evaluator": "gdpeval-staged-rubric",
        "sandbox": "gdpeval",
        "extras": ("ergon-builtins[data]",),
    },
    {
        "benchmark": "researchrubrics",
        "worker": "researchrubrics-researcher",
        "evaluator": "researchrubrics-rubric",
        "sandbox": "researchrubrics",
        "extras": ("ergon-builtins[data]",),
    },
    {
        "benchmark": "researchrubrics-vanilla",
        "worker": "researchrubrics-researcher",
        "evaluator": "researchrubrics-rubric",
        "sandbox": "researchrubrics-vanilla",
        "extras": ("ergon-builtins[data]",),
    },
]


@pytest.mark.parametrize("pairing", CORE_PAIRINGS)
def test_core_pairings_reference_registered_slugs(pairing: dict[str, object]) -> None:
    from ergon_builtins.registry_core import register_core_builtins

    registry = ComponentRegistry()
    register_core_builtins(registry)

    _assert_pairing(pairing, registry)


@pytest.mark.parametrize("pairing", DATA_PAIRINGS)
def test_data_pairings_reference_registered_slugs(pairing: dict[str, object]) -> None:
    pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
    from ergon_builtins.registry import register_builtins

    registry = ComponentRegistry()
    register_builtins(registry)

    _assert_pairing(pairing, registry)


def _assert_pairing(pairing: dict[str, object], registry: ComponentRegistry) -> None:
    benchmark = pairing["benchmark"]
    worker = pairing["worker"]
    evaluator = pairing["evaluator"]
    sandbox = pairing["sandbox"]
    extras = pairing["extras"]

    assert benchmark in registry.benchmarks
    assert worker in registry.workers
    assert evaluator in registry.evaluators
    assert sandbox in registry.sandbox_managers
    assert isinstance(extras, tuple)
    assert extras
```

- [ ] **Step 2: Run updated builtin pairing tests**

Run:

```bash
pytest tests/unit/registry/test_builtin_pairings.py -q
```

Expected: FAIL because the `register_*` functions do not exist.

- [ ] **Step 3: Replace `registry_core.py` dicts with `register_core_builtins`**

Modify `ergon_builtins/ergon_builtins/registry_core.py` to keep imports but replace exported dicts with:

```python
from ergon_core.api.registry import ComponentRegistry, registry


def register_core_builtins(target: ComponentRegistry = registry) -> None:
    """Register builtins that have no optional dependency extras."""

    target.register_worker("training-stub", TrainingStubWorker)
    target.register_worker("minif2f-react", minif2f_react)
    target.register_worker("swebench-react", swebench_react)

    target.register_benchmark(MiniF2FBenchmark)
    target.register_benchmark(SweBenchVerifiedBenchmark)

    target.register_evaluator(StagedRubric)
    target.register_evaluator(StagedRubric, slug="gdpeval-staged-rubric")
    target.register_evaluator(MiniF2FRubric)
    target.register_evaluator(SWEBenchRubric)

    target.register_sandbox_manager("gdpeval", GDPEvalSandboxManager)
    target.register_sandbox_manager("minif2f", MiniF2FSandboxManager)
    target.register_sandbox_manager("swebench-verified", SWEBenchSandboxManager)
```

Do not remove `SANDBOX_TEMPLATES` yet unless all uses are known. Leave it as a plain exported mapping:

```python
SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": Path(__file__).parent / "benchmarks/minif2f/sandbox",
    "swebench-verified": Path(__file__).parent / "benchmarks/swebench_verified/sandbox",
}
```

- [ ] **Step 4: Replace `registry_data.py` dicts with `register_data_builtins`**

Modify `ergon_builtins/ergon_builtins/registry_data.py`:

```python
from ergon_core.api.registry import ComponentRegistry, registry


def register_data_builtins(target: ComponentRegistry = registry) -> None:
    """Register builtins that require the [data] optional dependency group."""

    target.register_benchmark(GDPEvalBenchmark)
    target.register_benchmark(ResearchRubricsBenchmark)
    target.register_benchmark(ResearchRubricsVanillaBenchmark)

    target.register_evaluator(ResearchRubricsRubric, slug="research-rubric")
    target.register_evaluator(ResearchRubricsRubric)

    target.register_worker("gdpeval-react", gdpeval_react)
    target.register_worker(ResearchRubricsResearcherWorker.type_slug, ResearchRubricsResearcherWorker)
    target.register_worker(
        ResearchRubricsWorkflowCliReActWorker.type_slug,
        ResearchRubricsWorkflowCliReActWorker,
    )

    target.register_sandbox_manager("researchrubrics", ResearchRubricsSandboxManager)
    target.register_sandbox_manager("researchrubrics-vanilla", ResearchRubricsSandboxManager)
```

If `GDPEvalBenchmark` requires a sandbox manager but the current data registry does not register one, decide during implementation whether to add:

```python
target.register_sandbox_manager("gdpeval", GDPEvalSandboxManager)
```

only if `GDPEvalSandboxManager` can be imported from the data module without creating an optional dependency problem. Otherwise keep the current core registration for `"gdpeval"`.

- [ ] **Step 5: Convert top-level `ergon_builtins.registry` to an explicit registration function**

Modify `ergon_builtins/ergon_builtins/registry.py`:

```python
"""Register built-in Ergon components into the core public registry."""

import structlog

from ergon_core.api.registry import ComponentRegistry, registry
from ergon_builtins.models.resolution import register_model_backend
from ergon_builtins.registry_core import register_core_builtins

log = structlog.get_logger()


def register_builtins(target: ComponentRegistry = registry) -> None:
    """Register builtins available in the current environment.

    This is intentionally explicit: importing ``ergon_core`` does not import
    builtins, and importing builtins does not mutate core unless startup calls
    this function.
    """

    register_core_builtins(target)
    _register_local_model_builtins()
    _register_data_builtins(target)


def _register_local_model_builtins() -> None:
    try:
        from ergon_builtins.registry_local_models import register_local_model_builtins
    except ImportError:
        log.info("ergon-builtins[local-models] not installed; local transformers inference unavailable")
        return

    register_local_model_builtins()


def _register_data_builtins(target: ComponentRegistry) -> None:
    try:
        from ergon_builtins.registry_data import register_data_builtins
    except ImportError:
        log.info(
            "ergon-builtins[data] not installed; gdpeval and researchrubrics benchmarks unavailable"
        )
        return

    register_data_builtins(target)


INSTALL_HINTS: dict[str, str] = {
    "transformers": "pip install 'ergon-builtins[local-models]'",
    "gdpeval": "pip install 'ergon-builtins[data]'",
    "researchrubrics": "pip install 'ergon-builtins[data]'",
    "research-rubric": "pip install 'ergon-builtins[data]'",
}
```

- [ ] **Step 6: Convert local model registry**

Modify `ergon_builtins/ergon_builtins/registry_local_models.py`:

```python
"""Components that require the [local-models] capability."""

from ergon_builtins.models.resolution import register_model_backend
from ergon_builtins.models.transformers_backend import resolve_transformers


def register_local_model_builtins() -> None:
    register_model_backend("transformers", resolve_transformers)
```

Keep core model backends registered wherever they are currently registered. If `registry_core.py` currently owns `"vllm"`, `"openai"`, `"anthropic"`, `"google"`, `"openrouter"`, and `"openai-responses"`, move that into a helper in `ergon_builtins.registry_core` called by `register_core_builtins()`:

```python
def _register_core_model_backends() -> None:
    register_model_backend("vllm", resolve_vllm)
    register_model_backend("openai", resolve_cloud)
    register_model_backend("anthropic", resolve_cloud)
    register_model_backend("google", resolve_cloud)
    register_model_backend("openrouter", resolve_openrouter)
    register_model_backend("openai-responses", resolve_openrouter_responses)
```

- [ ] **Step 7: Run builtin registry tests**

Run:

```bash
pytest tests/unit/registry/test_builtin_pairings.py tests/unit/registry/test_component_registry.py -q
```

Expected: PASS.

---

### Task 3: Add Startup Registration For Runtime Processes

**Files:**
- Modify: runtime startup location that is imported by CLI/API before defining/running experiments.
- Likely modify: `ergon_core/ergon_core/core/rest_api/app.py`
- Search and modify: CLI entrypoints under `ergon_cli/**`
- Test: existing CLI/API tests that define experiments.

- [ ] **Step 1: Locate CLI and startup entrypoints**

Run:

```bash
rg "experiment define|ERGON_STARTUP_PLUGINS|startup_plugins|register_builtins|def main|typer|click" ergon_cli ergon_core tests -n
```

Expected: identify the CLI initialization path and FastAPI lifespan path.

- [ ] **Step 2: Add explicit builtin registration during API startup**

In `ergon_core/ergon_core/core/rest_api/app.py`, import only the core registry at module or function scope. In the lifespan before sandbox event sink wiring, call builtins registration as a startup plugin decision:

```python
from ergon_core.api.registry import registry


def _register_default_components() -> None:
    from ergon_builtins.registry import register_builtins

    register_builtins(registry)
```

Then call `_register_default_components()` early in `lifespan`, before runtime services need sandbox managers.

Important: this is acceptable at app startup because the application chooses to install builtins. Core library modules still must not import `ergon_builtins.registry`.

- [ ] **Step 3: Update sandbox event sink wiring to use core registry**

Replace:

```python
from ergon_builtins.registry import SANDBOX_MANAGERS
...
for manager_cls in SANDBOX_MANAGERS.values():
    manager_cls.set_event_sink(sink)
logger.info("sandbox event sink wired on %d manager subclass(es)", 1 + len(SANDBOX_MANAGERS))
```

with:

```python
from ergon_core.api.registry import registry
...
for manager_cls in registry.sandbox_managers.values():
    manager_cls.set_event_sink(sink)
logger.info(
    "sandbox event sink wired on %d manager subclass(es)",
    1 + len(registry.sandbox_managers),
)
```

- [ ] **Step 4: Add explicit builtin registration during CLI startup**

In the CLI root entrypoint, add a small registration helper and call it before commands that define or run experiments:

```python
from ergon_core.api.registry import registry


def register_default_components() -> None:
    from ergon_builtins.registry import register_builtins

    register_builtins(registry)
```

Do not scatter this call through individual commands if there is a central CLI startup hook. If no central hook exists, call it at the top of experiment define/run command handlers and note the duplication for later cleanup.

- [ ] **Step 5: Run fast CLI/API tests affected by startup**

Run the narrowest available tests after locating them:

```bash
pytest tests/unit tests/integration -q -k "experiment or registry or cli"
```

Expected: PASS or unrelated pre-existing failures documented before continuing.

---

### Task 4: Replace Core Imports Of Builtins Registry

**Files:**
- Modify listed core files containing `from ergon_builtins.registry import ...`
- Test: add import-boundary test under `tests/unit/registry/test_core_registry_boundary.py`

- [ ] **Step 1: Add boundary test that core does not import builtins registry**

Create `tests/unit/registry/test_core_registry_boundary.py`:

```python
from pathlib import Path


def test_ergon_core_does_not_import_builtins_registry() -> None:
    root = Path("ergon_core/ergon_core")
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        text = path.read_text()
        if "ergon_builtins.registry" in text:
            offenders.append(str(path))

    assert offenders == []
```

- [ ] **Step 2: Run boundary test and verify it fails**

Run:

```bash
pytest tests/unit/registry/test_core_registry_boundary.py -q
```

Expected: FAIL listing the current core files that import `ergon_builtins.registry`.

- [ ] **Step 3: Update worker execution lookup**

Modify `ergon_core/ergon_core/core/application/jobs/worker_execute.py`:

```python
from ergon_core.api.registry import registry
```

Inside `run_worker_execute_job`, remove:

```python
from ergon_builtins.registry import BENCHMARKS, WORKERS
```

Replace worker lookup:

```python
worker_cls = registry.workers.get(payload.worker_type)
```

Replace benchmark lookup:

```python
benchmark_cls = registry.benchmarks.get(payload.benchmark_type)
```

Keep existing `RegistryLookupError` behavior for workers by checking `None` as today.

- [ ] **Step 4: Update evaluation job lookup**

Modify `ergon_core/ergon_core/core/application/jobs/evaluate_task_run.py`:

```python
from ergon_core.api.registry import registry
```

Remove the builtins import inside `run_evaluate_task_run_job`. Replace:

```python
evaluator_cls = EVALUATORS.get(evaluator_type)
manager_cls = SANDBOX_MANAGERS.get(benchmark_type, DefaultSandboxManager)
benchmark_cls = BENCHMARKS.get(benchmark_type) if benchmark_type is not None else None
```

with:

```python
evaluator_cls = registry.evaluators.get(evaluator_type)
manager_cls = (
    registry.sandbox_managers.get(benchmark_type, DefaultSandboxManager)
    if benchmark_type is not None
    else DefaultSandboxManager
)
benchmark_cls = registry.benchmarks.get(benchmark_type) if benchmark_type is not None else None
```

- [ ] **Step 5: Update sandbox and output jobs**

Modify `ergon_core/ergon_core/core/application/jobs/persist_outputs.py` and `ergon_core/ergon_core/core/application/jobs/sandbox_setup.py`:

```python
from ergon_core.api.registry import registry
```

Replace:

```python
manager_cls = SANDBOX_MANAGERS.get(..., DefaultSandboxManager)
```

with:

```python
manager_cls = registry.sandbox_managers.get(..., DefaultSandboxManager)
```

- [ ] **Step 6: Update experiment launch and define services**

Modify `ergon_core/ergon_core/core/application/experiments/launch.py`:

```python
from ergon_core.api.registry import registry
```

Replace evaluator and benchmark lookups with:

```python
evaluator_cls = registry.require_evaluator(evaluator_slug)
source = registry.require_benchmark(benchmark_slug)()
```

Modify `ergon_core/ergon_core/core/application/experiments/service.py` so `_benchmark_cls` caches `registry.benchmarks`, not builtins dicts:

```python
from ergon_core.api.registry import registry
...
if self._benchmarks is None:
    self._benchmarks = registry.benchmarks
return self._benchmarks[benchmark_slug]
```

- [ ] **Step 7: Update workflow/task mutation validation**

Modify `ergon_core/ergon_core/core/application/workflows/service.py`, `ergon_core/ergon_core/core/application/tasks/management.py`, and `ergon_core/ergon_core/core/domain/experiments/worker_spec.py`:

```python
from ergon_core.api.registry import registry
```

Replace membership checks:

```python
if slug not in WORKERS:
```

with:

```python
if slug not in registry.workers:
```

For error messages listing known workers, use:

```python
known = ", ".join(sorted(registry.workers))
```

- [ ] **Step 8: Run boundary and affected unit tests**

Run:

```bash
pytest tests/unit/registry/test_core_registry_boundary.py tests/unit/registry/test_component_registry.py tests/unit/registry/test_builtin_pairings.py -q
```

Expected: PASS.

---

### Task 5: Move Smoke Test Helpers Out Of Core

**Files:**
- Move from: `ergon_core/ergon_core/test_support/smoke_fixtures/**`
- Move to: `tests/fixtures/smoke_components/**`
- Modify: `tests/e2e/conftest.py`
- Modify: startup plugin referenced by E2E environment
- Test: E2E smoke tests and import-boundary tests.

- [ ] **Step 1: Add a test proving smoke fixtures do not live under core**

Create or extend `tests/unit/registry/test_core_registry_boundary.py`:

```python
def test_core_package_has_no_smoke_fixture_registration_package() -> None:
    assert not Path("ergon_core/ergon_core/test_support/smoke_fixtures").exists()
```

Expected initially: FAIL.

- [ ] **Step 2: Create tests fixture package**

Create:

```text
tests/fixtures/smoke_components/
tests/fixtures/smoke_components/__init__.py
tests/fixtures/smoke_components/benchmarks.py
tests/fixtures/smoke_components/sandbox.py
tests/fixtures/smoke_components/criteria/
tests/fixtures/smoke_components/workers/
```

Move files from `ergon_core/ergon_core/test_support/smoke_fixtures/**` into the new package, preserving internal folder shape where possible.

- [ ] **Step 3: Update imports in moved files**

Search:

```bash
rg "ergon_core\\.test_support\\.smoke_fixtures|test_support\\.smoke_fixtures" tests/fixtures/smoke_components tests ergon_core -n
```

Replace imports such as:

```python
from ergon_core.test_support.smoke_fixtures.workers.swebench_smoke import SweBenchSmokeWorker
```

with:

```python
from tests.fixtures.smoke_components.workers.swebench_smoke import SweBenchSmokeWorker
```

- [ ] **Step 4: Replace smoke registration function**

In `tests/fixtures/smoke_components/__init__.py`, define:

```python
"""Test-only smoke component registration."""

import os

from ergon_core.api.registry import ComponentRegistry, registry
from tests.fixtures.smoke_components.benchmarks import (
    MiniF2FSmokeBenchmark,
    ResearchRubricsSmokeBenchmark,
    SweBenchSmokeBenchmark,
)
from tests.fixtures.smoke_components.criteria.smoke_rubrics import (
    MiniF2FSmokeRubric,
    ResearchRubricsSmokeRubric,
    SweBenchSmokeRubric,
)
from tests.fixtures.smoke_components.criteria.timing import SmokePostRootTimingRubric
from tests.fixtures.smoke_components.sandbox import SmokeSandboxManager
from tests.fixtures.smoke_components.workers.minif2f_smoke import (
    MiniF2FFailingLeafWorker,
    MiniF2FRecursiveSmokeWorker,
    MiniF2FSadPathSmokeWorker,
    MiniF2FSmokeLeafWorker,
    MiniF2FSmokeWorker,
)
from tests.fixtures.smoke_components.workers.researchrubrics_smoke import (
    ResearchRubricsFailingLeafWorker,
    ResearchRubricsRecursiveSmokeWorker,
    ResearchRubricsSadPathSmokeWorker,
    ResearchRubricsSmokeLeafWorker,
    ResearchRubricsSmokeWorker,
)
from tests.fixtures.smoke_components.workers.swebench_smoke import (
    SweBenchFailingLeafWorker,
    SweBenchRecursiveSmokeWorker,
    SweBenchSadPathSmokeWorker,
    SweBenchSmokeLeafWorker,
    SweBenchSmokeWorker,
)


def register_smoke_components(target: ComponentRegistry = registry) -> None:
    """Register test-only smoke components into the supplied registry."""

    if os.environ.get("ENABLE_TEST_HARNESS") == "1":
        target.register_benchmark(ResearchRubricsSmokeBenchmark)
        target.register_benchmark(MiniF2FSmokeBenchmark)
        target.register_benchmark(SweBenchSmokeBenchmark)
        target.register_sandbox_manager(ResearchRubricsSmokeBenchmark.type_slug, SmokeSandboxManager)
        target.register_sandbox_manager(MiniF2FSmokeBenchmark.type_slug, SmokeSandboxManager)
        target.register_sandbox_manager(SweBenchSmokeBenchmark.type_slug, SmokeSandboxManager)

    target.register_worker(ResearchRubricsSmokeWorker.type_slug, ResearchRubricsSmokeWorker)
    target.register_worker(ResearchRubricsSmokeLeafWorker.type_slug, ResearchRubricsSmokeLeafWorker)
    target.register_worker(
        ResearchRubricsRecursiveSmokeWorker.type_slug,
        ResearchRubricsRecursiveSmokeWorker,
    )
    target.register_evaluator(ResearchRubricsSmokeRubric)
    target.register_evaluator(SmokePostRootTimingRubric)
    target.register_worker(ResearchRubricsSadPathSmokeWorker.type_slug, ResearchRubricsSadPathSmokeWorker)
    target.register_worker(ResearchRubricsFailingLeafWorker.type_slug, ResearchRubricsFailingLeafWorker)

    target.register_worker(MiniF2FSmokeWorker.type_slug, MiniF2FSmokeWorker)
    target.register_worker(MiniF2FSmokeLeafWorker.type_slug, MiniF2FSmokeLeafWorker)
    target.register_worker(MiniF2FRecursiveSmokeWorker.type_slug, MiniF2FRecursiveSmokeWorker)
    target.register_worker(MiniF2FSadPathSmokeWorker.type_slug, MiniF2FSadPathSmokeWorker)
    target.register_worker(MiniF2FFailingLeafWorker.type_slug, MiniF2FFailingLeafWorker)
    target.register_evaluator(MiniF2FSmokeRubric)

    target.register_worker(SweBenchSmokeWorker.type_slug, SweBenchSmokeWorker)
    target.register_worker(SweBenchSmokeLeafWorker.type_slug, SweBenchSmokeLeafWorker)
    target.register_worker(SweBenchRecursiveSmokeWorker.type_slug, SweBenchRecursiveSmokeWorker)
    target.register_worker(SweBenchSadPathSmokeWorker.type_slug, SweBenchSadPathSmokeWorker)
    target.register_worker(SweBenchFailingLeafWorker.type_slug, SweBenchFailingLeafWorker)
    target.register_evaluator(SweBenchSmokeRubric)
```

- [ ] **Step 5: Update E2E startup plugin**

Locate the startup plugin currently importing `ergon_core.test_support.smoke_fixtures`. Replace it with:

```python
from tests.fixtures.smoke_components import register_smoke_components


def register() -> None:
    register_smoke_components()
```

If the startup plugin loader expects a different function name, preserve that function name and call `register_smoke_components()` inside it.

- [ ] **Step 6: Remove old core smoke fixture package**

Delete `ergon_core/ergon_core/test_support/smoke_fixtures/**` only after all imports have been updated.

- [ ] **Step 7: Run smoke fixture import and boundary tests**

Run:

```bash
pytest tests/unit/registry/test_core_registry_boundary.py -q
pytest tests/e2e/test_swebench_smoke.py --collect-only -q
```

Expected: PASS.

---

### Task 6: Update E2E And Integration Tests To Use Explicit Registry Setup

**Files:**
- Modify: `tests/e2e/conftest.py`
- Modify: E2E startup plugin module(s)
- Modify: tests currently using `ergon_builtins.registry` dict mutation
- Test: E2E smoke suite.

- [ ] **Step 1: Search for remaining dict mutation against old registries**

Run:

```bash
rg "BENCHMARKS|WORKERS|EVALUATORS|SANDBOX_MANAGERS|ergon_builtins\\.registry|register_smoke_fixtures|smoke_fixtures" tests ergon_core ergon_builtins -n
```

Expected: remaining references are either in `ergon_builtins` registration implementation, tests asserting pairings via `ComponentRegistry`, or places to update.

- [ ] **Step 2: Update tests that temporarily patch registries**

Replace code like:

```python
from ergon_builtins.registry import BENCHMARKS, SANDBOX_MANAGERS

original_benchmarks = {slug: BENCHMARKS[slug] for slug in slugs}
BENCHMARKS[slug] = SmokeBenchmark
```

with fresh registry injection if the code under test accepts a registry, or explicit registration into global `registry` if the code under test is runtime-like:

```python
from ergon_core.api.registry import registry

registry.register_benchmark(SmokeBenchmark)
registry.register_sandbox_manager(SmokeBenchmark.type_slug, SmokeSandboxManager)
```

If a test mutates global `registry`, restore state in `finally`:

```python
original_benchmarks = dict(registry.benchmarks)
original_sandbox_managers = dict(registry.sandbox_managers)
try:
    registry.register_benchmark(SmokeBenchmark)
    registry.register_sandbox_manager(SmokeBenchmark.type_slug, SmokeSandboxManager)
    ...
finally:
    registry.benchmarks.clear()
    registry.benchmarks.update(original_benchmarks)
    registry.sandbox_managers.clear()
    registry.sandbox_managers.update(original_sandbox_managers)
```

- [ ] **Step 3: Keep host-side E2E black-box behavior**

`tests/e2e/conftest.py` currently documents that smoke fixture registration lives in the API container via `ERGON_STARTUP_PLUGINS`. Keep that mental model. Update the note to reference `tests.fixtures.smoke_components.register_smoke_components`, not `ergon_core.test_support`.

- [ ] **Step 4: Run E2E smoke collect and selected tests**

Run:

```bash
pytest tests/e2e/test_swebench_smoke.py --collect-only -q
```

Then, if the E2E stack is running:

```bash
pytest tests/e2e/test_swebench_smoke.py -q
```

Expected: collect passes. Runtime E2E passes when required infrastructure is available.

---

### Task 7: Improve Experiment Validation Error Messages

**Files:**
- Modify: `ergon_core/ergon_core/core/domain/experiments/worker_spec.py`
- Modify: `ergon_core/ergon_core/core/domain/experiments/validation.py`
- Test: existing or new experiment validation unit tests.

- [ ] **Step 1: Add tests for clear missing component errors**

Create or update `tests/unit/experiments/test_experiment_validation.py` with tests covering:

```python
import pytest

from ergon_core.core.domain.experiments import WorkerSpec


def test_worker_spec_unknown_worker_lists_registered_workers() -> None:
    spec = WorkerSpec(worker_slug="missing-worker", name="primary", model="stub:constant")

    with pytest.raises(ValueError, match="Unknown worker slug 'missing-worker'"):
        spec.validate_spec()
```

If the registry is process-global and other tests register workers, isolate this test by snapshotting/restoring `registry.workers`.

- [ ] **Step 2: Update `WorkerSpec.validate_spec`**

Use `ergon_core.api.registry.registry`:

```python
from ergon_core.api.registry import registry


def validate_spec(self) -> None:
    """Check that ``worker_slug`` refers to a known registry entry."""
    if self.worker_slug not in registry.workers:
        known = ", ".join(sorted(registry.workers)) or "<none>"
        raise ValueError(
            f"Unknown worker slug {self.worker_slug!r}; registered workers: {known}"
        )
    if not self.name:
        raise ValueError("WorkerSpec.name must be a non-empty string")
    if not self.model:
        raise ValueError("WorkerSpec.model must be a non-empty string")
```

- [ ] **Step 3: Add benchmark pairing metadata only if needed**

Do not add a large new abstraction in this refactor unless tests show a concrete gap. If student-facing validation needs “benchmark X expects worker Y,” add a small optional method to benchmark classes later:

```python
def recommended_worker_slugs(self) -> tuple[str, ...]:
    return ()
```

For this plan, keep pairing validation in tests and docs unless an existing runtime path requires it.

- [ ] **Step 4: Run experiment validation tests**

Run:

```bash
pytest tests/unit -q -k "validation or WorkerSpec or registry"
```

Expected: PASS.

---

### Task 8: Final Search, Lint, And Regression Verification

**Files:**
- No planned source files beyond cleanup.

- [ ] **Step 1: Verify no core imports of builtins registry remain**

Run:

```bash
rg "ergon_builtins\\.registry" ergon_core/ergon_core -n
```

Expected: no matches.

- [ ] **Step 2: Verify old smoke fixture location is gone**

Run:

```bash
test ! -d ergon_core/ergon_core/test_support/smoke_fixtures
```

Expected: exit code 0.

- [ ] **Step 3: Verify remaining registry references are intentional**

Run:

```bash
rg "BENCHMARKS|WORKERS|EVALUATORS|SANDBOX_MANAGERS" ergon_core ergon_builtins tests -n
```

Expected: no core runtime imports from `ergon_builtins.registry`; remaining uppercase dict names should either be deleted or constrained to docs/backwards compatibility tests.

- [ ] **Step 4: Run focused tests**

Run:

```bash
pytest tests/unit/registry -q
pytest tests/unit -q -k "experiment or workflow or task or sandbox or registry"
```

Expected: PASS.

- [ ] **Step 5: Run E2E collect**

Run:

```bash
pytest tests/e2e --collect-only -q
```

Expected: PASS.

- [ ] **Step 6: Run full available test suite**

Run:

```bash
pytest tests/unit -q
```

Expected: PASS. If E2E infrastructure is available, also run:

```bash
pytest tests/e2e -q
```

Expected: PASS or documented infrastructure failures unrelated to this refactor.

---

## Self-Review

- Spec coverage: The plan covers core registry creation, builtins update, removal of `BENCHMARKS`/`WORKERS`/`EVALUATORS`/`SANDBOX_MANAGERS` imports from core, moving smoke test helpers out of core, and updating integration/E2E registration flow.
- Placeholder scan: No unfinished placeholder markers remain. The only conditional areas are explicitly bounded implementation checks where the current codebase must be searched first, such as CLI entrypoint location and optional data dependency import constraints.
- Type consistency: `ComponentRegistry`, `WorkerFactory`, `registry`, and `register_*` function names are used consistently across tasks.

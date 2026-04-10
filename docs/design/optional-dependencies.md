# Design: Capability-Based Optional Dependencies for Arcane

**Status:** Proposal  
**Author:** (generated)  
**Date:** 2026-04-10

---

## 1. Problem Statement

`arcane-builtins` declares `torch>=2.0` and `transformers>=4.40.0` as hard
dependencies.  These exist for a single file: `models/transformers_backend.py`.
Every other component in the registry — all four workers, all four benchmarks,
all five evaluators, the sandbox manager, and two of three model backends — is
lightweight and needs nothing beyond `h-arcane` and its transitive deps.

This means:

- **Every user pays the torch install cost** (~2GB) even if they never use
  local inference.
- **Importing the registry triggers all transitive imports**, so a missing
  optional package causes a hard crash even for unrelated code paths.
- **There is no structured way** for a component to declare "I need package X"
  or for `Experiment.validate()` to check prerequisites before a run starts.
- **Error messages are cryptic** — a raw `ImportError` stack trace with no
  install hint.

---

## 2. Why This Is Hard: Experiments Are Runtime Compositions

The core challenge is that an Arcane Experiment is a **free-form runtime
composition** across four independent axes: benchmarks, workers, evaluators, and
model backends.  The dependency footprint of an experiment is only knowable once
the user has specified the _entire_ composition.

This rules out two common patterns:

### Why not per-component packages? (Prime Intellect pattern)

Prime Intellect's [research-environments](https://github.com/PrimeIntellect-ai/research-environments)
uses a separate installable package per environment (`opencode-swe`,
`opencode-lean`, `opencode-math`).  Each is a fixed recipe: one taskset + one
harness.  This works because their environments are **closed compositions** —
you pick a recipe, and the recipe determines all deps.

Arcane experiments are **open compositions**.  `gdpeval` doesn't tell you
whether you need torch (that depends on which worker/model backend you pair it
with).  Per-benchmark or per-worker packages would create a combinatorial
explosion of packages for every possible pairing, and leak internal taxonomy
into the packaging structure.

### Why not per-provider extras? (pydantic-ai pattern)

pydantic-ai uses extras groups per model provider (`pydantic-ai-slim[openai]`,
`pydantic-ai-slim[anthropic]`).  This works because they have **one composition
axis** — you pick a model provider and that determines the SDK dep.

Arcane has **four composition axes**.  Per-component extras (`[gdpeval]`,
`[react]`, `[transformers-backend]`) are too granular, couple packaging to
internal names, and force users to enumerate every component they want.

---

## 3. The Right Abstraction: Capabilities

The dependency clusters in `arcane-builtins` don't follow component boundaries.
They follow **capability boundaries** — what kind of heavy runtime do you need?

A capability cuts across component types.  `local-models` isn't "a worker
thing" or "a model backend thing" — it's a capability that any component might
need.  A future benchmark might do local model evaluation.  A future evaluator
might run a local judge model.

### Current Dependency Map

Audit of every file imported by `arcane_builtins/registry.py`:

| Capability | Heavy Deps | Components That Need It |
|------------|------------|------------------------|
| `local-models` | `torch`, `transformers`, `outlines` | `models/transformers_backend.py` |
| `data` | `pandas`, `datasets`, `huggingface_hub` | `benchmarks/gdpeval/benchmark.py`, `benchmarks/researchrubrics/benchmark.py` |
| _(core)_ | nothing beyond `h-arcane` | Everything else: all 4 workers, smoke-test/MiniF2F benchmarks+rubrics, GDPEval rubric+sandbox, stub rubric, vllm_backend (HTTP-only), cloud_passthrough |

Two capabilities cover all the optional deps.  Everything else is lightweight.

### The Composition-Time Insight

Since each component knows what capabilities it needs, and an Experiment is a
composition of components, the **experiment is the first point at which the full
set of requirements is knowable**.  `Experiment.validate()` already walks the
full object graph — it's the natural place to collect and report all missing
dependencies in one pass.

```
User builds Experiment:
  benchmark = GDPEvalBenchmark()        → needs: [data]
  workers   = {"w": ReActWorker(...)}   → needs: (nothing heavy)
  model_backend = "transformers:..."    → needs: [local-models]

Experiment.validate() collects:
  ✗ GDPEvalBenchmark requires 'pandas' but it is not installed
  ✗ GDPEvalBenchmark requires 'datasets' but it is not installed
      → Install with: pip install 'arcane-builtins[data]'
  ✗ TransformersBackend requires 'torch' but it is not installed
      → Install with: pip install 'arcane-builtins[local-models]'
```

One clear report, all at once, before anything runs.

---

## 4. Design Principles

1. **No lazy imports.**  Lazy/deferred import patterns (string-based registries,
   `importlib.import_module` at call time) destroy type safety, break IDE
   navigation, and make static analysis useless.  Every module uses normal eager
   imports.

2. **Capabilities as the packaging axis.**  Extras groups are named for what
   runtime capability they provide (`local-models`, `data`), not for which
   specific component they enable.  This decouples packaging from internal
   taxonomy and stays stable as components are added/removed.

3. **Conditionality at the composition boundary, not inside modules.**  The only
   place where `try/except ImportError` appears is the single file that
   assembles the registry from sub-registries.  Within each sub-registry and
   each component module, all imports are unconditional.

4. **Validate at experiment composition time.**  Each component declares its
   requirements.  `Experiment.validate()` — the first moment the full
   composition is known — collects all unmet requirements and reports them in
   one pass with clear install hints.

5. **Default experience is batteries-included.**  `pip install arcane-builtins[all]`
   (or the CLI default) gives you everything.  The slim base install is opt-in
   for server deployments and CI that want a lighter footprint.

---

## 5. Prior Art

### pydantic-ai (in our dep tree)

Uses a two-package split (`pydantic-ai` wraps `pydantic-ai-slim`) with
per-provider extras.  Each backend module does a top-level `try/except
ImportError` that re-raises with a pip install hint.  No lazy registries.
Module-internal imports are fully typed and eager.

**What we borrow:** Module-boundary import guards for clear errors.  No lazy
registries.  Eager, typed imports everywhere.

**Where we diverge:** pydantic-ai has one composition axis (model provider);
we have four.  Per-provider extras don't scale to our model.  We use
capability-based extras instead.

### Prime Intellect research-environments

Each environment is a separate installable package with its own
`pyproject.toml`.  Fixed recipes: one taskset + one harness per package.  The
root workspace has zero runtime dependencies.  Cross-package refs use editable
path deps.  Tasksets have their own optional extras for sub-variants.

**What we borrow:** The insight that the workspace root should have minimal
deps and each subsystem should own its dependency declaration.

**Where we diverge:** Their environments are closed compositions (fixed
recipes).  Our experiments are open compositions (user picks and mixes).
Per-component packages would leak internal taxonomy into packaging structure
and create combinatorial pressure.

---

## 6. Proposed Changes

### 6.1 Package Extras — `arcane-builtins/pyproject.toml`

Move heavy deps from `dependencies` to `[project.optional-dependencies]`,
organized by capability:

```toml
[project]
name = "arcane-builtins"
version = "0.1.0"
description = "Built-in benchmarks, workers, evaluators, and criteria for Arcane"
requires-python = ">=3.13"
dependencies = ["h-arcane"]

[project.optional-dependencies]
local-models = [
    "torch>=2.0",
    "transformers>=4.40.0",
    "outlines",
]
data = [
    "pandas",
    "datasets",
    "huggingface_hub",
]
all = [
    "arcane-builtins[local-models,data]",
]
```

The capability names are intentionally generic.  `local-models` says what you
get (local model inference), not which file uses it (`transformers_backend`).
New components that need torch just document "requires `[local-models]`" without
any packaging changes.

### 6.2 Split Registry — Sub-Registries by Capability

Replace the single `registry.py` with sub-registry modules organized by
capability.  Each sub-registry uses normal, eager, fully-typed imports.  A
thin composition layer merges them.

**`registry_core.py`** — always available, no heavy deps:

```python
"""Components with no dependencies beyond h-arcane.

All imports are eager and fully typed.  This module is always safe to import
regardless of which optional extras are installed.
"""

from h_arcane.api import Benchmark, Evaluator, Worker
from h_arcane.core.providers.sandbox.manager import BaseSandboxManager

from arcane_builtins.benchmarks.smoke_test.benchmark import SmokeTestBenchmark
from arcane_builtins.benchmarks.smoke_test.rubric import SmokeTestRubric
from arcane_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark
from arcane_builtins.benchmarks.minif2f.rubric import MiniF2FRubric
from arcane_builtins.benchmarks.gdpeval.rubric import StagedRubric
from arcane_builtins.benchmarks.gdpeval.sandbox import GDPEvalSandboxManager
from arcane_builtins.evaluators.rubrics.stub_rubric import StubRubric
from arcane_builtins.models.vllm_backend import resolve_vllm
from arcane_builtins.models.cloud_passthrough import resolve_cloud
from arcane_builtins.workers.baselines.stub_worker import StubWorker
from arcane_builtins.workers.baselines.training_stub_worker import TrainingStubWorker
from arcane_builtins.workers.baselines.smoke_test_worker import SmokeTestWorker
from arcane_builtins.workers.baselines.react_worker import ReActWorker

WORKERS: dict[str, type[Worker]] = {
    "stub-worker": StubWorker,
    "training-stub": TrainingStubWorker,
    "smoke-test-worker": SmokeTestWorker,
    "react-v1": ReActWorker,
}

BENCHMARKS: dict[str, type[Benchmark]] = {
    "smoke-test": SmokeTestBenchmark,
    "minif2f": MiniF2FBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "stub-rubric": StubRubric,
    "smoke-test-rubric": SmokeTestRubric,
    "staged-rubric": StagedRubric,
    "minif2f-rubric": MiniF2FRubric,
}

SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
}

MODEL_BACKENDS: dict[str, object] = {
    "vllm": resolve_vllm,
    "openai": resolve_cloud,
    "anthropic": resolve_cloud,
    "google": resolve_cloud,
}
```

**`registry_local_models.py`** — capability: `local-models`:

```python
"""Components that require the [local-models] capability (torch + transformers).

Eager, fully-typed imports.  This module will fail to import if torch/
transformers/outlines are not installed — that's by design.  The composition
layer in registry.py handles the ImportError gracefully.
"""

from arcane_builtins.models.transformers_backend import resolve_transformers

MODEL_BACKENDS: dict[str, object] = {
    "transformers": resolve_transformers,
}
```

**`registry_data.py`** — capability: `data`:

```python
"""Components that require the [data] capability (pandas, datasets, HF hub).

Eager, fully-typed imports.
"""

from h_arcane.api import Benchmark, Evaluator

from arcane_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark
from arcane_builtins.benchmarks.researchrubrics.benchmark import ResearchRubricsBenchmark
from arcane_builtins.benchmarks.researchrubrics.rubric import ResearchRubricsRubric

BENCHMARKS: dict[str, type[Benchmark]] = {
    "gdpeval": GDPEvalBenchmark,
    "researchrubrics": ResearchRubricsBenchmark,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    "research-rubric": ResearchRubricsRubric,
}
```

**`registry.py`** — the composition boundary:

```python
"""Composed registry: merges sub-registries based on installed capabilities.

This is the ONLY file with try/except ImportError.  Sub-registries use eager,
fully-typed imports.  Conditionality lives here, not inside component modules.
"""

import structlog

from h_arcane.api import Benchmark, Evaluator, Worker
from h_arcane.core.providers.generation.model_resolution import register_model_backend
from h_arcane.core.providers.sandbox.manager import BaseSandboxManager

from arcane_builtins.registry_core import (
    BENCHMARKS as _core_benchmarks,
    EVALUATORS as _core_evaluators,
    MODEL_BACKENDS as _core_model_backends,
    SANDBOX_MANAGERS as _core_sandbox_managers,
    WORKERS as _core_workers,
)

log = structlog.get_logger()

# -- Start from core (always available) ------------------------------------

WORKERS: dict[str, type[Worker]] = {**_core_workers}
BENCHMARKS: dict[str, type[Benchmark]] = {**_core_benchmarks}
EVALUATORS: dict[str, type[Evaluator]] = {**_core_evaluators}
SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {**_core_sandbox_managers}

_model_backends: dict[str, object] = {**_core_model_backends}

# -- Capability: local-models ----------------------------------------------

try:
    from arcane_builtins.registry_local_models import (
        MODEL_BACKENDS as _local_model_backends,
    )
    _model_backends.update(_local_model_backends)
except ImportError:
    log.info(
        "arcane-builtins[local-models] not installed; "
        "local transformers inference unavailable"
    )

# -- Capability: data ------------------------------------------------------

try:
    from arcane_builtins.registry_data import (
        BENCHMARKS as _data_benchmarks,
        EVALUATORS as _data_evaluators,
    )
    BENCHMARKS.update(_data_benchmarks)
    EVALUATORS.update(_data_evaluators)
except ImportError:
    log.info(
        "arcane-builtins[data] not installed; "
        "gdpeval and researchrubrics benchmarks unavailable"
    )

# -- Register model backends -----------------------------------------------

for prefix, resolver in _model_backends.items():
    register_model_backend(prefix, resolver)

# -- Install hints for slugs that require optional capabilities -------------

INSTALL_HINTS: dict[str, str] = {
    "transformers": "pip install 'arcane-builtins[local-models]'",
    "gdpeval": "pip install 'arcane-builtins[data]'",
    "researchrubrics": "pip install 'arcane-builtins[data]'",
    "research-rubric": "pip install 'arcane-builtins[data]'",
}
```

**Properties of this design:**

- Every sub-registry file is normal Python with fully-typed eager imports.
  Type checkers, IDEs, and linters work without modification.
- The composition file is the single, narrow conditionality boundary.
- Call sites (`WORKERS[slug]`) are unchanged — dict values are real
  `type[Worker]` references, not proxies.
- Sub-registries are organized by **capability**, not by component type.
  Adding a new benchmark that needs torch goes into `registry_local_models.py`,
  not into a hypothetical `registry_benchmarks.py`.

### 6.3 Component-Level Dependency Declarations

Add `required_packages` and `install_hint` ClassVars to the component ABCs.
Each component declares what it needs; `validate()` checks at composition time.

**New utility — `h_arcane/h_arcane/api/dependencies.py`:**

```python
"""Dependency checking utilities for component validation."""

import importlib.util


def check_packages(
    required: list[str],
    component_label: str,
) -> list[str]:
    """Check that required packages are importable.

    Returns a list of human-readable error strings.  Empty list = all good.
    """
    errors: list[str] = []
    for spec in required:
        name = spec.split(">=")[0].split("<=")[0].split("==")[0].split("<")[0].strip()
        if importlib.util.find_spec(name) is None:
            errors.append(f"{component_label} requires '{spec}' but it is not installed")
    return errors
```

**New exception — `h_arcane/h_arcane/api/errors.py`:**

```python
class DependencyError(Exception):
    """A component's required package is not installed."""
```

Using a dedicated exception type (not `ImportError` or `ValueError`) lets
`Experiment.validate()` callers distinguish "missing dependency" from "bad
configuration."

**ABC changes — Worker, Benchmark, Evaluator:**

Each ABC gets two new ClassVars with empty defaults (non-breaking) and a base
`validate()` implementation that runs the check:

```python
from h_arcane.api.dependencies import check_packages
from h_arcane.api.errors import DependencyError


class Worker(ABC):
    type_slug: ClassVar[str]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    # ... existing __init__, execute ...

    def validate(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Worker '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))
```

Same pattern on `Benchmark` and `Evaluator`.  Subclasses that override
`validate()` call `super().validate()` to inherit the dependency check.

**Concrete declarations on existing components:**

```python
# benchmarks/gdpeval/benchmark.py
class GDPEvalBenchmark(Benchmark):
    type_slug: ClassVar[str] = "gdpeval"
    required_packages: ClassVar[list[str]] = ["pandas", "datasets"]
    install_hint: ClassVar[str] = "pip install 'arcane-builtins[data]'"

# benchmarks/researchrubrics/benchmark.py
class ResearchRubricsBenchmark(Benchmark):
    type_slug: ClassVar[str] = "researchrubrics"
    required_packages: ClassVar[list[str]] = ["datasets", "huggingface_hub"]
    install_hint: ClassVar[str] = "pip install 'arcane-builtins[data]'"
```

Model backends are functions, not ABC subclasses, so the pattern is slightly
different.  `transformers_backend.py` already has a top-level import of `torch`
and `outlines` — it will fail at import time if missing, which the
`registry.py` composition layer catches.  If a future worker wraps local
inference, it would declare:

```python
class LocalInferenceWorker(Worker):
    type_slug: ClassVar[str] = "local-inference"
    required_packages: ClassVar[list[str]] = ["torch", "transformers"]
    install_hint: ClassVar[str] = "pip install 'arcane-builtins[local-models]'"
```

**No changes to `Experiment.validate()` logic.**  It already calls
`worker.validate()`, `benchmark.validate()`, and `evaluator.validate()` for
every component in the composition.  The base implementations now run
dependency checks automatically.  The experiment is the first point where the
full composition is known, and `validate()` is the natural moment to surface
all unmet requirements together.

### 6.4 Enriched Registry Lookup Errors

When a slug is absent because the capability isn't installed, use
`INSTALL_HINTS` for a clear message:

```python
def get_worker(slug: str) -> type[Worker]:
    cls = WORKERS.get(slug)
    if cls is None:
        hint = INSTALL_HINTS.get(slug, "")
        msg = f"Unknown worker slug '{slug}'"
        if hint:
            msg += f" — you may need: {hint}"
        raise RegistryLookupError(msg)
    return cls
```

This catches the case where a user configures `benchmark: gdpeval` but hasn't
installed `arcane-builtins[data]`.

---

## 7. What This Preserves

- **Experiments are free-form compositions.**  Packaging doesn't constrain what
  you can combine.  Any benchmark can pair with any worker.
- **Components don't know about each other's deps.**  GDPEval doesn't know or
  care whether you're using a local model or a cloud API.
- **Module-internal imports stay eager and typed.**  No `importlib.import_module`.
  No string-based class references.  Full IDE and type-checker support.
- **Registry dict types stay `dict[str, type[Worker]]`.**  Call sites unchanged.
- **Capability extras can grow independently.**  Adding `[vision]` for future
  image-processing components requires no changes to existing code.

---

## 8. Migration Path

The changes are independently shippable:

| Step | Change | Breaking? |
|------|--------|-----------|
| 1 | Add `dependencies.py` utility, `DependencyError` exception | No |
| 2 | Add `required_packages` / `install_hint` ClassVars with empty defaults to Worker, Benchmark, Evaluator ABCs; wire `check_packages` into base `validate()` | No |
| 3 | Add `required_packages` declarations to concrete component classes | No (adds validation; doesn't remove functionality) |
| 4 | Split `registry.py` into `registry_core` / `registry_local_models` / `registry_data` with composition layer | No (same dict contents when all extras installed) |
| 5 | Update `arcane-builtins/pyproject.toml`: move torch/transformers to `[local-models]`, pandas/datasets to `[data]` | **Soft break** — `pip install arcane-builtins` no longer includes torch; users need `[all]` or specific capabilities |
| 6 | Update `arcane-cli` to depend on `arcane-builtins[all]` | Packaging decision |

Steps 1–4 can land in a single PR with zero user-visible behavior change.
Step 5 is a packaging boundary change; it should be deliberate and announced.

---

## 9. Open Questions

1. **CLI default.**  Should `arcane-cli` depend on `arcane-builtins[all]`?
   The CLI is the primary developer tool; batteries-included preserves DX.
   Server deployments can use the slim install directly.

2. **Version checking.**  The v1 proposal only checks presence (`find_spec`),
   not version.  Adding `importlib.metadata.version()` comparisons is
   straightforward but adds the `packaging` dependency to `h-arcane`.  Worth it
   in v1, or defer?

3. **Sandbox-side dependencies.**  Some benchmarks install packages inside the
   E2B sandbox at runtime (GDPEval installs `pdfplumber`, `PyPDF2`,
   `reportlab`).  Host-side validation can't see these.  Should there be a
   `sandbox_requirements` ClassVar for future validation, or is that a separate
   concern?

4. **Model backend registration timing.**  Currently `register_model_backend()`
   is called as a side effect when `registry.py` is imported.  The split
   preserves this.  Should registration move to an explicit `init()` call?

5. **Future capability groups.**  As new components are added, what's the
   threshold for introducing a new capability extra vs. adding deps to an
   existing one?  Rough heuristic: a new capability when the dep cluster is
   large (>100MB install size) or has conflicting version constraints with
   existing capabilities.

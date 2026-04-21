---
status: active
opened: 2026-04-18
author: architecture-qa
architecture_refs: [docs/architecture/06_builtins.md#invariants, docs/architecture/01_public_api.md]
supersedes: []
superseded_by: null
---

# RFC: Move `BENCHMARK_DEPS` onto the `Benchmark` ABC

## Problem

`BENCHMARK_DEPS` at `ergon_cli/ergon_cli/onboarding/profile.py:48–56` is a
hand-maintained dict parallel to the benchmark registry. Every benchmark
registered in `ergon_builtins/ergon_builtins/registry_core.py` and
`ergon_builtins/ergon_builtins/registry_data.py` must also appear in this
dict or `ergon onboard` silently omits the benchmark's required keys and
extras. The failure mode is silent: the prompt never fires and the first error
is a sandbox-provisioning failure deep in an actual run.

**The regression has already happened once.** `swebench-verified` was absent
from `BENCHMARK_DEPS` until 2026-04-17; users onboarding for SWE-Bench were
never prompted for `E2B_API_KEY` or `ergon-builtins[data]`. Symptom: opaque
sandbox failure at runtime, not at `ergon onboard`.

**Current gap is larger than the dict shows.** Nine benchmark slugs are
registered (five core, four data-extra); `BENCHMARK_DEPS` covers only five.
The four missing slugs — `delegation-smoke`, `researchrubrics-smoke`,
`researchrubrics-ablated`, `researchrubrics-vanilla` — never surface in the
onboarding wizard at all (the wizard iterates `BENCHMARK_DEPS` keys at
`ergon_cli/ergon_cli/commands/onboard.py:22`).

Key file:line anchors for the problem:

- `ergon_cli/ergon_cli/onboarding/profile.py:40–55` — `BenchmarkDeps` class
  and `BENCHMARK_DEPS` dict (5 entries; 4 registered benchmarks absent)
- `ergon_cli/ergon_cli/onboarding/profile.py:77` — `required_keys()` reads
  `BENCHMARK_DEPS.get(b, BenchmarkDeps())` so missing benchmarks silently
  return empty deps
- `ergon_cli/ergon_cli/commands/onboard.py:22` — benchmark list offered to
  user is `[(slug, slug) for slug in BENCHMARK_DEPS]` — only 5 of 9
  registered benchmarks appear
- `ergon_builtins/ergon_builtins/registry_core.py:66–72` — 5 core benchmarks
- `ergon_builtins/ergon_builtins/registry_data.py:20–26` — 4 data-extra
  benchmarks
- `ergon_core/ergon_core/api/benchmark.py:18–65` — `Benchmark` ABC (no
  `onboarding_deps` field today)

The root cause is having two registries of the same fact. Validation tests
on top of two dicts catch regressions after the fact; collapsing to a single
source of truth prevents them.

## Proposal

Add `onboarding_deps: ClassVar[BenchmarkDeps]` as a required class attribute
on the `Benchmark` ABC. Move `BenchmarkDeps` from `ergon_cli/` to
`ergon_core/api/` so it is a public API type importable by benchmark authors
without pulling in CLI internals. Every concrete `Benchmark` subclass declares
its own deps at the class body. `ergon_cli/onboarding/profile.py` derives
deps by iterating the registry instead of a separate dict.

### Option chosen: class-level `ClassVar` on `Benchmark`

Benchmark authors set `onboarding_deps` at the class body, co-located with
`type_slug`. The ABC declares the attribute without a default so omitting it
is a `TypeError` at class instantiation time (Python raises when a concrete
class inherits an abstract `ClassVar` annotation that has no value and is
enforced via `__init_subclass__`). A class-body `__init_subclass__` hook on
`Benchmark` enforces presence at import time, not at runtime.

**Why not `Optional[BenchmarkDeps] = None`?** An implicit opt-out is the
failure mode this RFC exists to prevent. `None` as a default means a new
benchmark author can silently skip the declaration. Enforcement must be at
class-definition time, not runtime.

**Why move `BenchmarkDeps` to `ergon_core/api/`?** Benchmark classes live in
`ergon_builtins/`; they must not import from `ergon_cli/`. Today they don't —
but they will need to import `BenchmarkDeps` after this change. The type must
live in `ergon_core/api/` (the layer both `ergon_builtins/` and `ergon_cli/`
already depend on).

## Architecture overview

### Before

```
ergon_cli/onboarding/profile.py
  BENCHMARK_DEPS: dict[str, BenchmarkDeps]   ← hand-maintained, drifts
      "smoke-test" → BenchmarkDeps(e2b=True)
      "minif2f"    → BenchmarkDeps(e2b=True)
      "gdpeval"    → BenchmarkDeps(e2b=True, extras=["ergon-builtins[data]"])
      "researchrubrics" → BenchmarkDeps(extras=[...], optional_keys=["EXA_API_KEY"])
      "swebench-verified" → BenchmarkDeps(e2b=True, extras=["ergon-builtins[data]"])
      # delegation-smoke, researchrubrics-smoke, -ablated, -vanilla: ABSENT

  OnboardProfile.required_keys()
    ↓ BENCHMARK_DEPS.get(b, BenchmarkDeps())   ← silent empty for unknown slugs

ergon_builtins/benchmarks/<slug>/benchmark.py
  type_slug: ClassVar[str] = "..."             ← only link to onboarding

ergon_cli/commands/onboard.py
  [(slug, slug) for slug in BENCHMARK_DEPS]   ← 5 of 9 benchmarks visible
```

### After

```
ergon_core/api/benchmark_deps.py
  BenchmarkDeps(e2b, extras, optional_keys)   ← frozen Pydantic model, public API

ergon_core/api/benchmark.py
  class Benchmark(ABC):
    type_slug: ClassVar[str]
    onboarding_deps: ClassVar[BenchmarkDeps]  ← enforced by __init_subclass__

ergon_builtins/benchmarks/<slug>/benchmark.py
  class SomeBenchmark(Benchmark):
    type_slug = "some-slug"
    onboarding_deps = BenchmarkDeps(...)       ← declared once, here

ergon_cli/onboarding/profile.py
  # BenchmarkDeps imported from ergon_core.api (re-exported for CLI convenience)
  # BENCHMARK_DEPS dict DELETED

  OnboardProfile.required_keys()
    ↓ BENCHMARKS[slug].onboarding_deps        ← single source of truth

ergon_cli/commands/onboard.py
  [(slug, slug) for slug in BENCHMARKS]       ← all 9 registered benchmarks visible
```

### Data-flow change in `ergon onboard`

```
ergon onboard
  │
  ├─ wizard: benchmarks = select_multiple([slug for slug in BENCHMARKS])
  │            ^-- was BENCHMARK_DEPS keys, now BENCHMARKS keys (full set)
  │
  ├─ OnboardProfile.required_keys()
  │     for b in self.benchmarks:
  │       deps = BENCHMARKS[b].onboarding_deps   ← registry lookup, not dict
  │       if deps.e2b:  result["E2B_API_KEY"] = ...
  │       for k in deps.optional_keys: result.setdefault(k, ...)
  │
  └─ OnboardProfile.required_extras()
        for b in self.benchmarks:
          for e in BENCHMARKS[b].onboarding_deps.extras: extras.add(e)
```

## Type / interface definitions

### `BenchmarkDeps` — new file in `ergon_core/api/`

```python
# ergon_core/ergon_core/api/benchmark_deps.py

from pydantic import BaseModel, Field


class BenchmarkDeps(BaseModel, frozen=True):
    """Onboarding requirements for a single benchmark.

    Declared as a ClassVar on every Benchmark subclass. The onboarding
    wizard reads these to determine which API keys to prompt for and
    which pip extras to install.

    This is the single source of truth for a benchmark's onboarding
    requirements. Do not add a corresponding entry in any dict elsewhere.
    """

    e2b: bool = False
    """True if this benchmark requires an E2B sandbox (implies E2B_API_KEY)."""

    extras: tuple[str, ...] = ()
    """Pip extras that must be installed to use this benchmark,
    e.g. ``("ergon-builtins[data]",)``."""

    optional_keys: tuple[str, ...] = ()
    """API keys to prompt for during onboarding that are not strictly required
    but enhance benchmark functionality (e.g. ``("EXA_API_KEY",)``)."""
```

**Note:** `extras` and `optional_keys` change from `list[str]` to
`tuple[str, ...]` to satisfy `frozen=True`. The CLI callers iterate them —
no behavior change.

### `Benchmark` ABC changes — `ergon_core/api/benchmark.py`

```python
# ergon_core/ergon_core/api/benchmark.py  (modified)

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark_deps import BenchmarkDeps
from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.task_types import BenchmarkTask


class Benchmark(ABC):
    """Base class for all benchmarks.

    Subclasses MUST set ``type_slug`` and ``onboarding_deps`` and implement
    ``build_instances``.  Omitting ``onboarding_deps`` raises ``TypeError``
    at class definition time.
    """

    type_slug: ClassVar[str]
    onboarding_deps: ClassVar[BenchmarkDeps]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:  # slopcop: ignore[no-typing-any]
        super().__init_subclass__(**kwargs)
        # Only enforce on concrete classes (those that also define type_slug).
        # Abstract intermediate subclasses (e.g. ResearchRubricsBenchmark before
        # ResearchRubricsVanillaBenchmark) may omit the field.
        if not getattr(cls, "__abstractmethods__", None) and hasattr(cls, "type_slug"):
            if not hasattr(cls, "onboarding_deps") or not isinstance(
                cls.__dict__.get("onboarding_deps") or getattr(cls, "onboarding_deps", None),
                BenchmarkDeps,
            ):
                raise TypeError(
                    f"{cls.__qualname__} must declare "
                    f"'onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)'. "
                    f"See ergon_core/api/benchmark_deps.py."
                )

    def __init__(
        self,
        *,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        self.name = name or self.__class__.__name__
        self.description = description or ""
        self.metadata: dict[str, Any] = dict(metadata or {})  # slopcop: ignore[no-typing-any]

    @abstractmethod
    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        """Materialize benchmark instances.

        Returns a mapping of instance_key -> tasks for that instance.
        """
        ...

    def evaluator_requirements(self) -> Sequence[str]:
        """Declare evaluator slot names required by this benchmark."""
        return ("default",)

    def validate(self) -> None:
        """Check that runtime dependencies are available."""
        errors = check_packages(
            self.required_packages,
            f"Benchmark '{self.type_slug}'",
        )
        if errors:
            parts = [*errors]
            if self.install_hint:
                parts.append(f"Install with: {self.install_hint}")
            raise DependencyError("\n".join(parts))
```

**Enforcement logic:** `__init_subclass__` fires at class-definition time (at
import). It skips classes that still have `__abstractmethods__` (abstract
intermediates) and skips classes without `type_slug` (avoids false positives
on internal base classes). For concrete registered benchmarks this fires the
moment the module is imported — well before any runtime operation.

**Inheritance case (`ResearchRubricsVanillaBenchmark`):** The parent
`ResearchRubricsBenchmark` declares `onboarding_deps`; the child
`ResearchRubricsVanillaBenchmark` inherits it. The check uses `getattr` (not
`cls.__dict__`) so inheritance works. If the child needs different deps it
overrides the field; if not, it inherits. Both cases pass.

## Full implementations

### New file: `ergon_core/ergon_core/api/benchmark_deps.py`

```python
# ergon_core/ergon_core/api/benchmark_deps.py

from pydantic import BaseModel


class BenchmarkDeps(BaseModel, frozen=True):
    """Onboarding requirements for a single benchmark.

    Declared as a ClassVar on every Benchmark subclass. The onboarding
    wizard reads these to determine which API keys to prompt for and
    which pip extras to install.

    This is the single source of truth for a benchmark's onboarding
    requirements. Do not add a corresponding entry in any dict elsewhere.
    """

    e2b: bool = False
    extras: tuple[str, ...] = ()
    optional_keys: tuple[str, ...] = ()
```

### Modified benchmark classes

Each benchmark gains one line: `onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)`.

**`SmokeTestBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/smoke_test/benchmark.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class SmokeTestBenchmark(Benchmark):
    type_slug: ClassVar[str] = "smoke-test"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(e2b=True)
    # ... rest unchanged
```

**`MiniF2FBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class MiniF2FBenchmark(Benchmark):
    type_slug: ClassVar[str] = "minif2f"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(e2b=True)
    # ... rest unchanged
```

**`DelegationSmokeBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/delegation_smoke/benchmark.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class DelegationSmokeBenchmark(Benchmark):
    type_slug: ClassVar[str] = "delegation-smoke"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps()
    # ... rest unchanged
```

**`ResearchRubricsSmokeTestBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class ResearchRubricsSmokeTestBenchmark(Benchmark):
    type_slug: ClassVar[str] = "researchrubrics-smoke"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps()
    # ... rest unchanged
```

**`SweBenchVerifiedBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class SweBenchVerifiedBenchmark(Benchmark):
    type_slug: ClassVar[str] = "swebench-verified"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        e2b=True,
        extras=("ergon-builtins[data]",),
    )
    # ... rest unchanged
```

**`GDPEvalBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/gdpeval/benchmark.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class GDPEvalBenchmark(Benchmark):
    type_slug: ClassVar[str] = "gdpeval"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        e2b=True,
        extras=("ergon-builtins[data]",),
    )
    # ... rest unchanged
```

**`ResearchRubricsBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py`

```python
from ergon_core.api.benchmark_deps import BenchmarkDeps

class ResearchRubricsBenchmark(Benchmark):
    type_slug: ClassVar[str] = "researchrubrics"
    onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(
        extras=("ergon-builtins[data]",),
        optional_keys=("EXA_API_KEY",),
    )
    # ... rest unchanged
```

**`ResearchRubricsVanillaBenchmark`** — `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/vanilla.py`

`ResearchRubricsVanillaBenchmark` subclasses `ResearchRubricsBenchmark`. Since
both `researchrubrics` and `researchrubrics-vanilla` have the same deps,
the child inherits `onboarding_deps` from the parent. No declaration needed.
However, `researchrubrics-ablated` is registered under a separate key but
reuses `ResearchRubricsBenchmark` directly (same class, two registry keys) —
see registry_data.py. The `__init_subclass__` check uses `getattr` on the class
so inheritance satisfies the check.

**`ResearchRubricsAblated`** — no separate class exists; `registry_data.py:23`
maps `"researchrubrics-ablated"` to `ResearchRubricsBenchmark` directly.
The inherited `onboarding_deps` from `ResearchRubricsBenchmark` applies; no
new class file change needed.

## Exact diffs for modified files

### `ergon_core/ergon_core/api/benchmark.py`

```diff
--- a/ergon_core/ergon_core/api/benchmark.py
+++ b/ergon_core/ergon_core/api/benchmark.py
@@ -7,12 +7,15 @@
 from abc import ABC, abstractmethod
 from collections.abc import Mapping, Sequence
-from typing import Any, ClassVar
+from typing import Any, ClassVar

+from ergon_core.api.benchmark_deps import BenchmarkDeps
 from ergon_core.api.dependencies import check_packages
 from ergon_core.api.errors import DependencyError
 from ergon_core.api.task_types import BenchmarkTask


 class Benchmark(ABC):
     """Base class for all benchmarks.
 
-    Subclasses must set ``type_slug`` and implement ``build_instances``.
+    Subclasses MUST set ``type_slug`` and ``onboarding_deps`` and implement
+    ``build_instances``.  Omitting ``onboarding_deps`` raises ``TypeError``
+    at class definition time.
     """

     type_slug: ClassVar[str]
+    onboarding_deps: ClassVar[BenchmarkDeps]
     required_packages: ClassVar[list[str]] = []
     install_hint: ClassVar[str] = ""
 
+    def __init_subclass__(cls, **kwargs: Any) -> None:  # slopcop: ignore[no-typing-any]
+        super().__init_subclass__(**kwargs)
+        if not getattr(cls, "__abstractmethods__", None) and hasattr(cls, "type_slug"):
+            if not hasattr(cls, "onboarding_deps") or not isinstance(
+                cls.__dict__.get("onboarding_deps") or getattr(cls, "onboarding_deps", None),
+                BenchmarkDeps,
+            ):
+                raise TypeError(
+                    f"{cls.__qualname__} must declare "
+                    f"'onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)'. "
+                    f"See ergon_core/api/benchmark_deps.py."
+                )
+
     def __init__(
```

### `ergon_core/ergon_core/api/__init__.py`

```diff
--- a/ergon_core/ergon_core/api/__init__.py
+++ b/ergon_core/ergon_core/api/__init__.py
@@ -1,6 +1,7 @@
 """Object-first Ergon public API surface."""

 from ergon_core.api.benchmark import Benchmark
+from ergon_core.api.benchmark_deps import BenchmarkDeps
 from ergon_core.api.criterion import Criterion
 ...
 
 __all__ = [
     "Benchmark",
+    "BenchmarkDeps",
     "BenchmarkTask",
     ...
 ]
```

### `ergon_cli/ergon_cli/onboarding/profile.py`

```diff
--- a/ergon_cli/ergon_cli/onboarding/profile.py
+++ b/ergon_cli/ergon_cli/onboarding/profile.py
@@ -1,10 +1,10 @@
-"""OnboardProfile: user choices -> required keys and pip extras.
-
-The BENCHMARK_DEPS dict is the single source of truth for what each benchmark
-needs.  Keep it aligned with registry_core.py / registry.py.
-"""
+"""OnboardProfile: user choices -> required keys and pip extras."""

 from enum import Enum

-from pydantic import BaseModel, Field
+from pydantic import BaseModel, Field
+
+from ergon_core.api.benchmark_deps import BenchmarkDeps  # noqa: F401 — re-exported for CLI callers
 
 
 class LLMProvider(str, Enum):
@@ -36,18 +36,6 @@
     GPUProvider.RUNPOD: "RUNPOD_API_KEY",
 }
 
-
-class BenchmarkDeps(BaseModel):
-    """What a single benchmark requires beyond the base install."""
-
-    e2b: bool = False
-    extras: list[str] = Field(default_factory=list)
-    optional_keys: list[str] = Field(default_factory=list)
-
-
-BENCHMARK_DEPS: dict[str, BenchmarkDeps] = {
-    "smoke-test": BenchmarkDeps(e2b=True),
-    "minif2f": BenchmarkDeps(e2b=True),
-    "gdpeval": BenchmarkDeps(e2b=True, extras=["ergon-builtins[data]"]),
-    "researchrubrics": BenchmarkDeps(
-        extras=["ergon-builtins[data]"], optional_keys=["EXA_API_KEY"]
-    ),
-    "swebench-verified": BenchmarkDeps(e2b=True, extras=["ergon-builtins[data]"]),
-}
-
 
 class OnboardProfile(BaseModel):
     """Captures every user choice made during onboarding."""
@@ -60,24 +48,24 @@
     def required_keys(self) -> dict[str, str]:
         """Return {env_var: human_reason} derived purely from user choices."""
+        # reason: deferred import avoids circular dep at CLI startup; registry
+        # depends on ergon_builtins which depends on ergon_core.
+        from ergon_builtins.registry import BENCHMARKS
+
         result: dict[str, str] = {}

         for provider in self.llm_providers:
             env_var = PROVIDER_KEY_MAP[provider]
             result[env_var] = f"{provider.value} API access"

-        if any(BENCHMARK_DEPS.get(b, BenchmarkDeps()).e2b for b in self.benchmarks):
+        if any(BENCHMARKS[b].onboarding_deps.e2b for b in self.benchmarks if b in BENCHMARKS):
             result["E2B_API_KEY"] = "Sandboxed code execution for selected benchmarks"

         for b in self.benchmarks:
-            for k in BENCHMARK_DEPS.get(b, BenchmarkDeps()).optional_keys:
-                result.setdefault(k, f"Optional for {b}")
+            if b in BENCHMARKS:
+                for k in BENCHMARKS[b].onboarding_deps.optional_keys:
+                    result.setdefault(k, f"Optional for {b}")

         if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
             env_var = GPU_PROVIDER_KEY_MAP[self.gpu_provider]
             result[env_var] = f"GPU provisioning via {self.gpu_provider.value}"

         return result

     def required_extras(self) -> list[str]:
         """Pip extras to install based on choices."""
+        from ergon_builtins.registry import BENCHMARKS
+
         extras: set[str] = set()
         for b in self.benchmarks:
-            for e in BENCHMARK_DEPS.get(b, BenchmarkDeps()).extras:
-                extras.add(e)
+            if b in BENCHMARKS:
+                for e in BENCHMARKS[b].onboarding_deps.extras:
+                    extras.add(e)
         if self.training:
             extras.add("ergon-infra[training]")
         if self.gpu_provider and self.gpu_provider != GPUProvider.LOCAL:
             extras.add("ergon-infra[skypilot]")
         return sorted(extras)
```

### `ergon_cli/ergon_cli/commands/onboard.py`

```diff
--- a/ergon_cli/ergon_cli/commands/onboard.py
+++ b/ergon_cli/ergon_cli/commands/onboard.py
@@ -5,8 +5,6 @@
 from ergon_cli.onboarding.env_writer import write_env
 from ergon_cli.onboarding.installer import install_extras
 from ergon_cli.onboarding.profile import (
-    BENCHMARK_DEPS,
     GPUProvider,
     LLMProvider,
     OnboardProfile,
@@ -17,9 +15,13 @@
 def handle_onboard(args: Namespace) -> int:  # noqa: ARG001
     print("\nWelcome to Ergon!  Let's get your environment set up.\n")

+    # reason: deferred import avoids pulling heavy ergon_builtins deps at CLI startup.
+    from ergon_builtins.registry import BENCHMARKS
+
     profile = OnboardProfile()

     # --- Q1: benchmarks -------------------------------------------------------
     profile.benchmarks = select_multiple(
         "Which benchmarks do you want to run?",
-        [(slug, slug) for slug in BENCHMARK_DEPS],
+        [(slug, slug) for slug in sorted(BENCHMARKS)],
     )
```

## Package structure

### New file: `ergon_core/ergon_core/api/benchmark_deps.py`

The file stands alone; no new package is created. It is imported by
`ergon_core/api/benchmark.py` and re-exported via `ergon_core/api/__init__.py`.

### `ergon_core/ergon_core/api/__init__.py` additions

```python
# Add to existing __init__.py:
from ergon_core.api.benchmark_deps import BenchmarkDeps

# Add to __all__:
"BenchmarkDeps",
```

## Implementation order

| Step | PR | What | Files touched |
|---|---|---|---|
| **1** | PR 1 | Add `BenchmarkDeps` to `ergon_core/api/benchmark_deps.py`; export from `ergon_core/api/__init__.py` | ADD `ergon_core/ergon_core/api/benchmark_deps.py`; MODIFY `ergon_core/ergon_core/api/__init__.py` |
| **2** | PR 1 | Add `onboarding_deps: ClassVar[BenchmarkDeps]` annotation and `__init_subclass__` enforcement to `Benchmark`; import `BenchmarkDeps` | MODIFY `ergon_core/ergon_core/api/benchmark.py` |
| **3** | PR 1 | Populate `onboarding_deps` on all five core benchmarks: `SmokeTestBenchmark`, `MiniF2FBenchmark`, `DelegationSmokeBenchmark`, `ResearchRubricsSmokeTestBenchmark`, `SweBenchVerifiedBenchmark` | MODIFY 5 files |
| **4** | PR 1 | Populate `onboarding_deps` on all four data-extra benchmarks: `GDPEvalBenchmark`, `ResearchRubricsBenchmark`, `ResearchRubricsVanillaBenchmark`; confirm `researchrubrics-ablated` inherits from `ResearchRubricsBenchmark` and needs no separate class change | MODIFY 3 files |
| **5** | PR 1 | Rewrite `OnboardProfile.required_keys()` and `required_extras()` to read `BENCHMARKS[b].onboarding_deps`; delete `BENCHMARK_DEPS` dict and `BenchmarkDeps` class from `profile.py`; add re-export import for `BenchmarkDeps` from `ergon_core.api` | MODIFY `ergon_cli/ergon_cli/onboarding/profile.py` |
| **6** | PR 1 | Update `ergon onboard` wizard: replace `BENCHMARK_DEPS` key iteration with `BENCHMARKS` key iteration; remove `BENCHMARK_DEPS` import | MODIFY `ergon_cli/ergon_cli/commands/onboard.py` |
| **7** | PR 2 | Add contract test asserting every value in `BENCHMARKS` (core + data) has a `BenchmarkDeps`-typed `onboarding_deps` | ADD `tests/state/test_benchmark_contract.py` |
| **8** | PR 2 | Update existing `tests/state/test_onboard_profile.py` to remove assertions that reference `BENCHMARK_DEPS` directly; add assertions for the four previously-absent benchmarks | MODIFY `tests/state/test_onboard_profile.py` |
| **9** | PR 2 | Update `docs/architecture/06_builtins.md` and `docs/architecture/01_public_api.md` per the "On acceptance" section | MODIFY 2 docs |

Steps 1–6 land as a single PR. Steps 7–9 land as a follow-on PR. The contract
test (step 7) can be written against the completed implementation from PR 1
and acts as a regression guard.

## File map

### ADD

| File | Purpose |
|---|---|
| `ergon_core/ergon_core/api/benchmark_deps.py` | `BenchmarkDeps` frozen Pydantic model; single source of truth type |
| `tests/state/test_benchmark_contract.py` | Contract test: every registered benchmark has a valid `onboarding_deps` |

### MODIFY

| File | Change |
|---|---|
| `ergon_core/ergon_core/api/benchmark.py` | Add `onboarding_deps: ClassVar[BenchmarkDeps]` and `__init_subclass__` enforcement; import `BenchmarkDeps` |
| `ergon_core/ergon_core/api/__init__.py` | Export `BenchmarkDeps` |
| `ergon_builtins/ergon_builtins/benchmarks/smoke_test/benchmark.py` | Add `onboarding_deps = BenchmarkDeps(e2b=True)` |
| `ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py` | Add `onboarding_deps = BenchmarkDeps(e2b=True)` |
| `ergon_builtins/ergon_builtins/benchmarks/delegation_smoke/benchmark.py` | Add `onboarding_deps = BenchmarkDeps()` |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke.py` | Add `onboarding_deps = BenchmarkDeps()` |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py` | Add `onboarding_deps = BenchmarkDeps(e2b=True, extras=("ergon-builtins[data]",))` |
| `ergon_builtins/ergon_builtins/benchmarks/gdpeval/benchmark.py` | Add `onboarding_deps = BenchmarkDeps(e2b=True, extras=("ergon-builtins[data]",))` |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py` | Add `onboarding_deps = BenchmarkDeps(extras=("ergon-builtins[data]",), optional_keys=("EXA_API_KEY",))` |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/vanilla.py` | No class-body change required — inherits from `ResearchRubricsBenchmark`; verify via contract test |
| `ergon_cli/ergon_cli/onboarding/profile.py` | Delete `BenchmarkDeps` class and `BENCHMARK_DEPS` dict; rewrite `required_keys()` and `required_extras()` to use registry; add `BenchmarkDeps` re-export import |
| `ergon_cli/ergon_cli/commands/onboard.py` | Replace `BENCHMARK_DEPS` import and key iteration with `BENCHMARKS`; deferred import |
| `tests/state/test_onboard_profile.py` | Remove `BENCHMARK_DEPS` references; add assertions for `delegation-smoke`, `researchrubrics-smoke`, `researchrubrics-ablated`, `researchrubrics-vanilla` |

## Testing approach

### Contract test: `tests/state/test_benchmark_contract.py`

```python
# tests/state/test_benchmark_contract.py

"""Contract: every registered benchmark declares onboarding_deps."""

from __future__ import annotations

import pytest

from ergon_core.api.benchmark_deps import BenchmarkDeps


class TestBenchmarkOnboardingDepsContract:
    """Every benchmark in both registries must declare onboarding_deps."""

    def test_core_benchmarks_have_onboarding_deps(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            assert hasattr(cls, "onboarding_deps"), (
                f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'onboarding_deps'. "
                f"Add 'onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)' "
                f"to the class body."
            )
            assert isinstance(cls.onboarding_deps, BenchmarkDeps), (
                f"Benchmark '{slug}' ({cls.__qualname__}).onboarding_deps is not a "
                f"BenchmarkDeps instance; got {type(cls.onboarding_deps)!r}."
            )

    def test_data_benchmarks_have_onboarding_deps(self) -> None:
        pytest.importorskip("datasets", reason="ergon-builtins[data] not installed")
        from ergon_builtins.registry_data import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            assert hasattr(cls, "onboarding_deps"), (
                f"Benchmark '{slug}' ({cls.__qualname__}) is missing 'onboarding_deps'."
            )
            assert isinstance(cls.onboarding_deps, BenchmarkDeps)

    def test_onboarding_deps_is_frozen(self) -> None:
        """BenchmarkDeps instances must be immutable (frozen=True)."""
        from ergon_builtins.registry_core import BENCHMARKS

        for slug, cls in BENCHMARKS.items():
            deps = cls.onboarding_deps
            with pytest.raises(Exception):  # Pydantic ValidationError or TypeError
                deps.__dict__["e2b"] = not deps.e2b  # type: ignore[index]

    def test_known_e2b_benchmarks(self) -> None:
        from ergon_builtins.registry_core import BENCHMARKS

        assert BENCHMARKS["smoke-test"].onboarding_deps.e2b is True
        assert BENCHMARKS["minif2f"].onboarding_deps.e2b is True
        assert BENCHMARKS["swebench-verified"].onboarding_deps.e2b is True
        assert BENCHMARKS["delegation-smoke"].onboarding_deps.e2b is False
        assert BENCHMARKS["researchrubrics-smoke"].onboarding_deps.e2b is False
```

### Unit tests: update `tests/state/test_onboard_profile.py`

The existing tests in `tests/state/test_onboard_profile.py` pass through
`OnboardProfile` and do not import `BENCHMARK_DEPS` directly — they will
continue to pass after the dict is deleted. Additions needed:

```python
# Additional tests to add to tests/state/test_onboard_profile.py

class TestPreviouslyMissingBenchmarks:
    """Regression: delegation-smoke and researchrubrics-smoke were absent
    from BENCHMARK_DEPS before this RFC. Verify they now appear in the
    onboarding wizard choices and produce correct deps."""

    def test_delegation_smoke_has_no_e2b(self) -> None:
        p = OnboardProfile(benchmarks=["delegation-smoke"])
        assert "E2B_API_KEY" not in p.required_keys()
        assert p.required_extras() == []

    def test_researchrubrics_smoke_has_no_e2b(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics-smoke"])
        assert "E2B_API_KEY" not in p.required_keys()
        assert p.required_extras() == []

    def test_researchrubrics_ablated_needs_data_extra(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics-ablated"])
        assert "ergon-builtins[data]" in p.required_extras()

    def test_researchrubrics_vanilla_needs_data_extra(self) -> None:
        p = OnboardProfile(benchmarks=["researchrubrics-vanilla"])
        assert "ergon-builtins[data]" in p.required_extras()


class TestOnboardingWizardSeesAllBenchmarks:
    """The wizard must offer all registered benchmarks, not just the old 5."""

    def test_wizard_sees_nine_slugs(self) -> None:
        from ergon_builtins.registry import BENCHMARKS

        # All nine registered slugs must be visible
        expected = {
            "smoke-test", "minif2f", "delegation-smoke", "researchrubrics-smoke",
            "swebench-verified", "gdpeval", "researchrubrics", "researchrubrics-ablated",
            "researchrubrics-vanilla",
        }
        assert expected <= set(BENCHMARKS.keys())
```

### `__init_subclass__` enforcement test

```python
# Can live in tests/state/test_benchmark_contract.py

class TestBenchmarkSubclassEnforcement:
    def test_missing_onboarding_deps_raises_at_class_definition(self) -> None:
        from ergon_core.api.benchmark import Benchmark
        from ergon_core.api.task_types import BenchmarkTask

        with pytest.raises(TypeError, match="onboarding_deps"):
            class BadBenchmark(Benchmark):
                type_slug = "bad-test"

                def build_instances(self):
                    return {}

    def test_valid_declaration_does_not_raise(self) -> None:
        from ergon_core.api.benchmark import Benchmark
        from ergon_core.api.benchmark_deps import BenchmarkDeps

        class GoodBenchmark(Benchmark):
            type_slug = "good-test"
            onboarding_deps = BenchmarkDeps()

            def build_instances(self):
                return {}
        # No exception raised
```

## Trace / observability impact

No span, log, or metric changes. This RFC is source-only and touches no
runtime hot paths. `ergon onboard` is a CLI wizard (synchronous, no spans).
The `__init_subclass__` check fires at import time and is not traced.

If a benchmark author ships a class without `onboarding_deps`, the `TypeError`
appears in the import traceback — visible in logs during module load. This is
intentional: fail fast, fail loudly, at import rather than at runtime.

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| `__init_subclass__` fires on abstract intermediate subclasses | `TypeError` for legitimate abstract base classes that don't declare `type_slug` | Enforcement skips classes with `__abstractmethods__` set and skips classes without `type_slug`. `ResearchRubricsBenchmark` has `type_slug` and must declare `onboarding_deps`. |
| `ergon_cli/` imports `ergon_builtins/` (circular potential) | Import error if `profile.py` top-level imports from `ergon_builtins` | Imports of `BENCHMARKS` in `required_keys()`, `required_extras()`, and `handle_onboard()` are deferred inside function bodies (same pattern used elsewhere in CLI). |
| `BenchmarkDeps` field type change (`list` → `tuple`) breaks callers | Existing callers iterating `extras` or `optional_keys` expect sequences | Both `list` and `tuple` are iterable — the change is backward-compatible for iteration. `BENCHMARK_DEPS` is deleted so there are no external dict callers. |
| `researchrubrics-ablated` has no class of its own | `onboarding_deps` not visible from the registry value | `researchrubrics-ablated` maps to `ResearchRubricsBenchmark` in `registry_data.py:23`. `ResearchRubricsBenchmark.onboarding_deps` is set; the contract test passes on the class, not the slug. |
| `ResearchRubricsVanillaBenchmark` inherits but doesn't override `onboarding_deps` | `__init_subclass__` passes because it checks `getattr`, not `cls.__dict__` | Desired behavior. The contract test verifies the value is the right type regardless of whether it was inherited or declared. |
| Deleting `BENCHMARK_DEPS` breaks external code that imports it | API break for any caller outside the monorepo | No external package can register benchmarks (see `docs/architecture/06_builtins.md#extension-points`); the dict is not a documented public API. Worktrees have their own copy — they will need the same change applied. |
| `ergon onboard` wizard benchmark list order changes | UX difference; alphabetical sort vs. insertion order | The diff uses `sorted(BENCHMARKS)` — deterministic alphabetical order, cleaner than implicit insertion order. |

## Invariants affected

### `docs/architecture/06_builtins.md#invariants` (section 4)

- **REPLACE** the invariant "Every registered benchmark MUST have a matching
  onboarding deps entry [in `BENCHMARK_DEPS`]" with: "Every concrete
  `Benchmark` subclass MUST declare `onboarding_deps: ClassVar[BenchmarkDeps]`
  at the class body. The ABC's `__init_subclass__` enforces this at import
  time. The parallel `BENCHMARK_DEPS` dict no longer exists."
- **REMOVE** the `docs/architecture/06_builtins.md#anti-patterns` bullet
  "Forgetting the onboarding deps entry" (replaced by the enforced invariant).

### `docs/architecture/06_builtins.md` section 3 (Control flow — adding a benchmark)

- **REPLACE** step 3 "Declare the benchmark's onboarding deps so `ergon onboard`
  prompts correctly (see invariants)." → "Set `onboarding_deps:
  ClassVar[BenchmarkDeps] = BenchmarkDeps(...)` on the class. The ABC enforces
  this at import; the onboarding wizard reads it from the registry."

### `docs/architecture/06_builtins.md` Code map (section at end)

- **CHANGE** row "Onboarding deps dict" from `ergon_cli/onboarding/profile.py`
  to `ergon_core/api/benchmark_deps.py` (type declaration) and "each
  `Benchmark` subclass" (values).

### `docs/architecture/01_public_api.md` (core abstractions)

- **EXTEND** the `Benchmark` bullet: "Carries a `type_slug: ClassVar[str]` ...
  and an `onboarding_deps: ClassVar[BenchmarkDeps]` that the onboarding wizard
  reads to determine required API keys and pip extras."
- **ADD** a `BenchmarkDeps` bullet in the core abstractions list.
- **UPDATE** `add a new benchmark` extension-point step 6: delete the note
  about `ergon_cli/onboarding/profile.py::BENCHMARK_DEPS`. Replace with:
  "Set `onboarding_deps: ClassVar[BenchmarkDeps] = BenchmarkDeps(...)` on
  the class body."
- **UPDATE** the Code map table: add a `BenchmarkDeps` row pointing at
  `ergon_core/api/benchmark_deps.py`.

## Alternatives considered

- **Validation test only** — a unit test that cross-checks the two registries.
  Rejected: does not remove the duplication. A contributor still has to update
  two files; the test only catches forgotten updates after the fact.
- **Status quo** — keep the dict and rely on code review. Rejected: already
  regressed once (`swebench-verified`, 2026-04-17). Review is not load-bearing.
- **Entry-points based registration** — have each benchmark's package expose
  its deps via a Python entry point. Rejected for now: we do not need external
  package contribution (see `docs/architecture/06_builtins.md#extension-points`);
  entry points add complexity without buying anything at current scale.

## Relationship to `2026-04-18-template-spec-public-api.md`

The template-spec RFC (`docs/rfcs/active/2026-04-18-template-spec-public-api.md`)
adds a second required `ClassVar` to `Benchmark`: `template_spec:
ClassVar[TemplateSpec | NoSetupSentinel]`. The two RFCs are **orthogonal** —
they each add a different class-level attribute, touch different consumers
(`ergon onboard` here, `ergon benchmark setup` there), and have no shared
logic. However they **cannot land in arbitrary order** without coordination:

- If this RFC lands first: `Benchmark` gains `__init_subclass__` checking for
  `onboarding_deps`. The template-spec RFC must extend `__init_subclass__` to
  also check `template_spec`, or add its own independent check.
- If the template-spec RFC lands first: this RFC must similarly not overwrite
  the template-spec RFC's `__init_subclass__` hook. The safest approach is for
  `__init_subclass__` to check both attributes in one pass.

**Recommendation:** land this RFC first; when the template-spec RFC ships,
extend `__init_subclass__` in `benchmark.py` to validate both fields. Do not
implement two independent `__init_subclass__` overrides — only the last one
in MRO would execute. Coordinate in the second RFC's implementation PR.

## Open questions

- Should `BenchmarkDeps` become frozen (Pydantic `frozen=True`)? Yes, this
  RFC proposes `frozen=True`. It is a class-level `ClassVar` and mutation
  would be surprising. No caller mutates it today. The field types change from
  `list[str]` to `tuple[str, ...]` to satisfy the frozen constraint.
- Should we also move `SANDBOX_MANAGERS` and `SANDBOX_TEMPLATES` onto the ABC
  at the same time for consistency? No — those registries are consumed
  differently (by the Inngest runtime and `ergon benchmark setup`). The
  template-spec RFC (`docs/rfcs/active/2026-04-18-template-spec-public-api.md`)
  already covers the `SANDBOX_TEMPLATES` angle. Keep this RFC focused.

## On acceptance

When this RFC moves from `active/` to `accepted/`:
  - Update `docs/architecture/06_builtins.md#invariants` to drop the
    `BENCHMARK_DEPS` parallel-dict invariant and replace with the
    `onboarding_deps` class-attribute invariant.
  - Update `docs/architecture/06_builtins.md` section 3, section 6
    (anti-patterns), and the Code map table.
  - Update `docs/architecture/01_public_api.md` to include `BenchmarkDeps`
    and the `onboarding_deps` field on the public `Benchmark` API surface.
  - Coordinate with the template-spec RFC author on `__init_subclass__`
    ordering if that RFC is still active.
  - Link the implementation plan in `docs/superpowers/plans/`.

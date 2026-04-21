---
status: active
opened: 2026-04-18
author: architecture-qa
architecture_refs: [docs/architecture/06_builtins.md#extension-points, docs/architecture/01_public_api.md]
supersedes: []
superseded_by: null
---

# RFC: `TemplateSpec` as a public API on the `Benchmark` ABC

## Relationship to sibling RFC

`docs/rfcs/active/2026-04-18-onboarding-deps-on-benchmark-abc.md` moves
`BENCHMARK_DEPS` onto `Benchmark` as `onboarding_deps: ClassVar[BenchmarkDeps]`
using the same pattern this RFC uses for `template_spec`. Both RFCs should land
in the same PR or in consecutive PRs targeting the same migration checklist: if
`onboarding-deps` lands first, the nine benchmark migrations it requires are the
same nine benchmarks that need `template_spec` here. Duplicate that sweep once,
not twice. The shared migration step is explicit in the Implementation order
(§9) below. Neither RFC supersedes the other; they are additive class-level
attributes on the same ABC.

---

## Problem

Sandbox-template setup is implicit today. Every benchmark that needs a sandbox
handles setup a different way, and the variation is bespoke and undiscoverable:

1. **`minif2f`** — `MiniF2FSandboxManager.__init__` calls
   `sandbox/utils.py:resolve_template()` which reads
   `~/.ergon/sandbox_templates.json["minif2f"]["template_id"]` and falls back to
   the mutable template name `ergon-minif2f-v1` hardcoded in
   `ergon_builtins/benchmarks/minif2f/sandbox/utils.py:13`.
   `ergon_builtins/benchmarks/minif2f/sandbox/e2b.toml.template` declares
   `dockerfile = "Dockerfile"` and `cpu_count = 2, memory_mb = 8192`.
   `MiniF2FSandboxManager._install_dependencies` is a no-op (line 78–79) because
   the template has elan + Lean 4 + mathlib4 baked in.

2. **`swebench-verified`** — `SWEBenchSandboxManager.__init__` calls
   `sandbox/utils.py:resolve_template()` with `DEFAULT_TEMPLATE_NAME =
   "ergon-swebench-v1"` and `REGISTRY_SLUG = "swebench-verified"` in
   `ergon_builtins/benchmarks/swebench_verified/sandbox/utils.py:13–15`.
   `_install_dependencies` is a no-op (line 59–62). Template declared in
   `sandbox/e2b.toml.template`: `cpu_count = 4, memory_mb = 8192`.

3. **`gdpeval`** — No pre-built template. `GDPEvalSandboxManager._install_dependencies`
   (in `ergon_builtins/benchmarks/gdpeval/sandbox.py:28–41`) installs
   `pdfplumber PyPDF2 reportlab pytesseract` at sandbox-prep time via
   `pip install`. The `sandbox_utils.py` file provides download helpers
   (unrelated to template setup). There is no `e2b.toml.template` and no
   entry in `SANDBOX_TEMPLATES` for `gdpeval`.

4. **`smoke-test`** — `SmokeTestBenchmark` in
   `ergon_builtins/benchmarks/smoke_test/benchmark.py` has no sandbox
   at all. No `SandboxManager` entry in `SANDBOX_MANAGERS` or `SANDBOX_TEMPLATES`
   for `smoke-test`.

5. **`delegation-smoke`** — `DelegationSmokeBenchmark` in
   `ergon_builtins/benchmarks/delegation_smoke/benchmark.py` has no sandbox.
   No entry in `SANDBOX_MANAGERS` or `SANDBOX_TEMPLATES`.

6. **`researchrubrics-smoke`** — `ResearchRubricsSmokeTestBenchmark` in
   `ergon_builtins/benchmarks/researchrubrics/smoke.py`. No sandbox. No
   entry in `SANDBOX_MANAGERS` or `SANDBOX_TEMPLATES`.

7. **`researchrubrics`** — `ResearchRubricsBenchmark` in
   `ergon_builtins/benchmarks/researchrubrics/benchmark.py`. No sandbox.
   No entry in `SANDBOX_MANAGERS` or `SANDBOX_TEMPLATES`.

8. **`researchrubrics-ablated`** — Registered in `registry_data.py:24` as
   `ResearchRubricsBenchmark` (same class as `researchrubrics`, different slug).
   No sandbox. No entry in `SANDBOX_MANAGERS` or `SANDBOX_TEMPLATES`.

9. **`researchrubrics-vanilla`** — `ResearchRubricsVanillaBenchmark` in
   `ergon_builtins/benchmarks/researchrubrics/vanilla.py` subclasses
   `ResearchRubricsBenchmark`. No sandbox. No entry in `SANDBOX_MANAGERS` or
   `SANDBOX_TEMPLATES`.

The `ergon benchmark setup <slug>` path in
`ergon_cli/ergon_cli/commands/benchmark.py:60–175` dispatches by looking up
`SANDBOX_TEMPLATES[slug]` (the dict in `registry_core.py:90–93`). That dict
is hardcoded to `minif2f` and `swebench-verified`. Any new benchmark that needs
a template must remember to edit `SANDBOX_TEMPLATES`; there is no public API
that declares setup requirements. A contributor who forgets has no signal from
the system — the benchmark silently fails at first run with an opaque sandbox
error.

There is no declared shape for "this benchmark has no template" vs. "this
benchmark ships a pre-built template ID" vs. "this benchmark installs deps at
sandbox startup". The architecture doc
(`docs/architecture/06_builtins.md:124–126`) already calls this out as an open
problem under "Template setup".

---

## Proposal

Introduce `TemplateSpec` as a public Pydantic model in `ergon_core/api/` and
require every concrete `Benchmark` subclass to declare a `template_spec` class
variable. The `NoSetup` sentinel forces the author to make an explicit
declaration even when no setup is needed.

### `TemplateSpec` model

```python
# ergon_core/ergon_core/api/template_spec.py

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel


class TemplateSpec(BaseModel, frozen=True):
    """Declarative description of a benchmark's sandbox-template setup.

    A Benchmark subclass sets ``template_spec`` to either a ``TemplateSpec``
    describing how its sandbox is prepared, or to the ``NoSetup`` sentinel to
    declare intentionally that no template setup is required.

    Fields are intentionally additive: a benchmark may set ``e2b_template_id``
    (pre-built), ``build_recipe_path`` (buildable), ``runtime_install``
    (installed at sandbox-prep time), or any combination.
    """

    e2b_template_id: str | None = None
    """Pre-built E2B template name or pinned template_id.

    When set, ``ergon benchmark setup <slug>`` verifies the template exists in
    the user's E2B account and prints rebuild instructions if absent.

    Example: ``"ergon-minif2f-v1"``
    """

    build_recipe_path: Path | None = None
    """Path to the Dockerfile or setup directory that ``ergon benchmark setup``
    uses to build the E2B template.

    Typically ``Path(__file__).parent / "sandbox"`` pointing to the
    per-benchmark ``sandbox/`` folder (which must contain a ``Dockerfile`` and
    an ``e2b.toml.template``).

    When set alongside ``e2b_template_id``, the setup command can rebuild the
    template from this recipe.
    """

    runtime_install: tuple[str, ...] = ()
    """pip package specifiers installed at sandbox-prep time.

    Strings are passed verbatim to ``pip install``; extras markers such as
    ``"foo[bar]==1.2.3"`` are supported.

    When non-empty and ``build_recipe_path`` is None, ``ergon benchmark setup``
    prints a note that setup is deferred to sandbox prep (no build step is
    needed).
    """
```

### `NoSetup` sentinel

```python
# ergon_core/ergon_core/api/template_spec.py (continued)

from typing import TypeAlias


class _NoSetupType:
    """Singleton sentinel: this benchmark has no template setup requirements.

    Use the pre-constructed ``NoSetup`` instance, not this class directly.
    """

    _instance: _NoSetupType | None = None

    def __new__(cls) -> _NoSetupType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NoSetup"


NoSetup: _NoSetupType = _NoSetupType()
NoSetupSentinel: TypeAlias = _NoSetupType
```

### `Benchmark` ABC change

`template_spec` is declared without a default. A concrete subclass that omits
it will raise `AttributeError` on attribute access — the same early failure
mode used by unimplemented abstract methods. No `= None` default. The system
cannot notice a `None` default; it can notice an `AttributeError`.

```python
# ergon_core/ergon_core/api/benchmark.py  (modified)

from abc import ABC, abstractmethod
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.dependencies import check_packages
from ergon_core.api.errors import DependencyError
from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.template_spec import NoSetupSentinel, TemplateSpec


class Benchmark(ABC):
    """Base class for all benchmarks.

    Subclasses must set ``type_slug``, ``template_spec``, and implement
    ``build_instances``.
    """

    type_slug: ClassVar[str]
    template_spec: ClassVar[TemplateSpec | NoSetupSentinel]
    required_packages: ClassVar[list[str]] = []
    install_hint: ClassVar[str] = ""

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

### `ergon_core/api/__init__.py` additions

```python
# ergon_core/ergon_core/api/__init__.py  (additions only — full file not shown)

from ergon_core.api.template_spec import NoSetup, NoSetupSentinel, TemplateSpec

__all__ = [
    # ... existing exports unchanged ...
    "NoSetup",
    "NoSetupSentinel",
    "TemplateSpec",
]
```

### `ergon benchmark setup <slug>` dispatch (rewritten)

The CLI no longer looks up `SANDBOX_TEMPLATES`. It reads the benchmark class's
`template_spec` attribute and dispatches accordingly.

```python
# ergon_cli/ergon_cli/commands/benchmark.py  setup_benchmark() — full replacement

def setup_benchmark(args: Namespace) -> int:
    """Build and register the E2B sandbox template for *args.slug*.

    Dispatches off ``Benchmark.template_spec`` instead of the hardcoded
    ``SANDBOX_TEMPLATES`` dict. No explicit dispatch table is needed; the spec
    carries all information.
    """
    # reason: deferred to avoid pulling heavy ergon_builtins deps at CLI startup
    from ergon_builtins.registry import BENCHMARKS

    from ergon_core.api.template_spec import NoSetup, TemplateSpec

    slug: str = args.slug
    force: bool = args.force

    # 1. Look up benchmark class
    if slug not in BENCHMARKS:
        available = ", ".join(sorted(BENCHMARKS)) or "(none)"
        return _fail(f"Error: unknown benchmark slug '{slug}'.\nAvailable slugs: {available}")

    benchmark_cls = BENCHMARKS[slug]

    # 2. Read template_spec
    spec = benchmark_cls.template_spec

    # 3. NoSetup sentinel — nothing to do
    if isinstance(spec, NoSetup.__class__):
        print(f"Benchmark '{slug}' declares NoSetup: no template build required.")
        return 0

    if not isinstance(spec, TemplateSpec):
        return _fail(
            f"Error: '{slug}'.template_spec is neither TemplateSpec nor NoSetup. "
            f"Got: {spec!r}"
        )

    # 4. runtime_install only — deferred to sandbox prep; no build step needed
    if spec.runtime_install and spec.build_recipe_path is None and spec.e2b_template_id is None:
        pkgs = ", ".join(spec.runtime_install)
        print(
            f"Benchmark '{slug}' installs packages at sandbox-prep time ({pkgs}). "
            "No template build required."
        )
        return 0

    # 5. E2B template required
    if not settings.e2b_api_key:
        return _fail(
            "Error: E2B_API_KEY is not set.\n"
            "Export your E2B API key before running this command:\n"
            "  export E2B_API_KEY=<your-key>\n"
            "Get a key at https://e2b.dev/dashboard"
        )

    # 6. No build recipe — verify-only path
    if spec.build_recipe_path is None:
        print(
            f"Benchmark '{slug}' references E2B template '{spec.e2b_template_id}' "
            "but declares no build_recipe_path. Cannot rebuild automatically.\n"
            f"Ensure template '{spec.e2b_template_id}' exists in your E2B account."
        )
        return 0

    template_dir = spec.build_recipe_path

    # 7. Load e2b.toml.template from the recipe directory
    template_spec_path = template_dir / "e2b.toml.template"
    if not template_spec_path.exists():
        return _fail(f"Error: template spec not found at {template_spec_path}")

    with open(template_spec_path, "rb") as f:
        toml_spec = tomllib.load(f)

    template_name = toml_spec.get("template_name") or spec.e2b_template_id
    if not template_name:
        return _fail(
            f"Error: no template_name in {template_spec_path} and "
            "no e2b_template_id on TemplateSpec."
        )

    # 8. Idempotency check
    config = _config_dir()
    registry_path = config / "sandbox_templates.json"

    existing_templates: dict[str, object] = {}
    if registry_path.exists():
        with open(registry_path) as f:
            existing_templates = json.load(f)

    if not force and slug in existing_templates:
        tid = existing_templates[slug].get("template_id", "unknown")  # type: ignore[union-attr]
        print(f"Template already built: {tid}. Use --force to rebuild.")
        return 0

    # 9. Build via E2B SDK
    cpu_count = int(toml_spec.get("cpu_count", 2))
    memory_mb = int(toml_spec.get("memory_mb", 8192))
    start_cmd = toml_spec.get("start_cmd", "/bin/bash")
    dockerfile_name = toml_spec.get("dockerfile", "Dockerfile")
    dockerfile_path = template_dir / dockerfile_name

    if not dockerfile_path.exists():
        return _fail(f"Error: Dockerfile not found at {dockerfile_path}")

    dockerfile_content = dockerfile_path.read_text()

    print(f"Building E2B template '{template_name}' from {template_dir} ...")
    print(f"  cpu_count={cpu_count}, memory_mb={memory_mb}")

    def _on_build_logs(log: object) -> None:
        print(f"  [build] {log}", flush=True)

    template_def = (
        Template(file_context_path=str(template_dir))
        .from_dockerfile(dockerfile_content)
        .set_start_cmd(start_cmd=start_cmd, ready_cmd="echo ready")
    )

    t0 = time.monotonic()
    try:
        build_info = Template.build(
            template_def,
            name=template_name,
            cpu_count=cpu_count,
            memory_mb=memory_mb,
            on_build_logs=_on_build_logs,
        )
    except Exception as exc:  # noqa: BLE001  # slopcop: ignore[no-broad-except]
        return _fail(f"Error: E2B SDK Template.build() failed: {exc}")

    build_time = round(time.monotonic() - t0, 1)
    template_id = build_info.template_id

    # 10. Persist
    config.mkdir(parents=True, exist_ok=True)
    existing_templates[slug] = {
        "template_id": template_id,
        "template_name": template_name,
        "build_id": build_info.build_id,
        "built_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(registry_path, "w") as f:
        json.dump(existing_templates, f, indent=2)

    print(f"\nSuccess! Template ID: {template_id} (build {build_info.build_id}, {build_time}s)")
    print(f"Now run: `ergon benchmark run {slug} --worker <worker> --model <model> --limit 1`")
    return 0
```

---

## Architecture overview

### Before

```
ergon benchmark setup <slug>
  │
  ├─ look up SANDBOX_TEMPLATES[slug]        ← hardcoded dict in registry_core.py:90–93
  │   (only "minif2f" and "swebench-verified" present)
  │
  ├─ read e2b.toml.template from that path
  └─ build E2B template via SDK
```

Unknown slugs fail with "Error: unknown benchmark slug". Slugs without a
`SANDBOX_TEMPLATES` entry (gdpeval, smoke-test, researchrubrics*) also fail
even though some have no template requirement and some install deps at runtime.

```
SandboxManager.__init__
  └─ calls per-benchmark resolve_template() in sandbox/utils.py
       └─ reads ~/.ergon/sandbox_templates.json[slug]
            or falls back to hardcoded DEFAULT_TEMPLATE_NAME string
```

Two per-benchmark `sandbox/utils.py` files duplicate the same JSON-read logic
(minif2f:18–36, swebench_verified:18–36).

### After

```
ergon benchmark setup <slug>
  │
  ├─ BENCHMARKS[slug].template_spec         ← ClassVar on Benchmark subclass
  │
  ├─ isinstance(spec, _NoSetupType)  →  "nothing to do", exit 0
  │
  ├─ TemplateSpec with runtime_install only
  │   and no build_recipe_path              →  "deferred to sandbox prep", exit 0
  │
  ├─ TemplateSpec with build_recipe_path
  │   (and optional e2b_template_id)        →  build E2B template from recipe
  │                                              persist to ~/.ergon/sandbox_templates.json
  │
  └─ TemplateSpec with e2b_template_id only →  verify template exists; print
                                               rebuild instructions if absent
```

The `SandboxManager` side is unchanged in this RFC: `sandbox/utils.py` files
continue to work as-is. The `resolve_template()` helpers could be folded into a
shared utility in a follow-up once `template_spec` stabilises.

---

## Type / interface definitions

### Full `TemplateSpec` model and `_NoSetupType` sentinel

```python
# ergon_core/ergon_core/api/template_spec.py

from __future__ import annotations

from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel


class TemplateSpec(BaseModel, frozen=True):
    """Declarative description of a benchmark's sandbox-template setup.

    A Benchmark subclass sets ``template_spec`` to either a ``TemplateSpec``
    describing how its sandbox is prepared, or to the ``NoSetup`` sentinel to
    declare intentionally that no template setup is required.

    Fields are intentionally additive: a benchmark may set ``e2b_template_id``
    (pre-built), ``build_recipe_path`` (buildable), ``runtime_install``
    (installed at sandbox-prep time), or any combination.
    """

    e2b_template_id: str | None = None
    """Pre-built E2B template name or pinned template_id.

    When set, ``ergon benchmark setup <slug>`` verifies the template exists in
    the user's E2B account and prints rebuild instructions if absent.
    """

    build_recipe_path: Path | None = None
    """Path to the Dockerfile or setup directory that ``ergon benchmark setup``
    uses to build the E2B template.

    Typically ``Path(__file__).parent / "sandbox"`` pointing to the
    per-benchmark ``sandbox/`` folder containing a ``Dockerfile`` and an
    ``e2b.toml.template``.
    """

    runtime_install: tuple[str, ...] = ()
    """pip package specifiers installed at sandbox-prep time.

    Strings are passed verbatim to ``pip install``; extras markers such as
    ``"foo[bar]==1.2.3"`` are supported. When non-empty and
    ``build_recipe_path`` is None, no template build step is required.
    """


class _NoSetupType:
    """Singleton sentinel: this benchmark has no template setup requirements.

    Use the pre-constructed ``NoSetup`` instance, not this class directly.
    """

    _instance: _NoSetupType | None = None

    def __new__(cls) -> _NoSetupType:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NoSetup"


NoSetup: _NoSetupType = _NoSetupType()
NoSetupSentinel: TypeAlias = _NoSetupType
```

---

## Full implementations

### New file: `ergon_core/ergon_core/api/template_spec.py`

Full content shown in "Type / interface definitions" above.

### Modified file: `ergon_core/ergon_core/api/benchmark.py`

Full content shown in "Proposal" above. The only substantive change is adding
`template_spec: ClassVar[TemplateSpec | NoSetupSentinel]` with no default, and
importing the new types.

### Modified file: `ergon_core/ergon_core/api/__init__.py`

Add three new exports:

```python
from ergon_core.api.template_spec import NoSetup, NoSetupSentinel, TemplateSpec
```

Add `"NoSetup"`, `"NoSetupSentinel"`, `"TemplateSpec"` to `__all__`.

---

## Exact diffs for all nine benchmarks

Each benchmark adds exactly one `ClassVar` declaration.

### 1. `smoke-test` — `ergon_builtins/benchmarks/smoke_test/benchmark.py`

```diff
+from ergon_core.api.template_spec import NoSetup, NoSetupSentinel
+
 class SmokeTestBenchmark(Benchmark):
     type_slug: ClassVar[str] = "smoke-test"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup
```

### 2. `delegation-smoke` — `ergon_builtins/benchmarks/delegation_smoke/benchmark.py`

```diff
+from ergon_core.api.template_spec import NoSetup, NoSetupSentinel
+
 class DelegationSmokeBenchmark(Benchmark):
     type_slug: ClassVar[str] = "delegation-smoke"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup
```

### 3. `researchrubrics-smoke` — `ergon_builtins/benchmarks/researchrubrics/smoke.py`

```diff
+from ergon_core.api.template_spec import NoSetup, NoSetupSentinel
+
 class ResearchRubricsSmokeTestBenchmark(Benchmark):
     type_slug: ClassVar[str] = "researchrubrics-smoke"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup
```

### 4. `minif2f` — `ergon_builtins/benchmarks/minif2f/benchmark.py`

```diff
+from pathlib import Path
+from ergon_core.api.template_spec import NoSetupSentinel, TemplateSpec
+
 class MiniF2FBenchmark(Benchmark):
     type_slug: ClassVar[str] = "minif2f"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = TemplateSpec(
+        e2b_template_id="ergon-minif2f-v1",
+        build_recipe_path=Path(__file__).parent / "sandbox",
+    )
```

Template name matches `DEFAULT_TEMPLATE_NAME` in `sandbox/utils.py:13` and
`template_name` in `sandbox/e2b.toml.template:9`.

### 5. `swebench-verified` — `ergon_builtins/benchmarks/swebench_verified/benchmark.py`

```diff
+from pathlib import Path
+from ergon_core.api.template_spec import NoSetupSentinel, TemplateSpec
+
 class SweBenchVerifiedBenchmark(Benchmark):
     type_slug: ClassVar[str] = "swebench-verified"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = TemplateSpec(
+        e2b_template_id="ergon-swebench-v1",
+        build_recipe_path=Path(__file__).parent / "sandbox",
+    )
```

Template name matches `DEFAULT_TEMPLATE_NAME` in `sandbox/utils.py:13` and
`template_name` in `sandbox/e2b.toml.template:9`.

### 6. `gdpeval` — `ergon_builtins/benchmarks/gdpeval/benchmark.py`

```diff
+from ergon_core.api.template_spec import NoSetupSentinel, TemplateSpec
+
 class GDPEvalBenchmark(Benchmark):
     type_slug: ClassVar[str] = "gdpeval"
     required_packages: ClassVar[list[str]] = ["pandas", "huggingface_hub"]
     install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = TemplateSpec(
+        runtime_install=(
+            "pdfplumber",
+            "PyPDF2",
+            "reportlab",
+            "pytesseract",
+        ),
+    )
```

Package names match `_GDP_PACKAGES` in
`ergon_builtins/benchmarks/gdpeval/sandbox.py:19`.

### 7. `researchrubrics` — `ergon_builtins/benchmarks/researchrubrics/benchmark.py`

```diff
+from ergon_core.api.template_spec import NoSetup, NoSetupSentinel
+
 class ResearchRubricsBenchmark(Benchmark):
     type_slug: ClassVar[str] = "researchrubrics"
     required_packages: ClassVar[list[str]] = ["datasets", "huggingface_hub"]
     install_hint: ClassVar[str] = "pip install 'ergon-builtins[data]'"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup
```

`researchrubrics` has no sandbox; all evaluation is pure Python.

### 8. `researchrubrics-ablated` — `registry_data.py` (class alias)

`researchrubrics-ablated` is registered in `registry_data.py:24` as
`ResearchRubricsBenchmark` directly (same class, different slug). Because the
slug is only a registry key and does not have its own class, it inherits
`template_spec = NoSetup` from `ResearchRubricsBenchmark`. No per-file change
needed — the diff is the `ResearchRubricsBenchmark` change in item 7.

If a dedicated class is added in future, it must re-declare `template_spec`.

### 9. `researchrubrics-vanilla` — `ergon_builtins/benchmarks/researchrubrics/vanilla.py`

```diff
 class ResearchRubricsVanillaBenchmark(ResearchRubricsBenchmark):
     type_slug: ClassVar[str] = "researchrubrics-vanilla"
+    template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup
```

`NoSetup` is re-declared explicitly even though it inherits from
`ResearchRubricsBenchmark`, because the contract test (§10) validates per-class
directly, and the slug is distinct. Future readers should not have to chase the
inheritance chain to understand this class's setup story.

---

## Package structure

### New file: `ergon_core/ergon_core/api/template_spec.py`

Full content is in "Type / interface definitions". No new package needed; the
file is added to the existing `ergon_core/api/` module.

### `ergon_core/ergon_core/api/__init__.py` — additions only

```python
# Additions to existing __all__ list and import block:
from ergon_core.api.template_spec import NoSetup, NoSetupSentinel, TemplateSpec

# In __all__:
"NoSetup",
"NoSetupSentinel",
"TemplateSpec",
```

No new `__init__.py` files required.

---

## Implementation order

Phases are sized for separate PRs. Steps within a phase can land as a single
commit.

| Step | Phase | What | Files touched |
|---|---|---|---|
| 1 | PR 1 | Create `ergon_core/ergon_core/api/template_spec.py` with `TemplateSpec`, `_NoSetupType`, `NoSetup`, `NoSetupSentinel` | ADD 1 file |
| 2 | PR 1 | Add `template_spec: ClassVar[TemplateSpec \| NoSetupSentinel]` to `Benchmark` ABC; import new types | MODIFY `ergon_core/ergon_core/api/benchmark.py` |
| 3 | PR 1 | Add `NoSetup`, `NoSetupSentinel`, `TemplateSpec` to `ergon_core/api/__init__.py` | MODIFY `ergon_core/ergon_core/api/__init__.py` |
| 4 | PR 1 | Unit tests for `TemplateSpec` (frozen, valid combos) and `NoSetup` singleton | ADD `tests/state/test_template_spec.py` |
| 5 | PR 2 | Migrate all nine benchmarks: add `template_spec` ClassVar per §7 diffs | MODIFY 8 benchmark files (researchrubrics-ablated is free via inheritance) |
| 6 | PR 2 | Add contract test: every benchmark in `registry_core.BENCHMARKS` and `registry_data.BENCHMARKS` has `template_spec` that is `TemplateSpec` or `NoSetup` | ADD `tests/state/test_benchmark_contract.py` |
| 7 | PR 3 | Rewrite `setup_benchmark()` in `ergon_cli/ergon_cli/commands/benchmark.py` to dispatch off `TemplateSpec`; remove `SANDBOX_TEMPLATES` lookup | MODIFY `ergon_cli/ergon_cli/commands/benchmark.py` |
| 8 | PR 3 | Remove `SANDBOX_TEMPLATES` from `ergon_builtins/ergon_builtins/registry_core.py` | MODIFY `ergon_builtins/ergon_builtins/registry_core.py` |
| 9 | PR 3 | Update CLI tests in `tests/cli/test_benchmark_setup.py` to exercise `TemplateSpec` dispatch and `NoSetup` path | MODIFY `tests/cli/test_benchmark_setup.py` |

**PR ordering constraint:** PR 2 (benchmark migrations) depends on PR 1
(`TemplateSpec` in `ergon_core/api/`). PR 3 (CLI rewrite + `SANDBOX_TEMPLATES`
removal) depends on PR 2 (all benchmarks have `template_spec`). Steps 5 and 6
in PR 2 can be combined with the `onboarding-deps` RFC's parallel sweep of the
same nine benchmarks if both RFCs are accepted together.

---

## File map

### ADD

| File | Purpose |
|---|---|
| `ergon_core/ergon_core/api/template_spec.py` | `TemplateSpec` model, `_NoSetupType`, `NoSetup` singleton, `NoSetupSentinel` alias |
| `tests/state/test_template_spec.py` | Unit tests: `TemplateSpec` frozen/field contract, `NoSetup` singleton, `isinstance` checks |
| `tests/state/test_benchmark_contract.py` | Contract test: every registered benchmark has a valid `template_spec` |

### MODIFY

| File | Changes |
|---|---|
| `ergon_core/ergon_core/api/benchmark.py` | Add `template_spec: ClassVar[TemplateSpec \| NoSetupSentinel]` with no default; add imports |
| `ergon_core/ergon_core/api/__init__.py` | Add `NoSetup`, `NoSetupSentinel`, `TemplateSpec` to imports and `__all__` |
| `ergon_builtins/ergon_builtins/benchmarks/smoke_test/benchmark.py` | Add `template_spec = NoSetup` |
| `ergon_builtins/ergon_builtins/benchmarks/delegation_smoke/benchmark.py` | Add `template_spec = NoSetup` |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/smoke.py` | Add `template_spec = NoSetup` |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py` | Add `template_spec = NoSetup` |
| `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/vanilla.py` | Add `template_spec = NoSetup` (explicit re-declaration) |
| `ergon_builtins/ergon_builtins/benchmarks/minif2f/benchmark.py` | Add `template_spec = TemplateSpec(e2b_template_id="ergon-minif2f-v1", build_recipe_path=...)` |
| `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py` | Add `template_spec = TemplateSpec(e2b_template_id="ergon-swebench-v1", build_recipe_path=...)` |
| `ergon_builtins/ergon_builtins/benchmarks/gdpeval/benchmark.py` | Add `template_spec = TemplateSpec(runtime_install=(...))` |
| `ergon_cli/ergon_cli/commands/benchmark.py` | Rewrite `setup_benchmark()` to dispatch off `template_spec` |
| `ergon_builtins/ergon_builtins/registry_core.py` | Remove `SANDBOX_TEMPLATES` dict (PR 3, after CLI is migrated) |
| `tests/cli/test_benchmark_setup.py` | Update to exercise `TemplateSpec` dispatch and `NoSetup` path |

**Note:** `researchrubrics-ablated` has no dedicated class file; it inherits
`template_spec` from `ResearchRubricsBenchmark` via `registry_data.py:24`.

---

## Testing approach

### Unit tests — `tests/state/test_template_spec.py`

```python
# tests/state/test_template_spec.py

from __future__ import annotations

from pathlib import Path

import pytest

from ergon_core.api.template_spec import (
    NoSetup,
    NoSetupSentinel,
    TemplateSpec,
    _NoSetupType,
)


class TestTemplateSpec:
    def test_frozen_rejects_mutation(self) -> None:
        spec = TemplateSpec(e2b_template_id="my-template")
        with pytest.raises(Exception):  # pydantic ValidationError or AttributeError
            spec.e2b_template_id = "other"  # type: ignore[misc]

    def test_default_all_none(self) -> None:
        spec = TemplateSpec()
        assert spec.e2b_template_id is None
        assert spec.build_recipe_path is None
        assert spec.runtime_install == ()

    def test_runtime_install_tuple(self) -> None:
        spec = TemplateSpec(runtime_install=("pdfplumber", "PyPDF2==3.0.0"))
        assert len(spec.runtime_install) == 2
        assert "pdfplumber" in spec.runtime_install

    def test_build_recipe_path_accepts_path(self) -> None:
        p = Path("/some/benchmark/sandbox")
        spec = TemplateSpec(e2b_template_id="ergon-minif2f-v1", build_recipe_path=p)
        assert spec.build_recipe_path == p

    def test_full_combo(self) -> None:
        spec = TemplateSpec(
            e2b_template_id="ergon-minif2f-v1",
            build_recipe_path=Path("/fake"),
            runtime_install=("lean4-extra",),
        )
        assert spec.e2b_template_id == "ergon-minif2f-v1"


class TestNoSetupSingleton:
    def test_singleton_identity(self) -> None:
        a = _NoSetupType()
        b = _NoSetupType()
        assert a is b
        assert a is NoSetup

    def test_repr(self) -> None:
        assert repr(NoSetup) == "NoSetup"

    def test_isinstance_alias(self) -> None:
        assert isinstance(NoSetup, NoSetupSentinel)

    def test_not_template_spec(self) -> None:
        assert not isinstance(NoSetup, TemplateSpec)
```

### Contract test — `tests/state/test_benchmark_contract.py`

This is the load-bearing enforcement mechanism: every registered benchmark must
declare `template_spec`. The test exercises both the core registry (always
available) and the data registry (guarded by `[data]` extra).

```python
# tests/state/test_benchmark_contract.py

from __future__ import annotations

import pytest

from ergon_core.api.template_spec import NoSetup, TemplateSpec, _NoSetupType


def _all_benchmark_entries():
    """Yield (slug, benchmark_cls) for all registered benchmarks."""
    from ergon_builtins.registry_core import BENCHMARKS as core_benchmarks

    for slug, cls in core_benchmarks.items():
        yield slug, cls

    try:
        from ergon_builtins.registry_data import BENCHMARKS as data_benchmarks

        for slug, cls in data_benchmarks.items():
            yield slug, cls
    except ImportError:
        pass  # ergon-builtins[data] not installed; skip data benchmarks


@pytest.mark.parametrize("slug,benchmark_cls", list(_all_benchmark_entries()))
def test_benchmark_has_template_spec(slug: str, benchmark_cls: type) -> None:
    """Every registered benchmark must declare template_spec as TemplateSpec or NoSetup."""
    assert hasattr(benchmark_cls, "template_spec"), (
        f"Benchmark '{slug}' ({benchmark_cls.__name__}) has no 'template_spec' ClassVar. "
        "Add 'template_spec: ClassVar[TemplateSpec | NoSetupSentinel] = NoSetup' "
        "(or a TemplateSpec) to the class."
    )
    spec = benchmark_cls.template_spec
    assert isinstance(spec, (TemplateSpec, _NoSetupType)), (
        f"Benchmark '{slug}' ({benchmark_cls.__name__}).template_spec is neither "
        f"TemplateSpec nor NoSetup. Got: {spec!r}"
    )
```

### CLI tests — `tests/cli/test_benchmark_setup.py` additions

The existing tests in `tests/cli/test_benchmark_setup.py` test the
`SANDBOX_TEMPLATES`-based dispatch. After PR 3 they must be updated. New cases:

```python
# New tests to add to tests/cli/test_benchmark_setup.py

def test_nosetup_benchmark_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A benchmark with NoSetup should print a note and return 0."""
    # smoke-test declares NoSetup after migration
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    rc = setup_benchmark(_make_args(slug="smoke-test"))
    assert rc == 0


def test_runtime_install_only_exits_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    """A benchmark with only runtime_install should return 0 without building."""
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    rc = setup_benchmark(_make_args(slug="gdpeval"))
    assert rc == 0


def test_template_spec_build_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """minif2f has e2b_template_id + build_recipe_path: full build path runs."""
    monkeypatch.setenv("E2B_API_KEY", "test-key")
    monkeypatch.setenv("ERGON_CONFIG_DIR", str(tmp_path))
    _patch_sdk(monkeypatch)
    rc = setup_benchmark(_make_args(slug="minif2f"))
    assert rc == 0
```

---

## Trace / observability impact

No new spans, logs, or metrics are introduced by this RFC. The change is
purely in the class hierarchy and CLI dispatch logic.

One minor observability improvement is implicit: `ergon benchmark setup <slug>`
will now produce meaningful output for `NoSetup` and `runtime_install`-only
benchmarks instead of an opaque "unknown benchmark slug" error. The log surface
at INFO level is unchanged.

If future work adds an `ergon benchmark status` command, it can iterate
`BENCHMARKS` and read `template_spec` to report setup state per benchmark.

---

## Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| A benchmark author forgets to declare `template_spec` | `AttributeError` at `Benchmark.template_spec` access; runtime failure if `ergon benchmark setup` is called | Contract test in `test_benchmark_contract.py` catches this in CI. The `Benchmark` ABC has no default so the error surfaces early. |
| `build_recipe_path` points to a directory that exists in dev but not in a package install | `setup_benchmark` fails with "Dockerfile not found" | `Path(__file__).parent / "sandbox"` is relative to the benchmark file; it is always valid when the package is installed (the sandbox directory is shipped with the package). |
| `researchrubrics-ablated` has no dedicated class; inherits `template_spec` from `ResearchRubricsBenchmark` | If `ResearchRubricsBenchmark.template_spec` changes, `researchrubrics-ablated` silently inherits the change | Documented explicitly in §7 (item 8). The contract test validates the resolved class attribute value, so any change to the base class is caught. |
| `SANDBOX_TEMPLATES` removal (PR 3) breaks code that imports it from `registry_core` | `ImportError` or `KeyError` at import time for any external user of `SANDBOX_TEMPLATES` | `SANDBOX_TEMPLATES` is not in `ergon_core/api/` and not part of the public API surface. Internal uses: only `ergon_cli/commands/benchmark.py:71` imports it. PR 3 removes both the import and the dict in the same change. |
| `NoSetup` is a singleton; `isinstance(spec, NoSetup.__class__)` is fragile | Subtle logic errors if the class check is written incorrectly | Use `isinstance(spec, _NoSetupType)` throughout. `NoSetupSentinel` is a TypeAlias for `_NoSetupType` and works the same way. The RFC, tests, and CLI rewrite all use `isinstance(spec, _NoSetupType)`. |
| `runtime_install` extras markers (e.g. `"foo[bar]"`) passed verbatim to pip | Shell injection if strings are user-supplied | Strings are always literal constants in `ClassVar` declarations, not runtime user input. No shell; pip is called via Python API or subprocess with a list. |

---

## Invariants affected

- **`docs/architecture/06_builtins.md#invariants` — new invariant added.**
  "Every concrete `Benchmark` subclass MUST declare `template_spec` as either a
  `TemplateSpec` instance or the `NoSetup` sentinel. The `Benchmark` ABC
  provides no default. Omitting this declaration is detected at class attribute
  access time."

- **`docs/architecture/06_builtins.md#invariants` — existing invariant
  updated.** "A custom sandbox template implies a matching `ergon benchmark
  setup <slug>` code path" becomes: "A benchmark with `TemplateSpec.build_recipe_path`
  set implies that `ergon benchmark setup <slug>` will build the template.
  Benchmarks declaring `NoSetup` or `TemplateSpec(runtime_install=...)`-only are
  self-documenting: no build step is required."

- **`docs/architecture/06_builtins.md#extension-points` — "Template setup"
  bullet updated.** The current prose ("the pattern is implicit") is replaced
  by: "Template setup is declared via `template_spec: ClassVar[TemplateSpec |
  NoSetupSentinel]` on the `Benchmark` subclass. Use `NoSetup` for benchmarks
  with no sandbox, `TemplateSpec(runtime_install=(...))` for packages installed
  at sandbox-prep time, and `TemplateSpec(e2b_template_id=...,
  build_recipe_path=...)` for pre-built E2B templates."

- **`docs/architecture/06_builtins.md#follow-ups`** — the "Template setup is
  implicit" entry is removed on acceptance.

- **`docs/architecture/01_public_api.md`** — adds `TemplateSpec`, `NoSetup`,
  and `NoSetupSentinel` to the public API surface under "core abstractions".
  Adds `template_spec` to the description of `Benchmark`. The `code map` table
  gains a row for `TemplateSpec | NoSetup | NoSetupSentinel` pointing to
  `ergon_core/api/template_spec.py`.

---

## Alternatives considered

- **Keep the ad-hoc pattern.** Rejected: contributors forget setup steps and
  the system cannot notice. New benchmarks land with inconsistent bootstrap
  code.

- **`Optional[TemplateSpec] = None` with `None` meaning "no setup."**
  Rejected per system-owner directive: an implicit opt-out defeats the point.
  `NoSetup` forces the author to write the intent down. Easier to grep, easier
  to review, harder to miss.

- **String-enum `"none" | "e2b" | "runtime"`.** Rejected: the structured
  model carries the template ID and recipe path directly; a tagged string
  would require the author to populate parallel fields. The sentinel-plus-model
  approach keeps the declaration site one-line simple.

---

## Open questions

- Should the sentinel be a typealias plus singleton instance (as above) or a
  `Literal["NoSetup"]` string? Either works. Pick the one that reads cleaner
  in a `ClassVar` annotation; leaning toward the singleton since it avoids
  magic-string comparisons.
- Should `runtime_install` support extras markers (e.g.
  `"foo[bar]==1.2.3"`)? Probably yes — just document that the strings are
  passed verbatim to `pip install`. The `gdpeval` case uses bare package names
  today; no incompatibility.
- Does `build_recipe_path` support directories (a whole `sandbox/` folder)?
  Yes — both `minif2f` and `swebench-verified` use the full `sandbox/`
  directory as the E2B file context path. The path should point to the
  directory; the `Dockerfile` name within it comes from `e2b.toml.template`.

---

## On acceptance

When this RFC moves from `active/` to `accepted/`:
  - Update `docs/architecture/06_builtins.md#extension-points`,
    `#invariants`, and `#follow-ups` per §12.
  - Update `docs/architecture/01_public_api.md` with the new exports per §12.
  - Link the implementation plan in `docs/superpowers/plans/`.

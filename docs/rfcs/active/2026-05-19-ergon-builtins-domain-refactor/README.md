---
status: active
opened: 2026-05-19
author: codex
architecture_refs:
  - docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/00-readme.md
  - ergon_builtins/ergon_builtins/benchmarks/README.md
supersedes: []
superseded_by: null
---

# RFC: Ergon Built-ins Domain Refactor

## Problem

`ergon_builtins` has mostly moved to object-bound, Python-authored benchmarks,
but its package layout still carries several migration-era shapes:

- benchmark-owned implementations live beside compatibility packages such as
  `evaluators/`, `shared/criteria/`, and `shared/workers/`
- files named for one concept contain several concepts, especially rubric
  state, aggregation logic, evidence loading, prompt construction, and tool
  response models
- some benchmark criteria and tools import core application or persistence
  internals directly
- stale `__pycache__` directories and compatibility import paths obscure which
  modules are active source and which are historical leftovers

This makes it harder to tell where new benchmark code should go, which import
paths are canonical, and where the domain boundary is between built-in
benchmark authoring and core runtime services.

## Proposal

Keep the current object-bound authoring model: each benchmark package owns its
payload schema, dataset loading, sandbox, toolkit, worker factories, criteria,
and rubric. Do not restore a central registry or CLI authoring path as part of
this refactor.

The refactor should make `ergon_builtins` read as a set of benchmark domains
plus a small set of genuinely shared runtime primitives.

See [01-logic-smell-audit.md](01-logic-smell-audit.md) for the current
library-tier audit that motivates the target package shape and migration order.
See [02-implementation-stack.md](02-implementation-stack.md) for the proposed
4-PR stack off `dev`.

## Intended folder structure

```text
ergon_builtins/
  ergon_builtins/
    __init__.py

    benchmarks/
      README.md
      __init__.py

      minif2f/
        __init__.py
        benchmark.py
        task_schemas.py
        sandbox.py
        sandbox_template/
          Dockerfile
          README.md
          e2b.toml
          e2b.toml.template
          utils.py
        worker_factory.py
        prompts.py
        toolkit.py
        tools/
          __init__.py
          lean_operations.py
          response_models.py
          tool_builder.py
        criteria/
          __init__.py
          proof_verification.py
        rubric.py
        constants.py

      swebench_verified/
        __init__.py
        benchmark.py
        task_schemas.py
        sandbox.py
        sandbox_template/
          Dockerfile
          e2b.toml.template
          utils.py
        worker_factory.py
        prompts.py
        toolkit.py
        tools/
          __init__.py
          git_operations.py
          response_models.py
          tool_builder.py
        criteria/
          __init__.py
          test_resolution.py
          grading.py
          patch_extraction.py
        rubric.py

      researchrubrics/
        __init__.py
        benchmark.py
        vanilla.py
        task_schemas.py
        sandbox.py
        worker_factory.py
        prompts.py
        toolkit.py
        tools/
          __init__.py
          report_operations.py
          research_operations.py
          response_models.py
          tool_builder.py
        criteria/
          __init__.py
          judge.py
          evidence.py
          prompts.py
        rubric.py

      gdpeval/
        __init__.py
        benchmark.py
        task_schemas.py
        loader.py
        sandbox.py
        worker_factory.py
        prompts.py
        toolkit.py
        tools/
          __init__.py
          document_operations.py
          response_models.py
          tool_builder.py
        criteria/
          __init__.py
          code_check_builders.py
          llm_judge_builders.py
        rubric/
          __init__.py
          aggregation.py
          stage.py
          staged_rubric.py

    common/
      __init__.py
      llm/
        __init__.py
        structured_judge.py
      llm_context/
        __init__.py
        adapters/
          __init__.py
          base.py
          pydantic_ai.py

    models/
      __init__.py
      cloud_passthrough.py
      openrouter_backend.py
      openrouter_responses_backend.py
      resolution.py
      transformers_backend.py
      vllm_backend.py

    observability/
      __init__.py
      pydantic_ai_logfire.py

    sandbox/
      __init__.py
      e2b_runtime.py
      e2b_sandbox.py

    tools/
      __init__.py
      bash_sandbox_tool.py
      graph_toolkit.py
      graph_toolkit_types.py
      subtask_lifecycle_toolkit.py
      workflow_cli_tool.py

    workers/
      __init__.py
      react_prompts.py
      react_worker.py
      toolkit.py
      tool_budget.py
      training_stub_worker.py
```

## Package boundary rules

### Benchmark packages

Benchmark packages are the primary domain boundary.

Each benchmark package owns:

- its `Benchmark` subclass and `Task[...]` subclass
- its task payload models and dataset row conversion
- dataset loading and optional data dependency handling
- benchmark-specific sandbox setup
- benchmark-specific toolkit config
- benchmark-specific runtime tools
- benchmark-specific worker factories
- benchmark-specific criteria
- benchmark-specific rubric aggregation

Benchmark packages may import from:

- `ergon_core.api`
- `ergon_builtins.common`
- `ergon_builtins.models`
- `ergon_builtins.observability`
- `ergon_builtins.sandbox`
- `ergon_builtins.tools`
- `ergon_builtins.workers`
- sibling modules in the same benchmark package

Benchmark criteria should not import core persistence repositories, SQLModel
sessions, or application service implementations directly. If a criterion needs
run resources, logs, or graph data, that data should arrive through
`CriterionContext` public capabilities or a small injected adapter owned by the
runtime boundary.

### Shared workers

`ergon_builtins.workers` contains generic worker machinery only.

It may contain:

- `ReActWorker`
- `TrainingStubWorker`
- the serializable `Toolkit` base class
- ReAct prompt fragments that are genuinely shared
- tool budget primitives

It should not contain benchmark-owned worker factories. A function like
`make_minif2f_worker()` belongs in
`ergon_builtins.benchmarks.minif2f.worker_factory`.

### Shared tools

`ergon_builtins.tools` contains reusable tools that are not specific to one
benchmark domain.

Good fits:

- sandbox bash command wrapper
- workflow CLI tool
- graph/resource inspection tools
- subtask lifecycle tools

Poor fits:

- Lean proof tools
- SWE-Bench git/apply helpers
- ResearchRubrics report-writing helpers
- GDPEval document transformation helpers

Benchmark-specific tools should live under
`ergon_builtins.benchmarks.<slug>.tools`.

### Criteria and rubrics

There should be no top-level `evaluators/` package after the refactor unless a
criterion or rubric is truly independent of all benchmark payloads and evidence
models.

Canonical locations:

- MiniF2F proof checking:
  `benchmarks/minif2f/criteria/proof_verification.py`
- SWE-Bench test resolution:
  `benchmarks/swebench_verified/criteria/test_resolution.py`
- ResearchRubrics dynamic LLM judging:
  `benchmarks/researchrubrics/criteria/judge.py`
- GDPEval staged rubric:
  `benchmarks/gdpeval/rubric/staged_rubric.py`

If a generic `LLMJudgeCriterion` remains useful, put it under either:

- `ergon_builtins.common.llm` if it is primarily a judging utility, or
- `ergon_builtins.tools` only if it is exposed as a worker tool

Do not keep both `shared/criteria/*` and `evaluators/criteria/*` as competing
import surfaces.

### Models

`ergon_builtins.models` remains the canonical home for model target resolution
and concrete backend adapters. The current `shared/models` compatibility layer
should be removed once imports are updated.

### Sandbox infrastructure

`ergon_builtins.sandbox` remains singular and contains cross-cutting sandbox
adapters only. Concrete benchmark sandboxes stay in benchmark packages:

- `benchmarks/minif2f/sandbox.py`
- `benchmarks/swebench_verified/sandbox.py`
- `benchmarks/researchrubrics/sandbox.py`
- `benchmarks/gdpeval/sandbox.py`

There should be no source `sandboxes/` package. Stale `sandboxes/__pycache__`
artifacts should be removed.

The E2B sandbox layer should be expressed as two concepts:

- `E2BSandboxRuntime`: the concrete implementation of the public
  `SandboxRuntime` protocol using the E2B SDK under the hood
- `E2BSandbox`: a reusable `Sandbox` subclass that implements `provision()` and
  `_bind_runtime()` once by attaching an `E2BSandboxRuntime`

Benchmark E2B sandboxes should usually be config-only subclasses of
`E2BSandbox`. They should not each repeat the same provision/bind boilerplate.

Target shape:

```python
class E2BSandboxRuntime:
    @classmethod
    async def create(
        cls,
        *,
        template: str | None,
        envs: dict[str, str] | None,
        timeout_seconds: int | None,
    ) -> "E2BSandboxRuntime": ...

    @classmethod
    async def connect(cls, sandbox_id: str) -> "E2BSandboxRuntime": ...

    async def run_command(...): ...
    async def write_file(...): ...
    async def read_file(...): ...
    async def list_files(...): ...
    async def close(self) -> None: ...
    async def close_local(self) -> None: ...
```

```python
class E2BSandbox(Sandbox):
    template: str | None = None

    async def provision(self) -> None:
        object.__setattr__(self, "_runtime", await self._runtime_create())

    async def _bind_runtime(self, sandbox_id: str) -> None:
        object.__setattr__(self, "_runtime", await self._runtime_connect(sandbox_id))

    async def _runtime_create(self) -> E2BSandboxRuntime:
        return await E2BSandboxRuntime.create(
            template=self.template,
            envs=self.env or None,
            timeout_seconds=self.timeout_seconds,
        )

    async def _runtime_connect(self, sandbox_id: str) -> E2BSandboxRuntime:
        return await E2BSandboxRuntime.connect(sandbox_id)
```

Benchmark sandboxes then collapse to declarative config:

```python
class LeanSandbox(E2BSandbox):
    template: str = "ergon-minif2f-v1"
    requires_network: bool = False
    output_path: str = "/workspace/final_output/"
    lean_version: str = "4.7.0"
```

## Migration

The refactor should happen in small slices.

1. Remove generated artifacts from the source tree:
   delete `__pycache__` directories, `.pyc` files, and stray files such as
   `benchmarks/gdpeval/Untitled`.

2. Establish canonical worker imports:
   move `workers/baselines/*` to `workers/*`, update imports, and delete the
   compatibility wrappers in `shared/workers`.

3. Rename benchmark factory modules:
   move each `benchmarks/<slug>/workers.py` to
   `benchmarks/<slug>/worker_factory.py`, update docs and imports.

4. Move benchmark-specific tool code:
   replace each monolithic `_tools.py` with a package-level `tools/` folder
   containing response models, operations, and a thin `tool_builder.py`.

5. Move benchmark-specific criteria:
   replace `rules/`, `criteria.py`, and detached top-level evaluator imports
   with benchmark-local `criteria/` packages.

6. Split heavy rubric logic:
   especially `gdpeval/rubric.py` into `rubric/stage.py`,
   `rubric/aggregation.py`, and `rubric/staged_rubric.py`.

7. Replace `_manager_backed.py` with explicit E2B sandbox infrastructure:
   introduce `sandbox/e2b_runtime.py` and `sandbox/e2b_sandbox.py`, then make
   benchmark E2B sandboxes inherit from `E2BSandbox` instead of overriding
   `provision()` and `_bind_runtime()` individually.

8. Remove compatibility import surfaces:
   delete `shared/criteria`, `shared/models`, and `evaluators` once no imports
   depend on them.

9. Add architecture tests:
   enforce no source `__pycache__`, no top-level `evaluators`, no
   `shared/criteria`, no direct persistence imports from benchmark criteria,
   no `_manager_backed.py`, and one canonical benchmark package shape.

## Invariants affected

This RFC introduces these invariants:

- Built-in benchmark authoring is benchmark-owned and object-bound.
- Benchmark-specific concepts live under
  `ergon_builtins.benchmarks.<slug>`.
- Shared packages contain only code used across multiple benchmark domains.
- Benchmark criteria do not import core persistence or application service
  implementations directly.
- E2B-backed benchmark sandboxes inherit common E2B provisioning and binding
  behavior instead of each repeating E2B runtime setup.
- Compatibility import packages are temporary and should not be used as
  canonical authoring locations.

## Alternatives considered

### Reintroduce central registries

Rejected for this RFC. The current built-ins README explicitly says there is
no CLI authoring path and no core registry to edit. The refactor should clarify
the architecture that exists now rather than revive an older slug registry
design.

### Keep `_tools.py` files but clean internals

Rejected as the final structure. The `_tools.py` pattern keeps runtime tool
builders import-light, which is useful, but the files now mix response models,
sandbox operations, parsing helpers, and pydantic-ai tool construction. A
`tools/` subpackage preserves lazy imports while giving each concept a home.

### Keep top-level `shared/`

Partially rejected. Some shared code is real, but `shared/criteria`,
`shared/workers`, and `shared/models` are currently mostly compatibility import
surfaces. The clearer shape is canonical packages named by concept:
`workers`, `models`, `tools`, `common`, `sandbox`, and `observability`.

## Open questions

1. Should generic `CodeCheckCriterion` and `LLMJudgeCriterion` remain as
   public built-in criteria, or should they become benchmark-local builders
   only?
2. Should `ResearchRubricsJudgeCriterion` load run resources through new
   `CriterionContext` public methods, or through an injected resource reader
   adapter?
3. Should `workers/react_prompts.py` stay generic, or should benchmark-specific
   prompts move entirely to `benchmarks/<slug>/prompts.py`?
4. Should `tools/graph_toolkit.py` remain in built-ins, or move closer to core
   public worker context APIs?

## On acceptance

When this RFC moves from `active/` to `accepted/`, also:

- update `ergon_builtins/ergon_builtins/benchmarks/README.md`
- add an implementation plan under `docs/superpowers/plans/`
- add architecture tests that enforce the accepted package boundaries

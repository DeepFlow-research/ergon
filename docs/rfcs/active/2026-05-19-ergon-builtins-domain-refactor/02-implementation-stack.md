# Implementation Stack

This stack refactors `ergon_builtins` toward library-tier example code while
keeping each PR reviewable on its own. Each PR should branch from `dev` or from
the previous PR in the stack, depending on how tightly the changes depend on
earlier renames.

## Stack goals

- make the active built-ins package shape obvious
- remove migration-era compatibility import surfaces
- keep benchmark authoring examples clean and copyable
- keep E2B mechanics behind a small infrastructure boundary
- make worker/tool/runtime code simpler to test

## PR 1: Hygiene, Guardrails, and Dead Surface Inventory

Branch:

```text
codex/builtins-pr01-hygiene-guardrails
```

Goal:

Create cheap safety rails before moving code. This PR should avoid broad
behavioral refactors.

Scope:

- delete generated artifacts from `ergon_builtins`
- delete stray files such as `benchmarks/gdpeval/Untitled`
- remove obvious unused imports in worker modules
- add architecture tests that prevent the same clutter from returning
- confirm whether `cloud_passthrough.py` is imported or registered anywhere

Files to touch:

- `ergon_builtins/ergon_builtins/**/__pycache__/`
- `ergon_builtins/ergon_builtins/**/*.pyc`
- `ergon_builtins/ergon_builtins/benchmarks/gdpeval/Untitled`
- `ergon_builtins/ergon_builtins/workers/baselines/react_worker.py`
- `ergon_builtins/tests/unit/architecture/test_builtin_package_hygiene.py`
- possibly `ergon_builtins/ergon_builtins/models/cloud_passthrough.py`

Tests:

```bash
pytest ergon_builtins/tests/unit/architecture -q
pytest ergon_builtins/tests/unit/workers -q
```

Acceptance criteria:

- no `__pycache__`, `.pyc`, or `Untitled` files under
  `ergon_builtins/ergon_builtins`
- architecture test fails if generated artifacts reappear
- `react_worker.py` no longer imports unused `UUID`, `Field`, `Session`, or
  `ContextEventService`
- decision recorded for `cloud_passthrough.py`: deleted if unused, otherwise
  renamed/documented as intentional passthrough

Review risk:

- low
- mostly filesystem hygiene and import cleanup

## PR 2: Canonical Worker Package and Factory Shape

Branch:

```text
codex/builtins-pr02-workers-canonical
```

Goal:

Make worker imports and benchmark worker factories boringly consistent.

Scope:

- move `workers/baselines/react_worker.py` to `workers/react_worker.py`
- move `workers/baselines/training_stub_worker.py` to
  `workers/training_stub_worker.py`
- move `workers/baselines/toolkit.py` to `workers/toolkit.py`
- move `workers/baselines/tool_budget.py` to `workers/tool_budget.py`
- move `workers/baselines/react_prompts.py` into benchmark-local
  `prompts.py` modules where prompts are benchmark-specific
- rename benchmark `workers.py` modules to `worker_factory.py`
- make factory signatures consistent across benchmarks
- remove `shared/workers`
- remove or clearly quarantine `workers/research_rubrics/_run_skill.py`

Target structure:

```text
ergon_builtins/ergon_builtins/workers/
  __init__.py
  react_worker.py
  react_output.py
  toolkit.py
  tool_budget.py
  training_stub_worker.py

ergon_builtins/ergon_builtins/benchmarks/<slug>/
  prompts.py
  worker_factory.py
```

Factory convention:

```python
DEFAULT_WORKER_MODEL = "openai:gpt-4o-mini"

def make_<slug>_worker(
    *,
    model: str = DEFAULT_WORKER_MODEL,
    max_iterations: int = <benchmark_default>,
) -> ReActWorker:
    ...
```

ReAct worker cleanup:

- replace mutable `_tools` run state with local `tools` passed into
  `_run_agent`
- add explicit error when `toolkit` is set but `task.sandbox` is missing
- move final output extraction to `workers/react_output.py`
- add metadata showing whether final output came from structured output,
  assistant-text fallback, or missing output

Training stub cleanup:

- add deterministic config:

```python
seed: int = 0
min_turns: int = 2
max_turns: int = 3
min_tokens: int = 8
max_tokens: int = 16
```

- use a local RNG seeded by `seed` and `task.task_slug`

Tests:

```bash
pytest ergon_builtins/tests/unit/workers -q
pytest ergon_builtins/tests/unit/test_*_v2_definition.py -q
pytest ergon_builtins/tests/unit/benchmarks -q
```

Acceptance criteria:

- no source imports from `ergon_builtins.shared.workers`
- no source imports from `ergon_builtins.workers.baselines`
- benchmark worker factories live in `worker_factory.py`
- benchmark prompts live in benchmark packages
- `TrainingStubWorker` output is deterministic for the same seed and task slug
- `ReActWorker` no longer stores per-run tool lists on the worker instance

Review risk:

- medium
- many imports change, but behavior should remain intentionally equivalent
  except deterministic training stub output and clearer missing-sandbox errors

## PR 3: E2B Sandbox Infrastructure Base

Branch:

```text
codex/builtins-pr03-e2b-sandbox-runtime
```

Goal:

Replace `_manager_backed.py` with an explicit E2B runtime implementation and
shared E2B sandbox base class.

Scope:

- create `sandbox/e2b_runtime.py`
- create `sandbox/e2b_sandbox.py`
- delete `sandbox/_manager_backed.py`
- update MiniF2F, SWE-Bench, ResearchRubrics, and GDPEval sandboxes to inherit
  from `E2BSandbox`
- remove repeated `provision()` and `_bind_runtime()` implementations from
  benchmark sandboxes
- update smoke fixtures to avoid importing private built-ins runtime classes
- update stale core sandbox docs that still name `ManagerBackedSandboxRuntime`

Target runtime:

```python
class E2BSandboxRuntime:
    sandbox_id: str

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

Target base:

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

Tests:

```bash
pytest ergon_builtins/tests/unit/state/test_criteria_do_not_spawn_sandboxes.py -q
pytest ergon_builtins/tests/unit/benchmarks -q
pytest tests/fixtures/smoke_components -q
```

Acceptance criteria:

- no source imports from `ergon_builtins.sandbox._manager_backed`
- benchmark E2B sandboxes do not override `provision()` or `_bind_runtime()`
  unless a justification comment explains benchmark-specific behavior
- shell paths inside E2B `list_files()` are quoted
- built-ins no longer imports `BaseSandboxManager`
- core public sandbox docs no longer mention `ManagerBackedSandboxRuntime` as
  the concrete production implementation

Review risk:

- medium-high
- this touches runtime lifecycle, so keep behavior equivalent and rely on
  existing sandbox/reconnect tests

## PR 4: Benchmark-Local Tools and Criteria Boundaries

Branch:

```text
codex/builtins-pr04-benchmark-domains
```

Goal:

Finish the domain cleanup by moving benchmark-specific tools and criteria into
benchmark-owned packages and removing compatibility evaluator/shared surfaces.

Scope:

- split each benchmark `_tools.py` into:

```text
tools/
  __init__.py
  response_models.py
  operations.py
  tool_builder.py
```

- move MiniF2F `rules/proof_verification.py` to
  `criteria/proof_verification.py`
- move SWE-Bench `criterion.py` to `criteria/test_resolution.py`, with helper
  modules for patch extraction/grading if useful
- split ResearchRubrics judge logic into:

```text
criteria/
  judge.py
  evidence.py
  prompts.py
```

- split GDPEval staged rubric into:

```text
rubric/
  __init__.py
  aggregation.py
  stage.py
  staged_rubric.py
```

- remove `shared/criteria`, `shared/models`, and `evaluators` after imports are
  migrated
- add architecture tests for domain boundaries

Tests:

```bash
pytest ergon_builtins/tests/unit/benchmarks -q
pytest ergon_builtins/tests/unit/state -q
pytest ergon_builtins/tests/unit/test_*_v2_definition.py -q
pytest ergon_builtins/tests/unit/architecture -q
```

Acceptance criteria:

- no source imports from `ergon_builtins.shared`
- no source imports from `ergon_builtins.evaluators`
- no benchmark criteria import `ergon_core.core.persistence`
- no benchmark criteria import repositories or `get_session`
- benchmark-specific tools live under `benchmarks/<slug>/tools`
- benchmark-specific criteria live under `benchmarks/<slug>/criteria`
- existing task definition round-trip tests still pass

Review risk:

- high
- this PR has the largest move set; keep it mechanical where possible and
  avoid behavior changes beyond cleaner module boundaries

## Stack order recommendation

Preferred order:

1. PR 1: Hygiene and guardrails
2. PR 2: Worker canonicalization
3. PR 3: E2B sandbox infrastructure
4. PR 4: Benchmark tools and criteria domains

If PR 4 feels too large, split it by benchmark:

```text
PR 4a: MiniF2F tools/criteria
PR 4b: SWE-Bench tools/criteria
PR 4c: ResearchRubrics criteria/evidence
PR 4d: GDPEval rubric/tools
```

That would make a cleaner review experience, but the conceptual stack remains
the same.

## Final stack acceptance

The stack is complete when:

- `ergon_builtins` has one obvious canonical import path per concept
- generated artifacts are rejected by tests
- workers do not carry per-run mutable tool state
- training stub output is deterministic
- E2B setup lives behind `E2BSandbox` and `E2BSandboxRuntime`
- benchmark sandboxes are mostly declarative config
- benchmark tools and criteria live under benchmark packages
- built-ins no longer imports core persistence/application internals from
  benchmark criteria
- compatibility packages are deleted or explicitly quarantined as temporary

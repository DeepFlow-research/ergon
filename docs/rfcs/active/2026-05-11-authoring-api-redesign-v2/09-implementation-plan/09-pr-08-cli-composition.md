# PR 8 — CLI Composition Path

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> `superpowers:subagent-driven-development` or
> `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make `ergon experiment define <slug>` build an `Experiment` and
call `persist_definition`; make `ergon experiment run <definition-id>` call
canonical launch.

**Architecture:** The CLI is a composition convenience. It has a static
in-process slug factory dict for in-tree benchmarks and no persistence path
of its own.

**Tech Stack:** argparse CLI handlers, builtin slug factories, pytest CLI
tests.

---

## Files

**Create:**

```text
ergon_builtins/ergon_builtins/benchmarks/_registry.py
```

**Modify:**

```text
ergon_cli/ergon_cli/commands/experiment.py
ergon_cli/ergon_cli/composition/__init__.py
ergon_cli/tests/unit/test_experiment_cli.py
ergon_core/ergon_core/core/application/experiments/service.py
ergon_core/ergon_core/core/application/experiments/launch.py
```

## Current State

CLI define builds `ExperimentDefineRequest` and calls
`ExperimentService().define_benchmark_experiment(request)`. Launch uses
`ExperimentRunRequest(experiment_id=<uuid string>)`, which loads
`ExperimentRecord`.

## Target State For This PR

CLI define:

```python
factory = BUILTIN_EXPERIMENT_FACTORIES[args.benchmark_slug]
experiment = factory(args)
handle = persist_definition(experiment)
logger.info("DEFINITION_ID=%s", handle.definition_id)
```

CLI run:

```python
result = await launch_run(UUID(args.experiment_id), metadata={"created_by": "cli"})
```

The argparse positional name can remain `experiment_id` in this PR; help text
must call it a definition ID.

## Task 1: Add Builtin Factory Dict

**Files:**

- Create: `ergon_builtins/ergon_builtins/benchmarks/_registry.py`

- [ ] **Step 1: Add registry**

```python
from collections.abc import Callable
from argparse import Namespace

from ergon_core.api import Experiment
from ergon_builtins.benchmarks.minif2f.benchmark import MiniF2FBenchmark

ExperimentFactory = Callable[[Namespace], Experiment]


def _minif2f(args: Namespace) -> Experiment:
    benchmark = MiniF2FBenchmark(limit=args.limit, sample_ids=tuple(args.sample_id or ()))
    return Experiment(
        benchmark=benchmark,
        name=args.name or "minif2f-react-baseline",
        description=None,
        metadata={
            "created_by": "cli",
            "slug": args.benchmark_slug,
            "workflow": args.workflow,
            "max_questions": args.max_questions,
        },
    )


BUILTIN_EXPERIMENT_FACTORIES: dict[str, ExperimentFactory] = {
    "minif2f-react-baseline": _minif2f,
}
```

### Adding a builtin factory (pattern for PR 10a/10b/10c)

PRs 10a / 10b / 10c each add one entry to `BUILTIN_EXPERIMENT_FACTORIES`
in the same file. The pattern is:

```python
# Added in PR 10a:
from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SWEBenchVerifiedBenchmark,
)

def _swebench(args: Namespace) -> Experiment:
    benchmark = SWEBenchVerifiedBenchmark(limit=args.limit)
    return Experiment(
        benchmark=benchmark,
        name=args.name or "swebench-verified",
        description="SWE-bench Verified on object-bound API.",
        metadata={
            "created_by": "cli",
            "slug": args.benchmark_slug,
        },
    )


# Added in PR 10b:
from ergon_builtins.benchmarks.researchrubrics.benchmark import (
    ResearchRubricsBenchmark,
)

def _researchrubrics(args: Namespace) -> Experiment:
    benchmark = ResearchRubricsBenchmark(limit=args.limit)
    return Experiment(
        benchmark=benchmark,
        name=args.name or "researchrubrics",
        description="Research Rubrics with LLM judge.",
        metadata={"created_by": "cli", "slug": args.benchmark_slug},
    )


# Added in PR 10c:
from ergon_builtins.benchmarks.gdpeval.benchmark import GDPEvalBenchmark

def _gdpeval(args: Namespace) -> Experiment:
    benchmark = GDPEvalBenchmark(limit=args.limit)
    return Experiment(
        benchmark=benchmark,
        name=args.name or "gdpeval",
        description="GDPEval on object-bound API.",
        metadata={"created_by": "cli", "slug": args.benchmark_slug},
    )


# Final state of the dict after all three sub-PRs land:
BUILTIN_EXPERIMENT_FACTORIES: dict[str, ExperimentFactory] = {
    "minif2f-react-baseline": _minif2f,
    "swebench-verified": _swebench,        # PR 10a
    "researchrubrics": _researchrubrics,   # PR 10b
    "gdpeval": _gdpeval,                   # PR 10c
}
```

Each vertical PR adds one factory and one entry; the dict is the single
source of truth for `ergon define <slug>` resolution. There is **no
runtime registration hook** — adding a builtin requires editing this
file, which is the deliberate trade-off for ruling out the v1
`saved_specs` dynamic-registration path.

CLI test coverage for each new entry: `ergon_cli/tests/unit/test_experiment_cli.py`
should be updated in the corresponding vertical PR to include a
parametrized test case for the new slug.

## Task 2: Rewrite Define Handler

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/experiment.py`

- [ ] **Step 1: Replace service call**

Replace construction of `ExperimentDefineRequest` and
`define_benchmark_experiment` with:

```python
from ergon_builtins.benchmarks._registry import BUILTIN_EXPERIMENT_FACTORIES
from ergon_core.core.application.experiments.definition_writer import persist_definition


def handle_experiment_define(args: Namespace) -> int:
    _ensure_cli_logging()
    ensure_db()
    factory = BUILTIN_EXPERIMENT_FACTORIES.get(args.benchmark_slug)
    if factory is None:
        known = ", ".join(sorted(BUILTIN_EXPERIMENT_FACTORIES))
        raise ValueError(f"Unknown benchmark slug: {args.benchmark_slug}; known: {known}")
    experiment = factory(args)
    handle = persist_definition(experiment)
    logger.info("DEFINITION_ID=%s", handle.definition_id)
    logger.info("BENCHMARK=%s", handle.benchmark_type)
    return 0
```

Keep `validate_explicit_runtime_choices` only for old commands that still
call it. PR 11 deletes it if no callers remain.

## Task 3: Rewrite Run Handler

**Files:**

- Modify: `ergon_cli/ergon_cli/commands/experiment.py`

- [ ] **Step 1: Delegate to launch**

Replace the `ExperimentService().run_experiment` call with:

```python
from ergon_core.core.application.experiments.launch import launch_run


async def handle_experiment_run(args: Namespace) -> int:
    _ensure_cli_logging()
    ensure_db()
    result = await launch_run(
        UUID(args.experiment_id),
        metadata={"created_by": "cli"},
    )
    logger.info("DEFINITION_ID=%s", args.experiment_id)
    for run_id in result.run_ids:
        logger.info("RUN_ID=%s", run_id)
    return 0
```

## Task 4: Tests

**Files:**

- Modify: `ergon_cli/tests/unit/test_experiment_cli.py`

- [ ] **Step 1: Define calls persist_definition**

```python
def test_experiment_define_calls_persist_definition(monkeypatch, caplog):
    recorded = {}
    monkeypatch.setattr(
        "ergon_cli.commands.experiment.persist_definition",
        lambda experiment: recorded.setdefault("experiment", experiment)
        or DefinitionHandle(definition_id=uuid4(), benchmark_type="minif2f-react-baseline"),
    )

    result = handle_experiment_define(args_for_slug("minif2f-react-baseline"))

    assert result == 0
    assert isinstance(recorded["experiment"], Experiment)
```

- [ ] **Step 2: Run calls launch_run**

```python
@pytest.mark.asyncio
async def test_experiment_run_calls_launch_run(monkeypatch):
    called = {}
    async def fake_launch(definition_id, *, metadata):
        called["definition_id"] = definition_id
        return ExperimentRunResult(experiment_id=definition_id, run_ids=[uuid4()], workflow_definition_ids=[definition_id])
    monkeypatch.setattr("ergon_cli.commands.experiment.launch_run", fake_launch)

    assert await handle_experiment_run(Namespace(experiment_id=str(uuid4()))) == 0
    assert called["definition_id"]
```

- [ ] **Step 3: Run focused tests**

```bash
uv run pytest ergon_cli/tests/unit/test_experiment_cli.py -q
```

## Task 5: Flip XFails Landed By This PR

**Files:**

- Modify: `ergon_core/tests/unit/architecture/test_dead_path_audit.py`

PR 8 removes the last caller of `_persist_single_sample_workflow_definition`
(the v1 CLI helper that wrote to `saved_specs`) by routing CLI define
through the canonical `persist_definition`.

- [ ] **Step 1: Remove the entry from `_XFAIL_BY_SYMBOL`**

In `test_dead_path_audit.py`, delete:

```python
"_persist_single_sample_workflow_definition": "PR 8: CLI uses persist_definition",
```

(`saved_specs` itself stays xfailed — the package still exists,
unimported, until PR 11 deletes it.)

- [ ] **Step 2: Run the dead-path audit**

```bash
uv run pytest ergon_core/tests/unit/architecture/test_dead_path_audit.py -q
```

Expected: the PR 8 case PASS; remaining cases still XFAIL.

## PR Ledger

Invariant landed: CLI define/run use canonical Python API paths.

Bridge code introduced: limited builtin factory dict.

Old path still intentionally alive: `saved_specs`, old composition helpers.

Deletion gate: PR 11 deletes `saved_specs` and old define service.

Tests added or updated: CLI define/run monkeypatch tests.

Modules owned by this PR: CLI command surface and builtin slug factories.

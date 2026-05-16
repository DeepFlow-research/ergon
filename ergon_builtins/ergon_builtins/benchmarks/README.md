# Builtin Benchmarks

Each subdirectory is one benchmark.  Import from Python; **there is no
CLI authoring path** (PR 6.5 deleted `ergon experiment define` /
`ergon run <benchmark>`).  Authoring is Python-only; the CLI is for
observation (`ergon experiment show` / `ergon run status`, added in
PR 8).

## Catalogue

| Benchmark | Module | Worker factories | Default sandbox |
|---|---|---|---|
| MiniF2F | `ergon_builtins.benchmarks.minif2f` | `make_minif2f_worker` (ReAct) | `LeanSandbox` |

Adding a new benchmark = a new subdirectory containing:

- `benchmark.py` — `<Slug>Benchmark(Benchmark)` with parameterised
  `__init__(*, worker_factory=..., sandbox_factory=..., evaluator_factory=...)`
- `sandbox.py` — `<Slug>Sandbox(Sandbox)` per-benchmark
- `toolkit.py` — `<Slug>Toolkit(BaseModel)` serialisable config
- `_tools.py` — runtime tool builders (lazy-imported by `toolkit.py`)
- `workers.py` — `make_<slug>_worker()` factory (one per agentic
  strategy; bind `ReActWorker` / `CoTWorker` / etc. to this benchmark's
  toolkit + sandbox + system prompt)
- `rubric.py` + optional `criteria/` — evaluator + criteria
- `_legacy_workers.py` — only if a registry-string bridge is required
  during the v1→v2 migration (PR 11 deletes)

Then update this table in the same PR.  No CLI registry to edit; no
factory dispatch dict; no per-benchmark `experiment.py` file.

## Authoring example (MiniF2F)

```python
import asyncio
from ergon_builtins.benchmarks.minif2f import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.workers import make_minif2f_worker
from ergon_core.api import persist_benchmark
# launch_run lives in core.application.experiments.launch

async def main():
    benchmark = MiniF2FBenchmark(
        worker_factory=make_minif2f_worker,
        limit=10,
    )
    handle = persist_benchmark(
        benchmark,
        name="minif2f-react",
        # experiment="ablation-2026-05-15",   # optional grouping tag
    )
    print(f"DEFINITION_ID={handle.definition_id}")
    # Then kick the run via the dashboard or programmatic launch.

asyncio.run(main())
```

## A/B testing across strategies

The benchmark is parameterised so you can swap workers without touching
benchmark code:

```python
EXPERIMENT = "minif2f-strategy-ablation-2026-05-15"

for label, worker_factory in [
    ("react", make_minif2f_worker),
    # ("cot", make_minif2f_cot_worker),   # when CoTWorker lands
]:
    benchmark = MiniF2FBenchmark(worker_factory=worker_factory, limit=10)
    persist_benchmark(
        benchmark,
        name=f"minif2f-{label}",
        experiment=EXPERIMENT,
        metadata={"strategy": label},
    )
```

The `experiment` argument is the optional grouping tag — definitions
tagged with the same string belong to the same logical experiment.
Use `ergon experiment by-tag <tag>` (PR 8) to list all definitions
sharing a tag and see their latest run status.

## Why no CLI authoring path?

See `docs/superpowers/brainstorms/2026-05-15-kill-experiment-class.md`
for the full rationale.  Short version: every CLI authoring flag would
need to mirror a Python constructor kwarg, doubling the surface and
constraining the Python API to only what argparse can pass.  A short
Python script is checked into your repo, version-controlled, and
parameterisable — strictly better for reproducibility than `ergon run
... --worker react --limit 10`.

## Discovery via Python

```python
import ergon_builtins.benchmarks as benchmarks
import pkgutil

for _, name, ispkg in pkgutil.iter_modules(benchmarks.__path__):
    if ispkg:
        print(name)
```

Or just `ls ergon_builtins/ergon_builtins/benchmarks/`.

## Observing runs via the CLI

After persisting and launching a benchmark from Python, use the CLI to observe its state:

- `ergon run status <run-id>` — current state of one run
- `ergon run list [--status=S] [--experiment=<tag>]` — list runs, optionally filtered
- `ergon experiment show <UUID>` — full experiment detail (UUID-based)
- `ergon experiment list` — list recent experiments
- `ergon experiment tags` — list distinct experiment-tag strings
- `ergon experiment by-tag <tag>` — list definitions sharing a tag, with latest run status

The `--experiment` filter and the `tags` / `by-tag` commands read the
`BenchmarkDefinitionRecord.experiment` column, which is populated today
only via the cohort harness.  All commands are read-only.

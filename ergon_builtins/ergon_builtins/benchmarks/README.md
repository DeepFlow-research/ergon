# Builtin Benchmarks

Each subdirectory is one benchmark.  Import from Python; **there is no
CLI authoring path**.  Authoring is Python-only; the CLI is for
observation (`ergon experiment show`, `ergon sample status`, and related read
commands).

## Catalogue

| Benchmark | Module | Worker factories | Default sandbox |
|---|---|---|---|
| MiniF2F | `ergon_builtins.benchmarks.minif2f` | `make_minif2f_worker` (ReAct) | `LeanSandbox` |
| SWE-Bench Verified | `ergon_builtins.benchmarks.swebench_verified` | `make_swebench_worker` (ReAct) | `SWEBenchSandbox` |
| ResearchRubrics | `ergon_builtins.benchmarks.researchrubrics` | `make_research_worker` (ReAct) | `ResearchE2BSandbox` |
| GDPEval | `ergon_builtins.benchmarks.gdpeval` | `make_gdpeval_worker` (ReAct) | `GDPEvalSandbox` |

Adding a new benchmark = a new subdirectory containing:

- `benchmark.py` — `<Slug>Benchmark(Benchmark)` with parameterised
  `__init__(*, worker_factory=..., sandbox_factory=..., evaluator_factory=...)`
- `sandbox.py` — `<Slug>Sandbox(Sandbox)` per-benchmark
- `toolkit.py` — `<Slug>Toolkit(BaseModel)` serialisable config
- `tools/tool_builder.py` — runtime tool builders (lazy-imported by `toolkit.py`)
- `worker_factory.py` — `make_<slug>_worker()` factory (one per agentic
  strategy; bind `ReActWorker` / `CoTWorker` / etc. to this benchmark's
  toolkit + sandbox + system prompt)
- `rubric.py` + optional `criteria/` — evaluator + criteria
Then update this table in the same PR.  No core registry to edit; no
runtime dispatch dict; no per-benchmark `experiment.py` file.

## Authoring example (MiniF2F)

```python
import asyncio
from ergon_builtins.benchmarks.minif2f import MiniF2FBenchmark
from ergon_builtins.benchmarks.minif2f.worker_factory import make_minif2f_worker

async def main():
    benchmark = MiniF2FBenchmark(
        worker_factory=make_minif2f_worker,
        limit=10,
    )
    # Submit this configured benchmark through a higher-level
    # experiment/environment authoring flow.
    print(benchmark.type_slug)

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
    metadata = {"strategy": label}
    # Add benchmark plus metadata to your experiment/environment authoring flow.
```

The experiment tag groups related submissions for read models and dashboards.

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
- `ergon sample list [--status=S] [--experiment-id=<UUID>]` — list samples, optionally filtered
- `ergon experiment show <UUID>` — full experiment detail (UUID-based)
- `ergon experiment list` — list recent experiments

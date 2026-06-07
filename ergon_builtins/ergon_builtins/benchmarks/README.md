# Builtin Environments

Each subdirectory is one env.  Import from Python; **there is no
CLI authoring path**.  Authoring is Python-only; the CLI is for
observation (`ergon experiment show`, `ergon sample status`, and related read
commands).

## Catalogue

| Environment | Module | Worker factories | Default sandbox |
|---|---|---|---|
| MiniF2F | `ergon_builtins.environments.minif2f` | `make_minif2f_worker` (ReAct) | `LeanSandbox` |
| SWE-Bench Verified | `ergon_builtins.environments.swebench_verified` | `make_swebench_worker` (ReAct) | `SWEBenchSandbox` |
| ResearchRubrics | `ergon_builtins.environments.researchrubrics` | `make_research_worker` (ReAct) | `ResearchE2BSandbox` |
| GDPEval | `ergon_builtins.environments.gdpeval` | `make_gdpeval_worker` (ReAct) | `GDPEvalSandbox` |

Adding a new environment = a new subdirectory containing:

- `env.py` — `<Slug>Environment(Environment)` with parameterised
  `__init__(*, worker_factory=..., sandbox_factory=..., evaluator_factory=...)`
- `sandbox.py` — `<Slug>Sandbox(Sandbox)` per-environment
- `toolkit.py` — `<Slug>Toolkit(BaseModel)` serialisable config
- `tools/tool_builder.py` — runtime tool builders (lazy-imported by `toolkit.py`)
- `worker_factory.py` — `make_<slug>_worker()` factory (one per agentic
  strategy; bind `ReActWorker` / `CoTWorker` / etc. to this environment's
  toolkit + sandbox + system prompt)
- `rubric.py` + optional `criteria/` — evaluator + criteria
Then update this table in the same PR.  No core registry to edit; no
runtime dispatch dict; no per-environment `experiment.py` file.

## Authoring example (MiniF2F)

```python
import asyncio
from ergon_builtins.environments.minif2f import MiniF2FEnvironment
from ergon_builtins.environments.minif2f.worker_factory import make_minif2f_worker

async def main():
    env = MiniF2FEnvironment(
        worker_factory=make_minif2f_worker,
        limit=10,
    )
    # Submit this configured environment through a higher-level
    # experiment/environment authoring flow.
    print(env.name)

asyncio.run(main())
```

## A/B testing across strategies

The environment is parameterised so you can swap workers without touching
environment code:

```python
EXPERIMENT = "minif2f-strategy-ablation-2026-05-15"

for label, worker_factory in [
    ("react", make_minif2f_worker),
    # ("cot", make_minif2f_cot_worker),   # when CoTWorker lands
]:
    env = MiniF2FEnvironment(worker_factory=worker_factory, limit=10)
    metadata = {"strategy": label}
    # Add environment plus metadata to your experiment/environment authoring flow.
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
import ergon_builtins.environments as environments
import pkgutil

for _, name, ispkg in pkgutil.iter_modules(environments.__path__):
    if ispkg:
        print(name)
```

Or just `ls ergon_builtins/ergon_builtins/environments/`.

## Observing runs via the CLI

After persisting and launching a environment from Python, use the CLI to observe its state:

- `ergon run status <run-id>` — current state of one run
- `ergon sample list [--status=S] [--experiment-id=<UUID>]` — list samples, optionally filtered
- `ergon experiment show <UUID>` — full experiment detail (UUID-based)
- `ergon experiment list` — list recent experiments

# ergon_builtins

Built-in benchmarks, workers, evaluators, criteria, and rubrics that ship
with Ergon.  Split across three registry modules so each can be imported
without dragging in optional heavy deps.

## Registry modules

| File | Extra | Contents |
|------|-------|----------|
| `registry_core.py` | (always) | No optional deps. Lean workers, minif2f benchmark, stub/staged evaluators, cloud+vllm model backends. |
| `registry_data.py` | `[data]` | pandas/datasets/HF-hub-dependent components: gdpeval + researchrubrics benchmarks + their workers. |
| `registry_local_models.py` | `[local]` | Local-inference model backends (llama.cpp, local transformers). |
| `registry.py` | (always) | Aggregator that merges the above dicts lazily when their extras are importable. |

Registration is by slug.  Adding a component = add the class + one line
in the right registry module.

### `registry_core.py` (current contents)

Workers: `training-stub`, `react-v1`, `minif2f-react`, `manager-researcher`.
Benchmarks: `minif2f`.
Evaluators: `stub-rubric`, `varied-stub-rubric`, `staged-rubric`,
`minif2f-rubric`.
Sandbox managers / templates: `gdpeval`, `minif2f`.
Model backends: `vllm`, `openai`, `anthropic`, `google`.

`StubWorker` (`stub-worker`) is intentionally *unregistered* but the
class is still importable for tests.

### `registry_data.py` (current contents)

Benchmarks: `gdpeval`, `researchrubrics`, `researchrubrics-ablated`,
`researchrubrics-vanilla`.
Evaluators: `research-rubric`.
Workers: `researchrubrics-manager`, `researchrubrics-researcher`.

## Canonical demo

One command exercises manager→researcher delegation, real sandbox I/O,
`SandboxResourcePublisher`, and the `stub-rubric` evaluator:

```bash
ergon benchmark run researchrubrics --limit 1 \
    --worker researchrubrics-manager --evaluator stub-rubric
```

`stub-rubric` = `Rubric(criteria=[StubCriterion()])`.  `StubCriterion`
scores 1.0 iff: ≥1 `RunResource` exists, every resource is readable
both host-side and from inside the sandbox, and the sandbox canary
`echo $((1+1))` returns `2`.  Any failure gives a specific feedback
string — use it as a smoke signal when wiring new sandbox providers.

## Conventions

- Every component exposes a `type_slug: ClassVar[str]` matching its
  registry key.
- Workers yield `GenerationTurn`s from `execute(task, context)`; use
  the ABCs in `ergon_core.api`.
- Evaluators are typically `Rubric(criteria=[...])` composed from
  concrete `Criterion` subclasses in `evaluators/criteria/`.
- Test fixtures live under `tests/integration/` with a leading
  underscore (e.g. `_fixture_benchmark.py`) so pytest ignores them.

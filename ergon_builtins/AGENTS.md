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

## Canonical per-dataset demos

Each dataset ships a single end-to-end smoke demo: one command that
exercises manager→worker delegation, real sandbox I/O, and a
dataset-appropriate "did it actually work" evaluator.  These are the
CI gates on `feature/*` branches (`.github/workflows/e2e-benchmarks.yml`).

**researchrubrics** (Exa + report drafting):

```bash
ergon benchmark run researchrubrics --limit 1 \
    --worker researchrubrics-manager --evaluator stub-rubric
```

`stub-rubric` = `Rubric(criteria=[StubCriterion()])`.  `StubCriterion`
scores 1.0 iff: ≥1 `RunResource` exists, every resource is readable
both host-side and from inside the sandbox, and the sandbox canary
`echo $((1+1))` returns `2`.

**minif2f-smoke** (Lean 4 theorem proving):

```bash
ergon benchmark run minif2f-smoke --limit 1 \
    --worker minif2f-manager --evaluator minif2f-rubric
```

Same manager→prover delegation pattern (see
`ergon_builtins/workers/minif2f/`), but the "canary" is a real Lean 4
compile.  `minif2f-rubric` wraps `ProofVerificationCriterion`: it reads
the agent's `final_solution.lean`, writes it into the sandbox at
`src/verify.lean`, and runs `lake env lean` — exit 0 ⇒ score 1.0.
The smoke benchmark ships a single trivial theorem
(`theorem smoke_add : 1 + 1 = 2 := by decide`) so the demo is
deterministic regardless of LLM choice.

### Adding a new dataset

Every new dataset (e.g. `swebench-verified`) must ship the same set of
pieces before merging:

1. **Benchmark**: a `…Benchmark` subclass registered in
   `registry_core.py` / `registry_data.py`.  For the CI smoke, either a
   dedicated `…-smoke` subclass with one canned deterministic task or a
   `--limit 1` slice of the real benchmark — whichever guarantees the
   demo passes without LLM luck.
2. **Manager + sub-worker**: a `…ManagerWorker` that spawns a
   `…Worker` sub-agent via `add_subtask`, and a matching composition
   case in `ergon_cli/ergon_cli/composition/__init__.py` that binds both
   workers.
3. **Sandbox manager**: an entry in `SANDBOX_MANAGERS` (and
   `SANDBOX_TEMPLATES` if a prebuilt image is needed) keyed by the
   benchmark's `type_slug`.
4. **Evaluator**: a rubric that asserts the dataset's real success
   signal — for researchrubrics that's "resources exist and the sandbox
   canary runs"; for minif2f it's "the Lean compiler accepts the proof";
   for swebench-verified it will be "the task's test suite passes".
5. **E2E test**: a `TestXxxDemo` class in
   `tests/e2e/test_benchmarks_stubbed.py` asserting the CLI completes,
   executions reach terminal-completed, and every evaluation scores 1.0.
6. **CI job**: a matching `e2e-xxx-demo` job in
   `.github/workflows/e2e-benchmarks.yml`, gated on
   `feature/*` + `workflow_dispatch`, with real E2B + OpenAI secrets.

## Conventions

- Every component exposes a `type_slug: ClassVar[str]` matching its
  registry key.
- Workers yield `GenerationTurn`s from `execute(task, context)`; use
  the ABCs in `ergon_core.api`.
- Evaluators are typically `Rubric(criteria=[...])` composed from
  concrete `Criterion` subclasses in `evaluators/criteria/`.
- Test fixtures live under `tests/integration/` with a leading
  underscore (e.g. `_fixture_benchmark.py`) so pytest ignores them.

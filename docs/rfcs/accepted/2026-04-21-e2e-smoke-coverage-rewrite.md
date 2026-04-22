---
status: active
opened: 2026-04-21
author: deepflow-research
architecture_refs:
  - docs/architecture/06_builtins.md
  - docs/architecture/07_testing.md
  - docs/architecture/05_dashboard.md
  - docs/architecture/01_public_api.md
supersedes:
  - docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md
  - docs/rfcs/active/2026-04-18-test-harness-endpoints.md
superseded_by: null
---

# RFC: End-to-end smoke coverage rewrite — canonical per-env smoke with Playwright + screenshots

## Problem

The current end-to-end test tier (`tests/e2e/`) is being retired under
`docs/rfcs/active/2026-04-18-testing-posture-reset.md` PR 4 for a clean-slate
rebuild. This RFC defines what fills that space.

Three structural problems with the previous tier:

1. **Ad-hoc stub workers, no shared shape.** Three stub workers exist
   (`stub-worker`, `smoke-test-worker`, `researchrubrics-stub`) — each
   implements its own subgraph shape (or none). Graph propagation regressions
   surface differently per benchmark or not at all. No invariant like "every
   benchmark proves diamond + line + singleton propagation works."
2. **No Playwright / dashboard coverage.** Existing e2e tests assert directly
   on Postgres rows via `sqlmodel.Session(get_engine())`. The dashboard is
   never exercised. A regression in dashboard delta streaming, cohort
   rendering, or run graph visualization lands silently until a human
   notices.
3. **No on-PR diagnostic artifacts.** When an e2e test fails, the only
   evidence is a CI log. No screenshots, no traces, no way to see what the
   dashboard showed at the moment of failure without reproducing locally.

Additionally, two in-flight RFCs cover adjacent parts of the problem but
scoped too narrowly to land independently:

- `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` proposes a
  `FixedDelegationStubWorker` with a single fan-out/fan-in subgraph
  (manager → subtask_a/b/c → join). Good shape, but only one topology per
  run; doesn't cover line or singleton invariants; lives in the integration
  tier only (no real sandbox, no Playwright).
- `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` proposes
  `/api/test/*` read/write endpoints gated on `ENABLE_TEST_HARNESS=1`.
  Necessary for Playwright backend assertion, but written as a standalone
  dependency with no concrete smoke tier consuming it.

Both are strictly subsumed by the scope of this RFC: the canonical smoke
worker grows from one topology to three + env-specific subworker; the
test-harness endpoints become a named deliverable of the same RFC that
defines the Playwright layer that uses them. Landing them as separate PRs
would be redundant coordination overhead.

## Proposal

One canonical smoke per environment (`researchrubrics`, `minif2f`,
`swebench-verified`), built on:

- **A shared parent worker** (`CanonicalSmokeWorker`) that always spawns the
  same graph shape: a 4-node diamond, a 3-node line, and 2 independent
  singletons — 9 subtasks total — via the `add_subtask` tool. The shape is
  hardcoded; determinism is the point.
- **A per-env leaf worker** (`{Env}SmokeSubworker`) that writes a
  deterministic env-specific file and runs a bash probe against the real
  sandbox to prove the container is set up correctly. Zero LLM calls.
- **A shared-base criterion** (`SmokeCriterionBase`) that enforces the
  structural contract (9 resources present, graph shape matches expected)
  + a per-env subclass (`{Env}SmokeCriterion`) that adds content assertions
  (Lean output parses, markdown headers exist, Python AST valid).
- **Benchmark composition bindings** that wire `smoke-leaf` binding-key →
  env-specific subworker slug. Parent worker resolves the leaf at runtime
  via the existing composition layer.
- **A Python-pytest test driver** per env at `tests/e2e/test_{env}_smoke.py`
  that runs the benchmark, asserts Postgres record-log directly, then
  invokes Playwright as a subprocess.
- **A Playwright spec** per env at
  `ergon-dashboard/tests/e2e/{env}.smoke.spec.ts` that asserts the dashboard
  renders the expected run state, captures screenshots on pass and fail, and
  uses the `/api/test/read/run/{id}/state` harness endpoint for stable
  backend assertions.
- **A `/api/test/*` harness router** (absorbed from the superseded
  `test-harness-endpoints` RFC) providing a narrow read DTO and secret-gated
  write endpoints for Playwright.
- **A screenshot delivery mechanism** that pushes captures to a dedicated
  git ref (`screenshots/pr-{N}`) and posts a PR comment with inline images
  on pass or fail. A cleanup workflow deletes the ref when the PR closes.
- **A parallel CI matrix** (`.github/workflows/e2e-benchmarks.yml`) running
  the three env smokes concurrently with a 5-minute hard budget per job,
  triggered on every PR.

Total production-code registrations: 1 shared parent worker + 3 leaf
workers + 3 criteria = 7 registry entries. Total test files: 3 Python +
3 TypeScript. The pattern extends to future benchmarks at a cost of one
`Benchmark`, one `SmokeSubworker` subclass, one `SmokeCriterion` subclass,
and one `test_{env}_smoke.py` + Playwright spec pair.

## Supersession

This RFC subsumes two in-flight RFCs. On merge:

| Superseded RFC | How it is absorbed |
|---|---|
| `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` | Canonical smoke worker pattern grows from single fan-out/fan-in shape to three-topology shape. Close as stale on this RFC's first implementation PR landing. `FixedDelegationStubWorker` class is not built; `CanonicalSmokeWorker` in this RFC replaces its intended role. |
| `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` | `/api/test/*` router, DTOs, `ENABLE_TEST_HARNESS` + `TEST_HARNESS_SECRET` gates, and `BackendHarnessClient` TypeScript helper are absorbed verbatim into §4 of this RFC. Unit-test scaffolding from the superseded RFC is preserved; the implementation file paths are unchanged. Close as stale when the harness lands as part of this RFC's PR 1. |

Both superseded RFCs should be moved `active/` → `rejected/` on this RFC's
first implementation PR landing, with a one-line note citing this RFC as
the canonical replacement. They do not move to `accepted/` because neither
landed as a standalone change; they were absorbed.

## Architecture overview

### Component topology

```
                       ┌──────────────────────────┐
                       │   CanonicalSmokeWorker   │
                       │  (shared, parameterless) │
                       │  slug: canonical-smoke   │
                       │                          │
                       │  on_start:               │
                       │    spawn diamond (4)     │
                       │    spawn line    (3)     │
                       │    spawn singleton(2)    │
                       │    wait_all(9)           │
                       └────────────┬─────────────┘
                                    │ add_subtask(worker="smoke-leaf", …)
                                    │ resolves via composition binding
                                    ▼
                       ┌──────────────────────────┐
                       │  SmokeSubworker Protocol │
                       │  .work(node_id, sandbox) │
                       │  → SubworkerResult       │
                       └────────┬───┬───┬─────────┘
                                │   │   │
                ┌───────────────┘   │   └──────────────┐
                ▼                   ▼                  ▼
    ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
    │ MiniF2FSmoke   │   │ ResearchSmoke  │   │ SweBenchSmoke  │
    │   Subworker    │   │  Subworker     │   │   Subworker    │
    │                │   │                │   │                │
    │ writes .lean   │   │ writes .md     │   │ writes .py     │
    │ probes lean    │   │ probes wc -l   │   │ probes pytest  │
    │                │   │                │   │    --collect   │
    └────────────────┘   └────────────────┘   └────────────────┘
            │                   │                     │
            └────── verified by per-env criterion ────┘
                                │
                                ▼
                       ┌──────────────────────────┐
                       │   SmokeCriterionBase     │
                       │   (shared abstract)      │
                       │                          │
                       │ _assert_graph_shape(ctx) │
                       │ _assert_9_resources(ctx) │
                       │ await _verify_env(ctx)   │ abstract
                       └────────┬───┬───┬─────────┘
                                │   │   │
                ┌───────────────┘   │   └──────────────┐
                ▼                   ▼                  ▼
    ┌────────────────┐   ┌────────────────┐   ┌────────────────┐
    │ MiniF2FSmoke   │   │ ResearchSmoke  │   │ SweBenchSmoke  │
    │   Criterion    │   │   Criterion    │   │   Criterion    │
    │                │   │                │   │                │
    │ asserts .lean  │   │ asserts .md    │   │ asserts .py    │
    │ output parses  │   │ has # header + │   │ AST parses;    │
    │ (lean --check) │   │ wc-l is digit  │   │ pytest collect │
    │                │   │                │   │ succeeded      │
    └────────────────┘   └────────────────┘   └────────────────┘
```

### Test driver flow (per env, per run)

```
CI job (e2e-benchmarks.yml, matrix: [researchrubrics, minif2f, swebench-verified])
  │
  ├─ docker-compose.ci.yml up   (postgres + inngest + api, cached images)
  │    env:
  │      ENABLE_TEST_HARNESS=1
  │      TEST_HARNESS_SECRET=ci-secret
  │
  ├─ pnpm --dir ergon-dashboard build  (Next.js production build)
  ├─ pnpm --dir ergon-dashboard start &  (serves on :3000 in background)
  │
  └─ uv run pytest tests/e2e/test_{env}_smoke.py -v --timeout=270
       │
       ├─ [phase 1] Python driver invokes the CLI
       │    run_id = run_benchmark(
       │        slug="{env}",
       │        worker="canonical-smoke",
       │        evaluator="{env}-smoke-rubric",
       │        cohort=f"ci-smoke-{env}-{run_timestamp}",
       │    )
       │
       ├─ [phase 2] Wait for terminal
       │    wait_for_terminal(run_id, timeout_seconds=180)
       │    # polls /runs/{run_id} every 2s until status ∈ {completed, failed, cancelled}
       │
       ├─ [phase 3] Postgres record-log assertions (Python, direct DB)
       │    with Session(get_engine()) as s:
       │      # Graph structure
       │      nodes = s.exec(select(RunGraphNode).where(…run_id…)).all()
       │      assert len(nodes) == 10  # 1 root + 9 subtasks
       │      assert sorted(n.task_key for n in nodes if n.level > 0) == EXPECTED_NODE_KEYS
       │      assert all(n.status == TaskStatus.COMPLETED for n in nodes)
       │      # Mutation log (ordered)
       │      muts = s.exec(select(RunGraphMutation).where(…).order_by(sequence)).all()
       │      assert any(m.mutation_type == "add_subtask" and m.target_id == d_root_id for m in muts)
       │      # ... (assert diamond, line, singleton mutations in expected order)
       │      # Resource publication
       │      resources = s.exec(select(RunResource).where(…)).all()
       │      assert len(resources) == 9  # one per subtask
       │      assert all(r.content_hash for r in resources)  # non-empty
       │      # Evaluation
       │      evals = s.exec(select(RunTaskEvaluation).where(…)).all()
       │      assert len(evals) == 1 and evals[0].score == 1.0
       │
       ├─ [phase 4] Playwright subprocess (always runs — even if phase 3 failed)
       │    subprocess.run(
       │        ["pnpm", "--dir", "ergon-dashboard",
       │         "exec", "playwright", "test",
       │         f"tests/e2e/{env}.smoke.spec.ts",
       │         "--project=chromium"],
       │        env={
       │            "RUN_ID": run_id,
       │            "SMOKE_ENV": "{env}",
       │            "SCREENSHOT_DIR": f"/tmp/playwright/{env}",
       │            "PLAYWRIGHT_LIVE": "1",
       │            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
       │            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
       │            "TEST_HARNESS_SECRET": "ci-secret",
       │            **os.environ,
       │        },
       │    )
       │
       │    # Playwright spec does:
       │    #   1. Fetch state via BackendHarnessClient.getRunState(RUN_ID)
       │    #   2. Navigate to /run/{RUN_ID}
       │    #   3. Assert 9 task-node elements render with status=completed
       │    #   4. Navigate to cohort index; assert this run's cohort appears
       │    #   5. Capture 3 screenshots:
       │    #        - full page at /run/{RUN_ID}
       │    #        - graph canvas panel
       │    #        - cohort index page
       │    #   Screenshots land in ${SCREENSHOT_DIR}/*.png regardless of test outcome
       │
       └─ [phase 5] Screenshot upload (pytest finalizer, always runs)
            ├─ git fetch origin screenshots/pr-{PR_NUMBER} || init_empty_branch
            ├─ copy /tmp/playwright/{env}/*.png → screenshots/pr-{PR_NUMBER}:{env}/
            ├─ git commit -m "ci: e2e screenshots pr-{N} env={env} job={run_id}"
            ├─ git push origin screenshots/pr-{PR_NUMBER}
            └─ POST PR comment (gh pr comment) with markdown:
                ## E2E smoke — {env}
                Run ID: {run_id} — status: {PASS|FAIL}

                ![dashboard full page](https://raw.githubusercontent.com/DeepFlow-research/ergon/screenshots/pr-{N}/{env}/dashboard-full.png)
                ![graph canvas](https://raw.githubusercontent.com/DeepFlow-research/ergon/screenshots/pr-{N}/{env}/graph.png)
                ![cohort index](https://raw.githubusercontent.com/DeepFlow-research/ergon/screenshots/pr-{N}/{env}/cohort.png)
```

Python pytest owns CI pass/fail. Playwright contributes one of the assertion
layers; its failure propagates through the subprocess return code. Screenshot
upload is a pytest finalizer so it runs on both paths.

## Graph topology — the hardcoded contract

Every canonical smoke run produces exactly this graph, regardless of env:

### Subtasks (9 total, plus 1 root node)

**Diamond** (4 nodes, fan-out + fan-in):

```
       d_root
       /    \
      v      v
   d_left  d_right
       \    /
        v  v
       d_join
```

- `d_root` — depends on nothing (root of diamond)
- `d_left` — depends on `d_root`
- `d_right` — depends on `d_root`
- `d_join` — depends on `d_left` and `d_right`

**Line** (3 nodes, sequential cascade):

```
l_1 → l_2 → l_3
```

- `l_1` — depends on nothing
- `l_2` — depends on `l_1`
- `l_3` — depends on `l_2`

**Singletons** (2 independent nodes):

```
s_a     s_b
```

- `s_a` — depends on nothing
- `s_b` — depends on nothing

### What each shape proves

| Shape | Invariant verified |
|---|---|
| Diamond | Fan-out works (`d_left` + `d_right` run in parallel after `d_root`); fan-in works (`d_join` waits for both); graph toolkit correctly tracks two-parent dependencies |
| Line | Sequential cascade works; each node waits for its single predecessor; no premature parallelism |
| Singletons | Multiple terminal leaves can coexist in one run; parent `wait_all` terminates only when both resolve; graph completion logic handles multi-terminal runs |

Plus, across all three shapes:

- The `add_subtask` tool works from within a worker (`CanonicalSmokeWorker` calls it 9 times)
- `wait_all` on a heterogeneous list works
- Subtasks run concurrently where dependencies allow
- All 9 subtasks ultimately transition to `COMPLETED`
- The parent worker itself transitions to `COMPLETED` after all subtasks finish
- 9 `RunResource` rows land with non-empty content hashes (one per subtask)
- 1 `RunTaskEvaluation` row lands with `score=1.0`

### Expected node-key list (used in assertions)

Python constant shared between the parent worker, criterion, Playwright spec,
and pytest tests:

```python
# ergon_builtins/workers/stubs/canonical_smoke_worker.py
EXPECTED_SUBTASK_KEYS: tuple[str, ...] = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)
```

## Type / interface definitions

### `SmokeSubworker` Protocol

```python
# ergon_builtins/workers/stubs/smoke_subworker.py

from typing import Protocol, runtime_checkable
from dataclasses import dataclass

from ergon_core.core.providers.sandbox.manager import AsyncSandbox


@dataclass(frozen=True)
class SubworkerResult:
    """What the parent worker reads off each subtask's turn."""
    file_path: str           # path inside the sandbox
    probe_stdout: str        # non-empty stdout of the bash probe
    probe_exit_code: int     # 0 on success


@runtime_checkable
class SmokeSubworker(Protocol):
    """The pluggable env-specific leaf. One implementation per env."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        """Write a deterministic file + run a bash probe. Return both.

        MUST NOT call an LLM. MUST NOT make network calls. MUST complete
        in under 20 seconds under normal sandbox conditions.
        """
        ...
```

### `CanonicalSmokeWorker`

```python
# ergon_builtins/workers/stubs/canonical_smoke_worker.py

class CanonicalSmokeWorker(Worker):
    """Shared parent worker for every env's canonical smoke.

    Topology is hardcoded: 4-node diamond + 3-node line + 2 singletons.
    Subtask work is env-specific via the composition binding for `smoke-leaf`.

    Invariants this worker proves end-to-end:
      - add_subtask creates exactly the subgraph declared
      - fan-out parallelism works (diamond two branches, two singletons)
      - fan-in waits on all parents (d_join after d_left AND d_right)
      - line cascade is strictly sequential
      - wait_all terminates iff all 9 subtasks are COMPLETED
    """

    async def execute(self, ctx: WorkerContext) -> WorkerResult:
        # Diamond
        d_root = await ctx.add_subtask(
            task_key="d_root",
            worker="smoke-leaf",
            depends_on=[],
        )
        d_left = await ctx.add_subtask(
            task_key="d_left",
            worker="smoke-leaf",
            depends_on=[d_root],
        )
        d_right = await ctx.add_subtask(
            task_key="d_right",
            worker="smoke-leaf",
            depends_on=[d_root],
        )
        d_join = await ctx.add_subtask(
            task_key="d_join",
            worker="smoke-leaf",
            depends_on=[d_left, d_right],
        )
        # Line
        l_1 = await ctx.add_subtask(
            task_key="l_1", worker="smoke-leaf", depends_on=[]
        )
        l_2 = await ctx.add_subtask(
            task_key="l_2", worker="smoke-leaf", depends_on=[l_1]
        )
        l_3 = await ctx.add_subtask(
            task_key="l_3", worker="smoke-leaf", depends_on=[l_2]
        )
        # Singletons
        s_a = await ctx.add_subtask(
            task_key="s_a", worker="smoke-leaf", depends_on=[]
        )
        s_b = await ctx.add_subtask(
            task_key="s_b", worker="smoke-leaf", depends_on=[]
        )

        results = await ctx.wait_all(
            [d_root, d_left, d_right, d_join, l_1, l_2, l_3, s_a, s_b]
        )

        # The parent emits a summary turn for dashboard visibility.
        summary = "\n".join(f"{r.task_key}: {r.status}" for r in results)
        await ctx.emit_turn(text=summary)

        return WorkerResult(success=all(r.status == TaskStatus.COMPLETED for r in results))
```

### Leaf workers (one per env, each is a thin `Worker` that wraps its `SmokeSubworker`)

Each env's leaf is a Worker subclass whose `execute()` delegates to the env's
`SmokeSubworker.work()`, then publishes a `RunResource` with the file + probe
output. The Worker class is what gets registered in `WORKERS`; the Protocol
implementation is what the Worker holds.

```python
# ergon_builtins/workers/stubs/base_smoke_leaf.py

class BaseSmokeLeafWorker(Worker):
    """Shared glue between any `SmokeSubworker` and the publisher pipeline.

    Subclasses set `subworker_cls: type[SmokeSubworker]`. The runtime instance
    is constructed per-execute so it can access the env-specific sandbox.
    """

    subworker_cls: ClassVar[type[SmokeSubworker]]

    async def execute(self, ctx: WorkerContext) -> WorkerResult:
        sandbox = await ctx.acquire_sandbox()
        subworker = self.subworker_cls()
        result = await subworker.work(node_id=ctx.task_key, sandbox=sandbox)

        # Publish as RunResource so the criterion can read it.
        await ctx.publish_resource(
            kind=RunResourceKind.ARTIFACT,
            path=result.file_path,
            metadata={
                "probe_stdout": result.probe_stdout,
                "probe_exit_code": result.probe_exit_code,
            },
        )
        return WorkerResult(success=result.probe_exit_code == 0)
```

Concrete per-env leaf workers:

```python
# ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py

class ResearchRubricsSmokeSubworker:
    """Writes a markdown report + runs `wc -l` against it."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = f"# Report {node_id}\n\nFinding: canonical smoke artifact.\n"
        path = f"/tmp/{node_id}.md"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"wc -l {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class ResearchRubricsSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = ResearchRubricsSmokeSubworker


# ergon_builtins/benchmarks/minif2f/smoke_subworker.py

class MiniF2FSmokeSubworker:
    """Writes a trivial Lean proof + runs `lean --check`."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = (
            f"-- canonical smoke proof for {node_id}\n"
            "theorem smoke_trivial : 1 + 1 = 2 := by norm_num\n"
        )
        path = f"/tmp/{node_id}.lean"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"lean --check {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class MiniF2FSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = MiniF2FSmokeSubworker


# ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py

class SweBenchSmokeSubworker:
    """Writes a no-op Python file + runs pytest --collect-only."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        content = (
            f"# canonical smoke artifact {node_id}\n"
            "def test_smoke_noop() -> None:\n"
            "    assert 1 + 1 == 2\n"
        )
        path = f"/tmp/fix_{node_id}.py"
        await sandbox.files.write(path, content)
        probe = await sandbox.commands.run(f"pytest --collect-only {path}")
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout,
            probe_exit_code=probe.exit_code,
        )


class SweBenchSmokeLeafWorker(BaseSmokeLeafWorker):
    subworker_cls = SweBenchSmokeSubworker
```

### `SmokeCriterionBase` + env subclasses

```python
# ergon_builtins/evaluators/criteria/smoke_criterion.py

class SmokeCriterionBase(Criterion):
    """Shared canonical smoke criterion: structural checks + delegate to env content.

    Subclasses override _verify_env_content() for env-specific assertions.
    Structural checks are shared: 9 resources, expected node keys, probe
    exit codes all 0.
    """

    async def evaluate(self, ctx: CriterionContext) -> Score:
        try:
            self._assert_graph_shape(ctx)
            self._assert_resources_present(ctx)
            self._assert_probes_succeeded(ctx)
            await self._verify_env_content(ctx)
        except AssertionError as e:
            return Score(value=0.0, reason=f"smoke criterion failed: {e}")
        return Score(value=1.0, reason="canonical smoke passed")

    def _assert_graph_shape(self, ctx: CriterionContext) -> None:
        actual = {n.task_key for n in ctx.graph_nodes if n.level > 0}
        expected = set(EXPECTED_SUBTASK_KEYS)
        assert actual == expected, f"graph shape mismatch: {actual} != {expected}"

    def _assert_resources_present(self, ctx: CriterionContext) -> None:
        resources = list(ctx.resources.all())
        assert len(resources) == 9, f"expected 9 resources, got {len(resources)}"
        for r in resources:
            assert r.content_hash, f"resource {r.id} has empty content hash"

    def _assert_probes_succeeded(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            exit_code = r.metadata.get("probe_exit_code")
            assert exit_code == 0, f"probe for {r.task_key} exited {exit_code}"

    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        """Override in env subclass."""
        raise NotImplementedError
```

Env-specific subclasses:

```python
class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert text.startswith(f"# Report {r.task_key}"), (
                f"{r.task_key}: missing expected markdown header"
            )
            wc_output = r.metadata["probe_stdout"].strip()
            assert wc_output.split()[0].isdigit(), (
                f"{r.task_key}: wc -l probe did not return a number"
            )


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert "theorem smoke_trivial" in text, (
                f"{r.task_key}: missing Lean theorem declaration"
            )
            # lean --check outputs nothing on success; stdout should be empty
            # but the probe ran successfully (exit_code == 0) — that's enough.


class SweBenchSmokeCriterion(SmokeCriterionBase):
    async def _verify_env_content(self, ctx: CriterionContext) -> None:
        for r in ctx.resources.all():
            text = r.content.decode("utf-8")
            assert "def test_smoke_noop" in text, (
                f"{r.task_key}: missing pytest function"
            )
            collect_output = r.metadata["probe_stdout"]
            assert "test_smoke_noop" in collect_output, (
                f"{r.task_key}: pytest did not collect the test"
            )
```

### Registry entries

```python
# ergon_builtins/ergon_builtins/registry_core.py

WORKERS: dict[str, type[Worker]] = {
    # … existing entries …
    "canonical-smoke": CanonicalSmokeWorker,
    "researchrubrics-smoke-leaf": ResearchRubricsSmokeLeafWorker,
    "minif2f-smoke-leaf": MiniF2FSmokeLeafWorker,
    "swebench-smoke-leaf": SweBenchSmokeLeafWorker,
}

EVALUATORS: dict[str, type[Evaluator]] = {
    # … existing entries …
    "researchrubrics-smoke-rubric": ResearchRubricsSmokeCriterion,
    "minif2f-smoke-rubric": MiniF2FSmokeCriterion,
    "swebench-smoke-rubric": SweBenchSmokeCriterion,
}
```

### Composition bindings (one per env)

```python
# ergon_cli/ergon_cli/composition/__init__.py

BENCHMARK_COMPOSITIONS = {
    # … existing entries …
    "researchrubrics": Composition(
        bindings={"smoke-leaf": "researchrubrics-smoke-leaf", "researcher": "react-v1"},
    ),
    "minif2f": Composition(
        bindings={"smoke-leaf": "minif2f-smoke-leaf"},
    ),
    "swebench-verified": Composition(
        bindings={"smoke-leaf": "swebench-smoke-leaf"},
    ),
}
```

### Test-harness endpoints (absorbed from superseded RFC)

Full implementation specification carries over unchanged from
`docs/rfcs/active/2026-04-18-test-harness-endpoints.md` §4 ("Type / interface
definitions") and §5 ("Full implementation"). See that RFC for the complete
source of `test_harness.py`, DTOs, and `BackendHarnessClient` TypeScript
helper. Summary of what lands with this RFC:

- `ergon_core/core/api/test_harness.py` — FastAPI `APIRouter` with prefix
  `/api/test`:
  - `GET /api/test/read/run/{run_id}/state` → `TestRunStateDto` (narrow,
    stable, additive-only schema)
  - `POST /api/test/write/run/seed` → insert a fixture `RunRecord` tagged
    `_test_seeded=true`, requires `X-Test-Secret` header
  - `POST /api/test/write/reset` → purge test-seeded rows, requires
    `X-Test-Secret` header
- `ergon_core/core/api/app.py` — conditional `include_router` gated on
  `os.getenv("ENABLE_TEST_HARNESS") == "1"`
- `ergon-dashboard/tests/helpers/testHarnessClient.ts` —
  `BackendHarnessClient` TypeScript class

Gate semantics:

- Router mount: only when `ENABLE_TEST_HARNESS=1` at startup. Absent = 404 on
  every `/api/test/*` route.
- Write endpoints: require `X-Test-Secret` header matching
  `TEST_HARNESS_SECRET` env var. Missing secret env var = 500 (distinct from
  401 "wrong secret") so misconfiguration is distinguishable from auth
  failure.
- Read endpoint: no secret (intentional — reveals only run state already
  visible via the API port to anyone on the network).

CI wiring: `docker-compose.ci.yml` api service sets both vars
(`ENABLE_TEST_HARNESS=1`, `TEST_HARNESS_SECRET=ci-secret`) inline. No
separate secrets management required — secret value is not privileged in the
CI context.

## Test driver shape (concrete code)

### Python pytest per env

```python
# tests/e2e/test_researchrubrics_smoke.py  (one such file per env)

"""End-to-end canonical smoke for the researchrubrics benchmark.

Runs the full pipeline via the CLI, asserts Postgres record-log directly,
invokes Playwright as a subprocess for dashboard assertion + screenshots.

Requires: docker-compose.ci.yml stack, ENABLE_TEST_HARNESS=1, dashboard
prod-build serving on :3000.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlmodel import Session, select

from ergon_core.core.persistence.shared.db import get_engine
from ergon_core.core.persistence.graph.models import RunGraphMutation, RunGraphNode
from ergon_core.core.persistence.telemetry.models import (
    RunRecord,
    RunResource,
    RunTaskEvaluation,
)
from ergon_core.core.persistence.shared.enums import RunStatus, TaskStatus
from tests.e2e.conftest import run_benchmark, wait_for_terminal

ENV = "researchrubrics"
EXPECTED_SUBTASK_KEYS = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)


@pytest.fixture(scope="module")
def screenshot_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    d = tmp_path_factory.mktemp(f"playwright-{ENV}")
    return d


def test_canonical_smoke_passes(screenshot_dir: Path) -> None:
    # Phase 1: drive the benchmark via the CLI
    run_id = run_benchmark(
        slug=ENV,
        worker="canonical-smoke",
        evaluator=f"{ENV}-smoke-rubric",
        cohort=f"ci-smoke-{ENV}-{int(time.time())}",
    )

    # Phase 2: wait for terminal
    wait_for_terminal(run_id, timeout_seconds=180)

    # Phase 3: Postgres assertions (always run before Playwright)
    with Session(get_engine()) as s:
        run = s.exec(select(RunRecord).where(RunRecord.id == run_id)).one()
        assert run.status == RunStatus.COMPLETED, f"run status: {run.status}"

        nodes = s.exec(select(RunGraphNode).where(RunGraphNode.run_id == run_id)).all()
        subtask_keys = sorted(n.task_key for n in nodes if n.level > 0)
        assert subtask_keys == sorted(EXPECTED_SUBTASK_KEYS), subtask_keys

        for n in nodes:
            assert n.status == TaskStatus.COMPLETED, f"{n.task_key}: {n.status}"

        resources = s.exec(select(RunResource).where(RunResource.run_id == run_id)).all()
        assert len(resources) == 9, len(resources)
        for r in resources:
            assert r.content_hash, f"{r.task_key}: empty hash"

        evals = s.exec(
            select(RunTaskEvaluation).where(RunTaskEvaluation.run_id == run_id)
        ).all()
        assert len(evals) == 1 and evals[0].score == 1.0, evals

    # Phase 4: Playwright subprocess (runs on phase-3 success OR failure)
    #   Playwright writes screenshots regardless of assertion outcome.
    result = subprocess.run(
        [
            "pnpm", "--dir", "ergon-dashboard", "exec",
            "playwright", "test",
            f"tests/e2e/{ENV}.smoke.spec.ts",
            "--project=chromium",
        ],
        env={
            **os.environ,
            "RUN_ID": str(run_id),
            "SMOKE_ENV": ENV,
            "SCREENSHOT_DIR": str(screenshot_dir),
            "PLAYWRIGHT_LIVE": "1",
            "PLAYWRIGHT_BASE_URL": "http://127.0.0.1:3000",
            "ERGON_API_BASE_URL": "http://127.0.0.1:9000",
            "TEST_HARNESS_SECRET": "ci-secret",
        },
        capture_output=True,
        text=True,
        timeout=120,
    )

    # Phase 5 (screenshot upload) runs in the conftest finalizer regardless.
    # Playwright failure is an assertion failure for this test.
    assert result.returncode == 0, (
        f"Playwright failed\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    )
```

### `tests/e2e/conftest.py` (finalizer for screenshot upload)

```python
# tests/e2e/conftest.py

"""Shared fixtures for the e2e tier.

Key responsibility: screenshot_upload_finalizer — runs after every test (pass
or fail), pushes ${SCREENSHOT_DIR} contents to the screenshots/pr-{N} ref
and posts a PR comment with inline images.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from uuid import UUID

import pytest


def run_benchmark(
    slug: str, worker: str, evaluator: str, cohort: str
) -> UUID:
    """Run a benchmark via the CLI. Returns the run_id."""
    result = subprocess.run(
        [
            "ergon", "benchmark", "run", slug,
            "--worker", worker,
            "--evaluator", evaluator,
            "--cohort", cohort,
            "--limit", "1",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    result.check_returncode()
    # CLI emits the run_id on its last line
    run_id_line = result.stdout.strip().splitlines()[-1]
    return UUID(run_id_line)


def wait_for_terminal(run_id: UUID, timeout_seconds: int) -> None:
    """Poll /runs/{run_id} every 2s until the run reaches a terminal status."""
    import time
    import httpx

    deadline = time.time() + timeout_seconds
    api = os.environ.get("ERGON_API_BASE_URL", "http://127.0.0.1:9000")
    while time.time() < deadline:
        r = httpx.get(f"{api}/runs/{run_id}", timeout=5)
        if r.status_code == 200:
            status = r.json()["status"]
            if status in {"completed", "failed", "cancelled"}:
                return
        time.sleep(2)
    raise TimeoutError(f"run {run_id} did not reach terminal in {timeout_seconds}s")


@pytest.fixture(autouse=True)
def screenshot_upload_finalizer(
    request: pytest.FixtureRequest,
    screenshot_dir: Path,
) -> None:
    """Upload screenshots + post PR comment after every e2e test.

    No-op when not running in CI (PR_NUMBER env var absent).
    """
    yield
    pr_number = os.environ.get("PR_NUMBER")
    if not pr_number:
        return
    env = os.environ.get("SMOKE_ENV", request.node.nodeid.split("/")[-1])
    try:
        _push_screenshots_to_ref(pr_number, env, screenshot_dir)
        _post_pr_comment(pr_number, env, passed=(request.node.rep_call.passed))
    except Exception as e:  # screenshot upload must never mask a real failure
        import logging
        logging.getLogger(__name__).exception("screenshot upload failed: %s", e)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo) -> None:
    outcome = yield
    rep = outcome.get_result()
    setattr(item, f"rep_{rep.when}", rep)


def _push_screenshots_to_ref(pr_number: str, env: str, src: Path) -> None:
    """git push screenshots/pr-{N} with src/*.png under {env}/."""
    ref = f"screenshots/pr-{pr_number}"
    worktree = Path(f"/tmp/screenshots-{pr_number}")
    if worktree.exists():
        subprocess.run(["rm", "-rf", str(worktree)], check=True)

    # Fetch existing ref or init an empty branch
    fetch = subprocess.run(
        ["git", "fetch", "origin", f"{ref}:{ref}"],
        capture_output=True, text=True,
    )
    if fetch.returncode == 0:
        subprocess.run(["git", "worktree", "add", str(worktree), ref], check=True)
    else:
        # Ref doesn't exist — create orphan branch
        subprocess.run(["git", "worktree", "add", "--detach", str(worktree), "HEAD"], check=True)
        subprocess.run(["git", "-C", str(worktree), "checkout", "--orphan", ref], check=True)
        subprocess.run(["git", "-C", str(worktree), "rm", "-rf", "."], check=False)

    env_dir = worktree / env
    env_dir.mkdir(parents=True, exist_ok=True)
    for png in src.glob("*.png"):
        subprocess.run(["cp", str(png), str(env_dir / png.name)], check=True)

    subprocess.run(["git", "-C", str(worktree), "add", "."], check=True)
    commit = subprocess.run(
        ["git", "-C", str(worktree), "commit", "-m", f"ci: e2e screenshots pr-{pr_number} {env}"],
        capture_output=True, text=True,
    )
    if commit.returncode == 0:  # nothing to commit is fine
        subprocess.run(
            ["git", "-C", str(worktree), "push", "origin", f"HEAD:{ref}"],
            check=True,
        )
    subprocess.run(["git", "worktree", "remove", "--force", str(worktree)], check=False)


def _post_pr_comment(pr_number: str, env: str, passed: bool) -> None:
    """Post a PR comment with inline screenshot images via gh CLI."""
    repo = os.environ.get("GITHUB_REPOSITORY", "DeepFlow-research/ergon")
    status = "✅ PASS" if passed else "❌ FAIL"
    body = (
        f"## E2E smoke — `{env}` — {status}\n\n"
        f"Screenshots from CI run:\n\n"
        f"![dashboard](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/dashboard-full.png)\n\n"
        f"![graph canvas](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/graph.png)\n\n"
        f"![cohort index](https://raw.githubusercontent.com/{repo}/screenshots/pr-{pr_number}/{env}/cohort.png)\n"
    )
    subprocess.run(
        ["gh", "pr", "comment", pr_number, "--body", body],
        check=True,
    )
```

### Playwright spec per env

```typescript
// ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts

import { expect, test } from "@playwright/test";

import { BackendHarnessClient } from "../helpers/testHarnessClient";

const RUN_ID = process.env.RUN_ID;
const SCREENSHOT_DIR = process.env.SCREENSHOT_DIR ?? "/tmp/playwright";
const ERGON_API = process.env.ERGON_API_BASE_URL ?? "http://127.0.0.1:9000";

test.skip(!RUN_ID, "Set RUN_ID (populated by pytest driver)");

test("canonical smoke — dashboard renders expected run", async ({ request, page }) => {
  // 1. Backend state via harness endpoint (stable wire shape)
  const harness = new BackendHarnessClient(request, ERGON_API);
  const state = await harness.getRunState(RUN_ID!);
  expect(state.status).toBe("completed");
  expect(state.graph_nodes.filter(n => n.level > 0)).toHaveLength(9);

  // 2. Run page renders the graph
  await page.goto(`/run/${RUN_ID}`);
  await expect(page.getByTestId("graph-canvas")).toBeVisible();
  const nodeElems = page.getByTestId(/^graph-node-/);
  await expect(nodeElems).toHaveCount(10);  // 1 root + 9 subtasks

  // Screenshot on pass — phase-5 uploader picks these up.
  await page.screenshot({ path: `${SCREENSHOT_DIR}/dashboard-full.png`, fullPage: true });
  await page.getByTestId("graph-canvas").screenshot({
    path: `${SCREENSHOT_DIR}/graph.png`,
  });

  // 3. Cohort index shows this run's cohort
  await page.goto("/");
  await expect(page.getByTestId("cohort-index-list")).toBeVisible();
  await page.screenshot({ path: `${SCREENSHOT_DIR}/cohort.png` });
});

// Screenshots on failure are captured automatically by the global config
// (`screenshot: "on"`; see playwright.config.ts delta below).
```

### `playwright.config.ts` — required changes

Current config (`ergon-dashboard/playwright.config.ts`) has
`screenshot: "only-on-failure"` which defeats the always-upload requirement.
Change to `"on"`:

```diff
 use: {
   baseURL,
   trace: "on-first-retry",
-  screenshot: "only-on-failure",
+  screenshot: "on",
   video: "retain-on-failure",
 },
```

## CI workflow

### `.github/workflows/e2e-benchmarks.yml` — reactivated and rewritten

```yaml
name: e2e-benchmarks

on:
  pull_request:
    branches: [main]

concurrency:
  group: e2e-${{ github.ref }}
  cancel-in-progress: true

jobs:
  smoke:
    name: e2e smoke — ${{ matrix.env }}
    timeout-minutes: 5
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        env: [researchrubrics, minif2f, swebench-verified]
    permissions:
      contents: write       # push to screenshots/pr-{N} ref
      pull-requests: write  # post PR comment
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - uses: astral-sh/setup-uv@v3
        with:
          enable-cache: true

      - run: uv sync --all-packages --group dev
      - run: pnpm install --frozen-lockfile

      # Docker caching (delivered in testing-posture-reset PR 2 — hard prerequisite)
      - uses: docker/setup-buildx-action@v3
      - uses: docker/bake-action@v4
        with:
          files: docker-compose.ci.yml
          load: true
          set: |
            *.cache-from=type=gha
            *.cache-to=type=gha,mode=max

      - name: Bring up backend stack
        run: |
          docker compose -f docker-compose.ci.yml up -d postgres inngest-dev api
          timeout 60 bash -c 'until curl -sf http://localhost:9000/docs >/dev/null; do sleep 2; done'
        env:
          ENABLE_TEST_HARNESS: "1"
          TEST_HARNESS_SECRET: ci-secret

      - name: Build + serve dashboard
        run: |
          pnpm --dir ergon-dashboard build
          pnpm --dir ergon-dashboard start > /tmp/dashboard.log 2>&1 &
          timeout 30 bash -c 'until curl -sf http://localhost:3000 >/dev/null; do sleep 2; done'
        env:
          ERGON_API_BASE_URL: http://127.0.0.1:9000

      - name: Run smoke
        run: |
          uv run pytest tests/e2e/test_${{ matrix.env }}_smoke.py -v --timeout=270
        env:
          ERGON_DATABASE_URL: postgresql://ergon:ci_test@localhost:5433/ergon
          ENABLE_TEST_HARNESS: "1"
          TEST_HARNESS_SECRET: ci-secret
          PR_NUMBER: ${{ github.event.pull_request.number }}
          GITHUB_REPOSITORY: ${{ github.repository }}
          E2B_API_KEY: ${{ secrets.E2B_API_KEY }}

      - name: Upload Playwright trace on failure
        if: failure()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-trace-${{ matrix.env }}
          path: ergon-dashboard/test-results/
          retention-days: 7

  cleanup-screenshot-ref:
    name: Delete screenshots/pr-{N} ref on PR close
    if: github.event.action == 'closed'
    runs-on: ubuntu-latest
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
      - run: |
          git push origin --delete "screenshots/pr-${{ github.event.pull_request.number }}" || true
```

Notes:

- `timeout-minutes: 5` enforces the per-job budget. If a run takes longer,
  the job fails and the PR review sees it. Increase later if 5 min is
  empirically tight (after 10-15 real runs).
- `concurrency` cancels prior e2e runs when a new push lands on the same
  branch — avoids stacking screenshot commits on the same PR ref.
- `fail-fast: false` ensures one env's failure doesn't skip the other two's
  screenshot capture — every env's failure mode should be visible in the
  PR simultaneously.
- `E2B_API_KEY` is available to every PR. DeepFlow Research org-internal
  project; fork-PR secret exposure is not a current concern. See §"Open
  questions" for revisiting if the org policy changes.
- Cleanup job runs on PR close and deletes the `screenshots/pr-{N}` ref so
  the repo doesn't accumulate orphan branches. The ref is orphan (never
  merged into main) so deletion is safe.

## Migration

### Hard prerequisites (must land first)

| Dependency | Source | Why |
|---|---|---|
| Docker layer caching in `e2e-benchmarks.yml` + `docker-compose.ci.yml` | PR 2 of `docs/rfcs/active/2026-04-18-testing-posture-reset.md` (which fixes `docs/bugs/open/2026-04-18-ci-docker-caching.md`) | Every-PR trigger with 5-min budget is impossible without layer caching. Cold stack boot is ~60-90s on current CI. |
| `tests/e2e/` deleted for clean slate | PR 4 of `docs/rfcs/active/2026-04-18-testing-posture-reset.md` | Current e2e tier is retired wholesale; this RFC rebuilds. See §3.1 note in reset RFC. |
| `tests/integration/` infrastructure (real Postgres + Inngest) | PR 3 of the reset RFC | Pytest driver assumes the integration-tier Docker stack is already wired and caching works. |

Coverage-gap window: between reset-RFC PR 4 landing (e2e deleted) and this
RFC's PR 1 landing (first smoke live), main has zero e2e coverage for the
CLI → Inngest → sandbox pipeline. This is an intentional tradeoff chosen
over gradual displacement (see reset RFC PR 4 note). To minimize the
window, this RFC's PR 1 should be drafted in parallel and land immediately
after reset PR 4.

### Superseded RFCs on merge

Both superseded RFCs move `active/` → `rejected/` (not `accepted/` — neither
was implemented standalone) with a one-line note in the file header:

```markdown
---
status: rejected
superseded_by: docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md
```

### Architecture doc updates (on this RFC moving to `accepted/`)

- `docs/architecture/06_builtins.md §4` — replace "Every benchmark MUST ship
  a stub worker …" invariant with "Every benchmark MUST ship a
  `SmokeSubworker` + `SmokeCriterion` pair and register the `smoke-leaf`
  binding in its composition." Reference this RFC.
- `docs/architecture/07_testing.md §2` — update code map to include
  `tests/e2e/test_{env}_smoke.py` pattern and
  `ergon-dashboard/tests/e2e/{env}.smoke.spec.ts` pattern.
- `docs/architecture/07_testing.md §4` — add invariant: "every env in
  {researchrubrics, minif2f, swebench-verified} has exactly one canonical
  smoke pair (Python + Playwright) that runs on every PR."
- `docs/architecture/05_dashboard.md` — add invariant: "every run produced
  by `CanonicalSmokeWorker` renders in the dashboard with 10 graph nodes
  (1 root + 9 subtasks) and completes successfully; this is enforced by
  the e2e smoke Playwright specs."
- `docs/architecture/01_public_api.md` — add section "Test-only extension
  points" listing the `/api/test/*` router as not part of the public API.

## Invariants affected

**New invariants introduced by this RFC:**

1. **Every env has exactly one canonical smoke.** `tests/e2e/` contains
   exactly `test_researchrubrics_smoke.py`, `test_minif2f_smoke.py`,
   `test_swebench_verified_smoke.py` — one per env, no more, no less.
   Enforced by the structure of the CI matrix + review.

2. **Canonical graph shape is immutable across envs.** The 9-subtask
   topology (diamond + line + 2 singletons) is hardcoded in
   `CanonicalSmokeWorker` and referenced by constant name in every
   criterion and every pytest + Playwright spec. Changing the shape is a
   global change that requires amending this RFC.

3. **Canonical smokes run on every PR.** `.github/workflows/e2e-benchmarks.yml`
   triggers on `pull_request`, not `feature/*`. The previous policy
   (feature-branch-only) is retired.

4. **Playwright backend assertions go through `/api/test/*`.** TypeScript
   test code never queries Postgres directly. Python test code
   (`tests/e2e/test_*.py`) MAY query Postgres directly via the engine;
   TypeScript code MUST NOT.

5. **Screenshots are inline in PR comments on pass AND fail.** Not
   downloadable-only; not failure-only. The PR reviewer sees
   `![image](raw.githubusercontent.com/…)` rendered in every e2e
   smoke comment.

**Invariants changed:**

- `docs/architecture/06_builtins.md §4` "every benchmark ships a stub
  worker" → "every benchmark ships a `SmokeSubworker` + `SmokeCriterion`
  pair via composition binding".
- `docs/architecture/07_testing.md §3` "E2E tests run on `feature/*` only"
  → "e2e smokes run on every PR; expensive full-stack benchmark tests
  (non-smoke) run on `feature/*`".

**Invariants preserved:**

- "Every state change has a corresponding `dashboard/*` event"
  (`docs/architecture/05_dashboard.md`) — this RFC's smokes implicitly test
  this by asserting dashboard DOM reflects Postgres state.
- "Integration tests hit real Postgres + real Inngest"
  (`docs/architecture/07_testing.md §4`) — e2e smokes do too; they just go
  one layer higher (real sandbox + real dashboard).

## Implementation order

Phased into four PRs. Each PR must leave CI green before the next lands.

### PR 1 — Shared smoke worker + harness endpoints, no env implementations

| Step | What | Files touched |
|---|---|---|
| 1 | Add `SmokeSubworker` Protocol, `SubworkerResult` dataclass, `BaseSmokeLeafWorker`, `CanonicalSmokeWorker` | ADD `ergon_builtins/workers/stubs/smoke_subworker.py`, `ergon_builtins/workers/stubs/canonical_smoke_worker.py`, `ergon_builtins/workers/stubs/base_smoke_leaf.py` |
| 2 | Add `SmokeCriterionBase` abstract class | ADD `ergon_builtins/evaluators/criteria/smoke_criterion.py` |
| 3 | Add `/api/test/*` router (absorbed from test-harness RFC) | ADD `ergon_core/core/api/test_harness.py` + unit tests per superseded RFC spec |
| 4 | Mount router conditionally in `app.py` | MODIFY `ergon_core/core/api/app.py` |
| 5 | Add `BackendHarnessClient` TS helper | ADD `ergon-dashboard/tests/helpers/testHarnessClient.ts` |
| 6 | Update `playwright.config.ts` screenshot setting | MODIFY `ergon-dashboard/playwright.config.ts` |
| 7 | Close superseded RFCs | MOVE `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` → `rejected/`; MOVE `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` → `rejected/`; set `superseded_by` on both |

**PR 1 acceptance gate:** `pnpm run check:be` + `check:fe` green;
`/api/test/*` endpoints return expected responses against a live dev stack;
shared worker classes pass unit tests (collection + registry lookup).

### PR 2 — First env smoke: `researchrubrics` (canary)

| Step | What | Files touched |
|---|---|---|
| 1 | Add `ResearchRubricsSmokeSubworker`, `ResearchRubricsSmokeLeafWorker`, `ResearchRubricsSmokeCriterion` | ADD `ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py` + criterion |
| 2 | Register in `registry_core.py` | MODIFY `ergon_builtins/registry_core.py` |
| 3 | Add composition binding for `researchrubrics`: `smoke-leaf → researchrubrics-smoke-leaf` | MODIFY `ergon_cli/ergon_cli/composition/__init__.py` |
| 4 | Add `tests/e2e/conftest.py` with screenshot finalizer, `run_benchmark`, `wait_for_terminal` | ADD `tests/e2e/conftest.py` |
| 5 | Add `tests/e2e/test_researchrubrics_smoke.py` | ADD |
| 6 | Add `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts` | ADD |
| 7 | Add `.github/workflows/e2e-benchmarks.yml` with matrix containing only `researchrubrics` (minif2f/swebench added in PR 3/4) | ADD |
| 8 | Add `ENABLE_TEST_HARNESS` + `TEST_HARNESS_SECRET` to `docker-compose.ci.yml` api env block | MODIFY `docker-compose.ci.yml` |

**PR 2 acceptance gate:** `researchrubrics` e2e smoke runs on every PR in
under 5 min; Postgres assertions + Playwright + screenshot upload + PR
comment all work end-to-end; cleanup workflow deletes
`screenshots/pr-{N}` on PR close.

### PR 3 — Second env smoke: `minif2f`

| Step | What | Files touched |
|---|---|---|
| 1 | Add `MiniF2FSmokeSubworker`, `MiniF2FSmokeLeafWorker`, `MiniF2FSmokeCriterion` | ADD |
| 2 | Register + binding | MODIFY |
| 3 | Add pytest + Playwright spec | ADD 2 files |
| 4 | Add `minif2f` to CI matrix | MODIFY `.github/workflows/e2e-benchmarks.yml` |

**PR 3 acceptance gate:** both `researchrubrics` and `minif2f` smokes
green on every PR, with Lean kernel probe verified.

### PR 4 — Third env smoke: `swebench-verified`

| Step | What | Files touched |
|---|---|---|
| 1 | Add `SweBenchSmokeSubworker`, `SweBenchSmokeLeafWorker`, `SweBenchSmokeCriterion` | ADD |
| 2 | Register + binding | MODIFY |
| 3 | Add pytest + Playwright spec | ADD 2 files |
| 4 | Add `swebench-verified` to CI matrix | MODIFY |
| 5 | Update architecture-doc invariants cited in §"Invariants affected" | MODIFY `docs/architecture/{01,05,06,07}*.md` |
| 6 | Move this RFC `active/` → `accepted/` | MOVE |

**PR 4 acceptance gate:** all three env smokes green on every PR;
architecture docs updated; this RFC moved to `accepted/`.

## File map

### ADD (Python, production)

| File | Purpose |
|---|---|
| `ergon_builtins/workers/stubs/smoke_subworker.py` | `SmokeSubworker` Protocol + `SubworkerResult` dataclass |
| `ergon_builtins/workers/stubs/canonical_smoke_worker.py` | `CanonicalSmokeWorker` (shared parent) + `EXPECTED_SUBTASK_KEYS` |
| `ergon_builtins/workers/stubs/base_smoke_leaf.py` | `BaseSmokeLeafWorker` — shared glue between any subworker and the publisher |
| `ergon_builtins/benchmarks/researchrubrics/smoke_subworker.py` | Leaf subworker + leaf worker wrapper |
| `ergon_builtins/benchmarks/minif2f/smoke_subworker.py` | Leaf subworker + leaf worker wrapper |
| `ergon_builtins/benchmarks/swebench_verified/smoke_subworker.py` | Leaf subworker + leaf worker wrapper |
| `ergon_builtins/evaluators/criteria/smoke_criterion.py` | `SmokeCriterionBase` + 3 env-specific subclasses |
| `ergon_core/core/api/test_harness.py` | FastAPI test-harness router (absorbed from superseded RFC) |

### ADD (Python, tests)

| File | Purpose |
|---|---|
| `tests/e2e/conftest.py` | Screenshot upload finalizer, `run_benchmark`, `wait_for_terminal` |
| `tests/e2e/test_researchrubrics_smoke.py` | Canonical smoke pytest for researchrubrics |
| `tests/e2e/test_minif2f_smoke.py` | Canonical smoke pytest for minif2f |
| `tests/e2e/test_swebench_verified_smoke.py` | Canonical smoke pytest for swebench-verified |
| `tests/unit/test_test_harness.py` | Unit tests for harness gate + secret + round-trip |
| `tests/integration/smokes/test_smoke_harness.py` | Integration test for harness seed + read round-trip |

### ADD (TypeScript)

| File | Purpose |
|---|---|
| `ergon-dashboard/tests/helpers/testHarnessClient.ts` | `BackendHarnessClient` class |
| `ergon-dashboard/tests/e2e/researchrubrics.smoke.spec.ts` | Playwright spec |
| `ergon-dashboard/tests/e2e/minif2f.smoke.spec.ts` | Playwright spec |
| `ergon-dashboard/tests/e2e/swebench-verified.smoke.spec.ts` | Playwright spec |

### ADD (CI)

| File | Purpose |
|---|---|
| `.github/workflows/e2e-benchmarks.yml` | Reactivated from disabled state (reset RFC PR 4 left it disabled); full rewrite with matrix + screenshot cleanup |

### MODIFY

| File | Change |
|---|---|
| `ergon_builtins/ergon_builtins/registry_core.py` | Register `canonical-smoke`, 3 env leaf workers, 3 env criteria |
| `ergon_cli/ergon_cli/composition/__init__.py` | Add `smoke-leaf` binding for each env's composition |
| `ergon_core/core/api/app.py` | Conditional `include_router(test_harness_router)` on `ENABLE_TEST_HARNESS=1` |
| `docker-compose.ci.yml` | Add `ENABLE_TEST_HARNESS=1` + `TEST_HARNESS_SECRET=ci-secret` to api env |
| `ergon-dashboard/playwright.config.ts` | `screenshot: "only-on-failure"` → `"on"` |
| `docs/architecture/06_builtins.md` | Rewrite §4 invariant per §"Invariants affected" |
| `docs/architecture/07_testing.md` | Update §2 code map, §3 trigger policy, §4 new invariant |
| `docs/architecture/05_dashboard.md` | Add canonical-smoke invariant |
| `docs/architecture/01_public_api.md` | Add "Test-only extension points" section |

### MOVE (on PR 1 merge)

| From | To | Reason |
|---|---|---|
| `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` | `docs/rfcs/rejected/…` | Superseded by this RFC |
| `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` | `docs/rfcs/rejected/…` | Superseded by this RFC |

### MOVE (on PR 4 merge)

| From | To |
|---|---|
| `docs/rfcs/active/2026-04-21-e2e-smoke-coverage-rewrite.md` | `docs/rfcs/accepted/…` |

## Testing approach

### PR 1

- Unit: `tests/unit/test_test_harness.py` — harness gate, secret, read+seed+reset
  round-trip.
- Registry: `tests/unit/test_benchmark_contract.py` (existing) — extends to
  assert `canonical-smoke` + base classes are registered and constructible.

### PR 2-4

- Each env PR is its own e2e acceptance: the pytest smoke runs in CI against
  the full stack. No local-only green; the test either passes in the matrix
  job or doesn't merge.

### Failure-mode rehearsal (manual, pre-merge of PR 2)

Before PR 2 merges, manually induce each failure class to verify screenshot
delivery works on failure paths:

1. Break a Python Postgres assertion → pytest fails → Playwright still
   runs → screenshots upload → PR comment says ❌ FAIL → reviewer sees
   DOM at moment of failure.
2. Make Playwright fail (e.g. change a testId expectation) → pytest sees
   subprocess returncode ≠ 0 → fails → screenshots still upload (Playwright
   writes on failure via config).
3. Timeout the benchmark (set `--timeout=10s` locally against a slow env) →
   `wait_for_terminal` raises → pytest fails → finalizer still runs.

All three must produce visible screenshots in the PR comment.

## Alternatives considered

- **One monolithic smoke worker per env (no shared parent).** Rejected. Each
  env reimplements topology; graph regressions surface differently or not
  at all. The "every env proves the same graph invariants" property is
  structurally impossible without a shared parent.
- **Real-LLM canary in addition to stub-only.** Rejected. Explicitly
  scoped out (see question-5 dialogue in brainstorm). Real-LLM coverage
  belongs in eval runs, not smokes. The env-container probe is what
  verifies the sandbox is set up; the parent graph topology is what
  verifies the runtime. Neither needs an LLM.
- **Feature-branch-only trigger (current e2e policy).** Rejected. Main is
  trunk-based per `CLAUDE.md §Git workflow`; direct-to-main commits don't
  run feature-branch CI, so regressions in the CLI → Inngest → sandbox
  path can land for days before a feature PR catches them. Every-PR trigger
  is the structural fix.
- **Screenshots as CI artifacts only, no PR comment.** Rejected. User
  requirement is "see them in the PR." CI artifact download requires
  clicking through to the Actions tab, which reviewers skip. Inline in PR
  comment is the only mechanism that meets the requirement.
- **Screenshots via imgur/S3 upload.** Rejected. External dependency +
  retention risk + ACL management. Pushing to a dedicated orphan ref in
  the same repo is secretless, auditable, and self-cleaning on PR close.
- **Single Python test that drives Playwright via `playwright-pytest`
  plugin.** Rejected. The plugin changes the fixture model in ways that
  fight with our existing `screenshot_upload_finalizer`. Subprocess
  invocation is simpler, explicit, and keeps the two test languages in
  their respective ecosystems.
- **Parameterize topology per env.** Rejected (option B in Q4 of the
  brainstorm). The whole point of a shared topology is that "graph
  regressions surface uniformly across envs." If one env has its own
  shape, we lose that property and re-introduce the per-benchmark-drift
  problem the old stub workers had.

## Open questions

- **E2B secret exposure on every PR.** Current assumption: DeepFlow Research
  is org-internal; fork PRs are rare-to-nonexistent; `E2B_API_KEY` on
  every PR is operationally fine. Revisit if the org opens the repo to
  external contributors. Mitigation if that happens: either require
  maintainer-approval-to-run for untrusted PRs (GitHub setting) or switch
  `researchrubrics` + `swebench-verified` to a local Docker sandbox image
  for the smoke tier while reserving E2B for `feature/*`.
- **Wall-clock budget of 5 minutes.** Chosen optimistically. If empirical
  runs average above 3 minutes, raise to 8 min. If they're consistently
  over 5 even with caching, we've got a bottleneck to investigate
  (sandbox provision time is the usual suspect).
- **Dashboard target: prod-build vs dev-server.** Chosen: prod-build
  (`pnpm build` + `pnpm start`). Rationale: this is what end-users
  experience; dev-server has different timing characteristics that can
  mask regressions. Adds ~30s to CI boot but more representative.
  `@charliemasters` — revisit if prod-build boot makes the 5-min budget
  impossible.
- **Screenshot retention policy beyond PR close.** Chosen: delete on PR
  close. If someone wants historical screenshots for a regression
  investigation, the CI artifact from the original run still has them
  (retention 7d). Revisit if 7-day artifact retention proves too short
  in practice.
- **Third-party retention for screenshots (CDN).** Considered and
  rejected (see Alternatives). If the in-repo orphan ref approach causes
  git-ops pain (e.g. clone time bloat), revisit.

## On acceptance

When this RFC moves from `active/` to `accepted/` on PR 4 merge:

- Move `docs/rfcs/active/2026-04-18-fixed-delegation-stub-worker.md` →
  `docs/rfcs/rejected/` (on PR 1 merge, not PR 4 — they're dead before
  PR 4).
- Move `docs/rfcs/active/2026-04-18-test-harness-endpoints.md` →
  `docs/rfcs/rejected/` (on PR 1 merge).
- Update `docs/architecture/06_builtins.md §4`,
  `docs/architecture/07_testing.md §§2-4`,
  `docs/architecture/05_dashboard.md`, `docs/architecture/01_public_api.md`
  per §"Invariants affected".
- Delete `docs/bugs/open/2026-04-18-ci-docker-caching.md` from open/ and
  move to fixed/ (closed when reset-RFC PR 2 lands; confirm in this RFC's
  PR 4 body).
- Link the implementation plan in
  `docs/superpowers/plans/2026-04-21-e2e-smoke-coverage-rewrite.md`.

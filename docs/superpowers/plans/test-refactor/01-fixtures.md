# 01 — Fixtures: shared bases + per-env workers, leaves, criteria

**Status:** draft
**Scope:** every production-code change in `tests/e2e/_fixtures/` and the corresponding deletions in `ergon_builtins/`. Code sketches are representative, not literal copy-paste — the actual PR must conform to current `Worker` / `Criterion` ABC signatures.

For deletion of the equivalent files from `ergon_builtins/`, see [`05-deletions.md`](05-deletions.md).

---

## 1. Directory layout

```
tests/
└── e2e/
    ├── __init__.py
    ├── conftest.py
    ├── _fixtures/
    │   ├── __init__.py                      ← registration hook; see §2.7
    │   ├── smoke_base/
    │   │   ├── __init__.py
    │   │   ├── constants.py                 ← EXPECTED_SUBTASK_SLUGS, SUBTASK_GRAPH
    │   │   ├── worker_base.py               ← SmokeWorkerBase (non-registered, @final execute)
    │   │   ├── leaf_base.py                 ← BaseSmokeLeafWorker (non-registered)
    │   │   ├── subworker.py                 ← SmokeSubworker Protocol + SubworkerResult
    │   │   └── criterion_base.py            ← SmokeCriterionBase (non-registered)
    │   ├── workers/
    │   │   ├── __init__.py
    │   │   ├── researchrubrics_smoke.py     ← parent + leaf + subworker for researchrubrics
    │   │   ├── minif2f_smoke.py             ← parent + leaf + subworker for minif2f
    │   │   └── swebench_smoke.py            ← parent + leaf + subworker for swebench
    │   └── criteria/
    │       ├── __init__.py
    │       ├── researchrubrics_smoke.py     ← ResearchRubricsSmokeCriterion
    │       ├── minif2f_smoke.py             ← MiniF2FSmokeCriterion
    │       └── swebench_smoke.py            ← SweBenchSmokeCriterion
    ├── test_researchrubrics_smoke.py
    ├── test_minif2f_smoke.py
    └── test_swebench_smoke.py
```

Rationale for a single file per env in `workers/`: the env-specific parent, leaf, and subworker are cohesive and changing one usually requires changing the others. Bundle per env, not per role.

---

## 2. Shared bases (not registered)

### 2.1 `smoke_base/constants.py`

```python
# tests/e2e/_fixtures/smoke_base/constants.py

from collections.abc import Sequence

EXPECTED_SUBTASK_SLUGS: tuple[str, ...] = (
    "d_root", "d_left", "d_right", "d_join",
    "l_1", "l_2", "l_3",
    "s_a", "s_b",
)

# (slug, depends_on_slugs, description) — shape of the DAG in one place.
SUBTASK_GRAPH: Sequence[tuple[str, tuple[str, ...], str]] = (
    ("d_root",  (),                    "Diamond root"),
    ("d_left",  ("d_root",),           "Diamond left arm"),
    ("d_right", ("d_root",),           "Diamond right arm"),
    ("d_join",  ("d_left", "d_right"), "Diamond join"),
    ("l_1",     (),                    "Line node 1"),
    ("l_2",     ("l_1",),              "Line node 2"),
    ("l_3",     ("l_2",),              "Line node 3"),
    ("s_a",     (),                    "Singleton A"),
    ("s_b",     (),                    "Singleton B"),
)
```

### 2.2 `smoke_base/subworker.py`

```python
# tests/e2e/_fixtures/smoke_base/subworker.py

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ergon_core.core.providers.sandbox.manager import AsyncSandbox


@dataclass(frozen=True)
class SubworkerResult:
    file_path: str
    probe_stdout: str
    probe_exit_code: int


@runtime_checkable
class SmokeSubworker(Protocol):
    """Env-specific deterministic work inside a sandbox.

    MUST NOT call an LLM. MUST NOT make external network calls.
    MUST complete within 20 seconds under normal sandbox conditions.
    """

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult: ...
```

### 2.3 `smoke_base/worker_base.py`

**Key difference from the retired `CanonicalSmokeWorker`:** no `type_slug` at the base (so it is not registered), and `execute()` is `@final`. Subclasses set `leaf_slug` only.

```python
# tests/e2e/_fixtures/smoke_base/worker_base.py

from collections.abc import AsyncGenerator
from typing import ClassVar, final
from uuid import UUID

from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.shared.types import (
    AssignedWorkerSlug, NodeId, RunId, TaskSlug,
)
from ergon_core.core.runtime.services.task_management_dto import (
    PlanSubtasksCommand, SubtaskSpec,
)
from ergon_core.core.runtime.services.task_management_service import (
    TaskManagementService,
)

from tests.e2e._fixtures.smoke_base.constants import SUBTASK_GRAPH


class SmokeWorkerBase(Worker):
    """Abstract parent. Subclasses set `type_slug` and `leaf_slug`.

    Topology is locked by `@final` on `execute` and by using SUBTASK_GRAPH
    directly (no subclass hook for altering the shape).
    """

    leaf_slug: ClassVar[str]  # e.g. "researchrubrics-smoke-leaf"

    def __init__(
        self, *, name: str, model: str | None, task_id: UUID, sandbox_id: str,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)

    # Parent execution yields 3 turns so the incremental turn persistence
    # path is exercised on every smoke run. See §2.6 ("Fidelity") for why.
    PARENT_TURN_COUNT: ClassVar[int] = 3

    @final
    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        if context.node_id is None:
            raise ValueError(f"{type(self).__name__} requires context.node_id")

        # --- Turn 1: planning announcement (pre-service-call) ---
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: planning 9 subtasks "
                        f"(diamond+line+singletons) → leaf slug={self.leaf_slug}"
                    ),
                ),
            ],
        )

        # Per-slug spec construction goes through _spec_for so sad-path
        # subclasses can route specific slugs to a different leaf worker
        # without overriding execute() (which stays @final).
        specs = [self._spec_for(slug, deps, desc) for slug, deps, desc in SUBTASK_GRAPH]
        with get_session() as session:
            result = await TaskManagementService().plan_subtasks(
                session,
                PlanSubtasksCommand(
                    run_id=RunId(context.run_id),
                    parent_node_id=NodeId(context.node_id),
                    subtasks=specs,
                ),
            )

        # --- Turn 2: plan result (post-service-call) ---
        summary = "\n".join(
            f"{slug}: planned (node_id={result.nodes[TaskSlug(slug)]})"
            for slug, _deps, _desc in SUBTASK_GRAPH
        )
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: 9 subtasks planned "
                        f"(roots={sorted(result.roots)}):\n{summary}"
                    ),
                ),
            ],
        )

        # --- Turn 3: awaiting children (terminal) ---
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: awaiting 9 children → "
                        "runtime will mark parent COMPLETED once wait_all resolves"
                    ),
                ),
            ],
        )

    def _spec_for(
        self, slug: str, deps: tuple[str, ...], desc: str,
    ) -> SubtaskSpec:
        """Overridable per-slug → (assigned_worker_slug, deps) mapping.

        Default routes every slug to `self.leaf_slug`. Sad-path subclasses
        (see §3.4) override this to route specific slugs to a failing leaf
        while keeping the 9-subtask topology identical. Execute() stays
        @final so topology is never changed; only the leaf binding is.
        """
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=desc,
            assigned_worker_slug=AssignedWorkerSlug(self.leaf_slug),
            depends_on=[TaskSlug(d) for d in deps],
        )
```

**No pydantic-ai toolkits, no tool-loop, no generation model.** `execute()` runs deterministic Python that plans nine subtasks in one `TaskManagementService.plan_subtasks` call and yields one terminal `GenerationTurn`. `model=None` is passed through `__init__` and ignored.

### 2.4 `smoke_base/leaf_base.py`

Unchanged in shape from current `ergon_builtins/workers/stubs/base_smoke_leaf.py`, just re-homed and sanded down for the new import paths. Subclasses set `type_slug` (registered) and `subworker_cls` (composition).

```python
# tests/e2e/_fixtures/smoke_base/leaf_base.py

from collections.abc import AsyncGenerator
from typing import ClassVar
from uuid import UUID

from e2b_code_interpreter import AsyncSandbox
from ergon_core.api import BenchmarkTask, Worker, WorkerContext
from ergon_core.api.generation import GenerationTurn, TextPart
from ergon_core.api.results import WorkerOutput

from tests.e2e._fixtures.smoke_base.subworker import SmokeSubworker, SubworkerResult


class BaseSmokeLeafWorker(Worker):
    """Abstract leaf. Subclasses set `type_slug` and `subworker_cls`."""

    subworker_cls: ClassVar[type[SmokeSubworker]]

    # Each leaf yields 2 turns. Driver asserts on per-run totals to catch
    # silent regressions in incremental turn persistence. See §2.6.
    LEAF_TURN_COUNT: ClassVar[int] = 2

    def __init__(
        self, *, name: str, model: str | None, task_id: UUID, sandbox_id: str,
    ) -> None:
        super().__init__(name=name, model=model, task_id=task_id, sandbox_id=sandbox_id)
        self._last_result: SubworkerResult | None = None

    async def execute(
        self, task: BenchmarkTask, *, context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        node_hex = context.node_id.hex[:8] if context.node_id else "unknown"

        # --- Turn 1: attaching + starting ---
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: attaching to sandbox "
                        f"{context.sandbox_id} for node={node_hex}"
                    ),
                ),
            ],
        )

        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
        result = await self.subworker_cls().work(node_id=node_hex, sandbox=sandbox)
        self._last_result = result

        # Post a one-line completion message to the shared "smoke-completion"
        # thread. Every happy-path leaf sends exactly one message; sad-path
        # leaves that raise before this point do NOT send — the driver asserts
        # on that shape. Uses the existing (today unused) CommunicationService.
        await self._send_completion_message(context, result)

        # --- Turn 2: done + result summary ---
        yield GenerationTurn(
            response_parts=[
                TextPart(
                    content=(
                        f"{type(self).__name__}: done node={node_hex} "
                        f"file={result.file_path} probe_exit={result.probe_exit_code}"
                    ),
                ),
            ],
        )

    async def _send_completion_message(
        self, context: WorkerContext, result: SubworkerResult,
    ) -> None:
        """One ThreadMessage per leaf on the smoke-completion thread.

        Structure asserted by driver (`_assert_thread_messages_ordered`):

        - Thread topic == "smoke-completion"
        - Agents: `leaf-{task_slug}` → `parent`
        - 9 messages per happy-path run (sequence_num 1..9, per-thread monotonic)
        - Creation timestamps monotonically non-decreasing in leaf-completion order

        Sad-path leaf does NOT reach this call because `AlwaysFailSubworker`
        raises inside `work()`. Driver asserts 8 messages in the sad-path run.
        """
        from ergon_core.core.runtime.services.communication_service import (
            communication_service,
        )
        from ergon_core.core.runtime.services.communication_schemas import (
            CreateMessageRequest,
        )

        await communication_service.save_message(
            CreateMessageRequest(
                run_id=context.run_id,
                task_execution_id=context.execution_id,
                from_agent_id=f"leaf-{context.task_slug}",
                to_agent_id="parent",
                thread_topic="smoke-completion",
                content=(
                    f"{context.task_slug}: done exit={result.probe_exit_code} "
                    f"file={result.file_path}"
                ),
            ),
        )

    def get_output(self, context: WorkerContext) -> WorkerOutput:
        r = self._last_result
        if r is None:
            return WorkerOutput(output="", success=False, metadata={"error": "no_result"})
        return WorkerOutput(
            output=r.probe_stdout,
            success=r.probe_exit_code == 0,
            metadata={"probe_exit_code": r.probe_exit_code, "file_path": r.file_path},
        )
```

### 2.5 `smoke_base/criterion_base.py`

**Change from the current file:** `_pull_children` and `_pull_probe_results` must be concretely implemented, not raise `NotImplementedError`. The current file has pointer comments — those get filled in here.

```python
# tests/e2e/_fixtures/smoke_base/criterion_base.py

from typing import Any
from uuid import UUID

from sqlmodel import select

from ergon_core.api import (
    Criterion, CriterionResult, CriteriaCheckError, EvaluationContext,
)
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.graph.status_conventions import COMPLETED
from ergon_core.core.persistence.resources.models import RunResource
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.providers.blob.client import BlobClient  # or canonical import

from tests.e2e._fixtures.smoke_base.constants import EXPECTED_SUBTASK_SLUGS


class SmokeCriterionBase(Criterion):
    """Structural + probe checks. Env subclasses override `_verify_env_content`."""

    async def evaluate(self, context: EvaluationContext) -> CriterionResult:
        try:
            # 1. Artifact-side checks (no sandbox; reads blob storage only)
            children = await self._pull_children(context)
            self._check_graph_shape(children)
            self._check_children_completed(children)
            probes = await self._pull_probe_results(context, children)
            self._check_probes_succeeded(probes, children)
            await self._verify_env_content(context, children, probes)

            # 2. Sandbox-side check: attach to the parent task's OWN
            #    sandbox (kept alive by the runtime per RFC
            #    `sandbox-lifetime-covers-criteria`) and run a trivial
            #    env-specific command. Proves the image / toolchain is
            #    healthy; independent of what the leaves produced.
            #    No fresh sandbox acquisition — zero extra E2B cost.
            await self._verify_sandbox_setup(context)
        except CriteriaCheckError as e:
            return CriterionResult(
                name=self.name, score=0.0, passed=False,
                weight=self.weight,
                feedback=f"smoke criterion failed: {e}",
            )
        return CriterionResult(
            name=self.name, score=1.0, passed=True,
            weight=self.weight, feedback="smoke passed",
        )

    async def _pull_children(self, context: EvaluationContext) -> list[RunGraphNode]:
        with get_session() as s:
            parent = s.exec(
                select(RunGraphNode).where(
                    RunGraphNode.task_execution_id == context.execution_id,
                ),
            ).one()
            children = s.exec(
                select(RunGraphNode)
                .where(RunGraphNode.parent_id == parent.id)
                .order_by(RunGraphNode.task_slug),
            ).all()
        return list(children)

    async def _pull_probe_results(
        self, context: EvaluationContext, children: list[RunGraphNode],
    ) -> dict[UUID, dict[str, Any]]:
        results: dict[UUID, dict[str, Any]] = {}
        with get_session() as s:
            for child in children:
                resource = s.exec(
                    select(RunResource)
                    .where(RunResource.node_id == child.id)
                    .where(RunResource.name.like("probe_%.json")),
                ).first()
                if resource is None:
                    raise CriteriaCheckError(f"{child.task_slug}: no probe_*.json resource")
                blob_bytes = await BlobClient.default().get(resource.content_hash)
                results[child.id] = _parse_probe_json(blob_bytes)
        return results

    def _check_graph_shape(self, children: list[RunGraphNode]) -> None:
        actual = {c.task_slug for c in children}
        expected = set(EXPECTED_SUBTASK_SLUGS)
        if actual != expected:
            raise CriteriaCheckError(
                f"graph shape mismatch: actual={sorted(actual)} expected={sorted(expected)}",
            )

    def _check_children_completed(self, children: list[RunGraphNode]) -> None:
        for c in children:
            if c.status != COMPLETED:
                raise CriteriaCheckError(
                    f"child {c.task_slug} not completed (status={c.status!r})",
                )

    def _check_probes_succeeded(
        self, probes: dict[UUID, dict[str, Any]], children: list[RunGraphNode],
    ) -> None:
        by_id = {c.id: c for c in children}
        for child_id, probe in probes.items():
            slug = by_id[child_id].task_slug
            code = probe.get("exit_code")
            if code != 0:
                raise CriteriaCheckError(
                    f"probe for {slug} exited {code}, stdout={probe.get('stdout', '')!r}",
                )

    async def _verify_env_content(
        self, context: EvaluationContext,
        children: list[RunGraphNode],
        probes: dict[UUID, dict[str, Any]],
    ) -> None:
        """Subclass hook: read artifacts and check env-specific file shape."""
        raise NotImplementedError

    async def _verify_sandbox_setup(self, context: EvaluationContext) -> None:
        """Subclass hook: run a trivial env-specific command in the parent
        task's sandbox to prove the toolchain is healthy.

        Canonical shape for subclasses — goes through the landed
        `CriterionRuntime` DI API (RFC `criterion-runtime-di-container`,
        accepted). The runtime owns sandbox lifecycle; the criterion never
        calls `AsyncSandbox.connect` directly.

            await context.runtime.ensure_sandbox()
            result = await context.runtime.run_command(
                "<env-health-probe>", timeout=20,
            )
            if result.exit_code != 0:
                raise CriteriaCheckError(
                    f"<env> health probe failed: exit={result.exit_code} "
                    f"stdout={(result.stdout or '')[:200]!r}",
                )

        Why the runtime is the right surface:

        - `CriterionRuntime.ensure_sandbox()` (`runtime/evaluation/criterion_runtime.py`)
          attaches via `sandbox_manager.get_sandbox(run_id)` for in-process
          criteria and will use `BaseSandboxManager.reconnect(sandbox_id)`
          for cross-process criteria once Phase G lands that method. Either
          way, criteria keep calling `context.runtime.run_command(...)` —
          no code change on the criterion side.
        - RFC `sandbox-lifetime-covers-criteria` (active) guarantees the
          task's sandbox is kept alive through criterion execution.
        - Criteria MUST NOT construct sandboxes directly — the anti-pattern
          that `bugs/fixed/2026-04-18-swebench-criterion-spawns-sandbox.md`
          fixed.
        """
        raise NotImplementedError
```

`_parse_probe_json` is a pure helper colocated beside the class.

### 2.6 Fidelity — what smoke proves, and what it deliberately skips

Smoke fixtures are not miniature production workers; they are the minimal subclass of `Worker` that exercises the runtime plumbing we care about without requiring an LLM. Being explicit about the gap is what lets smoke stay fast and deterministic.

#### What smoke preserves (same code path as production)

- `Worker` ABC signature (`__init__(*, name, model, task_id, sandbox_id)`, `execute`, `get_output`).
- `AsyncGenerator[GenerationTurn, None]` yield protocol — **smoke yields multiple turns per execution** (3 from the parent, 2 per leaf; §2.3, §2.4), so incremental turn persistence, context event sequencing, and thread-message emission per-turn are exercised on every smoke run.
- `AsyncSandbox.connect(sandbox_id=...)` attach contract — used by **leaf workers** (during execution) **and** by smoke criteria (during evaluation, via the parent task's sandbox kept alive per `sandbox-lifetime-covers-criteria`).
- `WorkerOutput(output, success, metadata)` shape.
- `type_slug` registration flow (via `tests/e2e/_fixtures/__init__.py`).
- `TaskManagementService.plan_subtasks` service call — this is the same service-layer entry point a production worker eventually reaches, after its toolkit tool is invoked.
- Per-leaf sandbox acquisition, resource publication from `/workspace/final_output/`, per-criterion evaluation row write.
- **Criterion-side sandbox attach** (not acquisition) — proves the env toolchain is healthy at evaluation time without violating [`rfcs/accepted/2026-04-17-criterion-runtime-di-container.md`](../../../rfcs/accepted/2026-04-17-criterion-runtime-di-container.md) (criteria never construct sandboxes).

#### What smoke deliberately skips

- **LLM agent loop.** Zero calls to any model; `model=None` is accepted and ignored.
- **Pydantic-AI toolkits** (`GraphToolkit`, `ResearchRubricsToolkit`, `SubtaskLifecycleToolkit`, …). Toolkits exist to mediate between an LLM's tool calls and Ergon services. With no LLM, a toolkit buys nothing and would force us to invent a deterministic fake agent loop. `SmokeWorkerBase` calls `TaskManagementService.plan_subtasks` **directly** instead — one call hop below where a toolkit tool would land.
- **Tool-call message shape.** Real workers stream tool-call / tool-return turns interleaved with text. Smoke yields text-only `GenerationTurn`s. Code paths that specifically parse tool-call turn parts are not exercised here.
- **LLM response parsing / retry / budget logic.** Owned by `tests/real_llm/`.

#### Coverage owner matrix

Use this to decide where a regression should be caught.

| Code path | Smoke (this tier) | Integration | Real-LLM |
|---|:---:|:---:|:---:|
| `Worker.execute` async generator consumed | ✅ | ✅ | ✅ |
| Multi-turn persistence (`GenerationTurn` rows) | ✅ (3 parent + 2 × 9 = 21 turns/run) | partial (services called directly) | ✅ |
| `TaskManagementService.plan_subtasks` DB effects | ✅ | ✅ | ✅ |
| Per-subtask sandbox acquisition at volume | ✅ (81/PR) | ❌ | ✅ |
| **Env toolchain health in sandbox** (Lean / Python / bash) | ✅ (per-env `_verify_sandbox_setup`) | ❌ | partial (only exercised if LLM happens to hit it) |
| Sandbox lifetime covers criterion (RFC) | ✅ (criterion attaches to task's sandbox) | ❌ | ✅ |
| **Sandbox command WAL emits per `sandbox.commands.run`** | ✅ (`_assert_sandbox_command_wal` per run) | partial | ✅ |
| **Sandbox lifecycle events** (`sandbox_created`/`_command`/`_closed`) fire end-to-end | ✅ (`_assert_sandbox_lifecycle_events`) | ❌ | ✅ |
| **`CommunicationService.save_message` round-trips to `ThreadMessage` rows** | ✅ (first caller of a currently-dead service) | ❌ | possible |
| **ThreadMessage `sequence_num` per-thread monotonicity** | ✅ (9 per happy run / 8 per sad run) | ❌ | ❌ |
| **Partial work persists on FAILED leaf** (partial file + pre-fail WAL) | ✅ (sad-path driver) | ❌ | ❌ |
| **Static-sibling failure cascade** (l_3 blocked when l_2 fails) | ✅ (sad-path driver) | partial | ❌ |
| **Blob-store round-trip byte fidelity** | ✅ (`_assert_blob_roundtrip` on 1 leaf/run) | ❌ | ❌ |
| **Temporal ordering honours DAG deps** (d_join.started ≥ max(d_left, d_right).completed) | ✅ (`_assert_temporal_ordering`) | ❌ | ❌ |
| **Cohort-key membership** (3 runs visible on `/cohort/{key}`) | ✅ (`_assert_cohort_membership`) | ❌ | partial |
| Graph toolkit tool → service wiring | ❌ | ✅ (toolkit unit/integration tests) | ✅ |
| LLM tool-call turn part persisted correctly | ❌ | ❌ | ✅ |
| LLM retry / budget / provider failover | ❌ | ❌ | ✅ |

The ❌ cells are not gaps in smoke's design; they are the *reason* we run three tiers instead of one.

#### Why multi-turn matters (and why we didn't just yield one)

A prior revision of this plan had `SmokeWorkerBase.execute` yield a single terminal turn. That would have silently skipped incremental turn persistence — `GenerationTurnRepository`, `RunContextEvent` sequence numbers, and per-turn dashboard deltas only trigger once per turn. Bumping to 3 parent + 2 leaf turns is the cheapest way to put those paths on the hot smoke path without introducing a fake agent loop.

Driver-side invariant (asserted per run in [`02-drivers-and-asserts.md`](02-drivers-and-asserts.md)):

> For a run with 1 parent × 3 turns + 9 leaves × 2 turns, total `GenerationTurn` rows = **21**.

If we ever change `PARENT_TURN_COUNT` or `LEAF_TURN_COUNT`, the driver assertion changes in lock-step. These are `ClassVar`s on the base classes (§2.3, §2.4) so the driver imports them rather than hardcoding `21`.

### 2.7 Data flow — how criteria get their inputs

Two independent channels feed the criterion. Understanding which channel carries which check is how we avoid conflating "leaf output correct" with "env toolchain healthy."

#### Channel A: blob storage (for leaf artifact checks)

```
Leaf worker in sandbox
  │
  │  writes /workspace/final_output/<file> (report_<node>.md, probe_<node>.json, …)
  ▼
Runtime persist_outputs step (Inngest)
  │
  │  scans /workspace/final_output/, hashes bytes, uploads blob, writes
  │  RunResource(run_id, node_id, name, content_hash) row
  ▼
Sandbox is torn down (or repurposed)
  │
  ▼
Criterion.evaluate()
  │
  │  _pull_probe_results:  SELECT RunResource WHERE name LIKE 'probe_%.json'
  │                        → BlobClient.default().get(content_hash) → bytes
  │                        → json.loads → exit code + stdout
  │
  │  _verify_env_content:  SELECT RunResource WHERE name LIKE '<env>_%.<ext>'
  │                        → BlobClient.default().get(content_hash) → bytes
  │                        → content assertions
```

No sandbox access needed. Works even if every sandbox is already gone.

#### Channel B: sandbox attach (for env-health check)

```
Parent task's sandbox is kept alive by the runtime, per
  docs/rfcs/accepted/2026-04-17-sandbox-lifetime-covers-criteria.md
  │
  │  (leaves had their own sandboxes; those are gone.
  │   The parent's sandbox persists through evaluation.)
  ▼
Criterion.evaluate() → _verify_sandbox_setup()
  │
  │  sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
  │  # context.sandbox_id comes from the CriterionRuntime DI container per
  │  # docs/rfcs/accepted/2026-04-17-criterion-runtime-di-container.md
  │
  │  await sandbox.commands.run("<env-specific health probe>")
  │  # Lean:   lean --check /tmp/smoke_health.lean
  │  # Python: python /tmp/smoke_health.py && python -c 'import pytest; …'
  │  # Bash:   echo … | wc -l
  │
  │  assert exit_code == 0
  ▼
Criterion returns CriterionResult(score=1.0) iff both channels passed.
```

The criterion does not own the sandbox's lifecycle. It attaches, runs a command, and returns. The runtime tears the sandbox down after `evaluate()` completes.

#### Which channel catches which regression?

| Regression | Channel A (artifacts) | Channel B (sandbox) |
|---|:---:|:---:|
| Leaf wrote wrong content | ✅ | — |
| Leaf didn't write the file at all | ✅ | — |
| Probe JSON missing / malformed | ✅ | — |
| Lean toolchain silently broken (probe's `\|\| true` masked it) | ❌ | ✅ |
| Python interpreter missing `pytest` | ❌ | ✅ |
| Sandbox image regressed (PATH wrong, `/tmp` read-only) | partial | ✅ |
| Sandbox-lifetime RFC regressed (sandbox torn down too early) | — | ✅ (criterion fails attach) |

Having both channels means a silent leaf probe failure cannot mask a toolchain break, and a toolchain break cannot be disguised by a leaf writing a plausible-looking artifact.

#### Lifecycle dependency — and the final step of this program

Channel B relies on the parent task's sandbox staying alive through criterion execution. That guarantee is RFC [`2026-04-17-sandbox-lifetime-covers-criteria`](../../../rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md), which ships as two coordinated changes:

1. **Timeout split** — `BaseSandboxManager.create()` takes `task_timeout_minutes + max_criterion_timeout_minutes`, provisions their sum to E2B. Ensures the sandbox is not killed by E2B mid-criterion.
2. **`BaseSandboxManager.reconnect(sandbox_id)`** — the blessed cross-process reconnect path. `CriterionRuntime.ensure_sandbox()` uses it to hand a live sandbox handle to the criterion, so the criterion can run its commands with the sandbox held open for the entire evaluation.

In the sketches above, `_verify_sandbox_setup` calls `AsyncSandbox.connect(sandbox_id=context.sandbox_id)` directly. That works end-to-end and is fine as an interim, but it violates [`sandbox_lifecycle.md`](../../../architecture/cross_cutting/sandbox_lifecycle.md) invariant 3 ("Criteria MUST reconnect via the manager"). The invariant exists so event emission, template pinning, and expiry-error translation all flow through one path.

**The final step of this test-refactor program is landing the `reconnect` path so smoke criteria — and every production criterion — reconnect to the task's sandbox through the manager and hold it open for the duration of evaluation.** That's Phase G in [`06-phases.md`](06-phases.md). Once it ships, the only change in smoke criteria is swapping the one-liner:

```python
# before (interim, used in Phases C–F):
sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)

# after (Phase G):
sandbox = await context.get_sandbox()   # or whatever the DI accessor is named
```

And `sandbox_lifecycle.md` invariant 3 flips from "pending enforcement" to "enforced end-to-end by smoke on every PR."

### 2.7 `_fixtures/__init__.py` — registration hook

```python
# tests/e2e/_fixtures/__init__.py
"""Test-only registration hook.

Importing this package registers the 9 smoke workers + criteria into the
process-level builtins registry. Production CLI paths do not import this
package, so registrations are confined to test runtimes.
"""

from ergon_core.api.registry import registry

from tests.e2e._fixtures.workers.researchrubrics_smoke import (
    ResearchRubricsSmokeWorker, ResearchRubricsSmokeLeafWorker,
)
from tests.e2e._fixtures.workers.minif2f_smoke import (
    MiniF2FSmokeWorker, MiniF2FSmokeLeafWorker,
)
from tests.e2e._fixtures.workers.swebench_smoke import (
    SweBenchSmokeWorker, SweBenchSmokeLeafWorker,
)
from tests.e2e._fixtures.criteria.researchrubrics_smoke import (
    ResearchRubricsSmokeCriterion,
)
from tests.e2e._fixtures.criteria.minif2f_smoke import MiniF2FSmokeCriterion
from tests.e2e._fixtures.criteria.swebench_smoke import SweBenchSmokeCriterion


def register_smoke_fixtures() -> None:
    for cls in (
        ResearchRubricsSmokeWorker, ResearchRubricsSmokeLeafWorker,
        MiniF2FSmokeWorker, MiniF2FSmokeLeafWorker,
        SweBenchSmokeWorker, SweBenchSmokeLeafWorker,
    ):
        registry.register_worker(cls)
    for cls in (
        ResearchRubricsSmokeCriterion,
        MiniF2FSmokeCriterion,
        SweBenchSmokeCriterion,
    ):
        registry.register_criterion(cls)


register_smoke_fixtures()
```

Exact call names (`registry.register_worker`, `register_criterion`) must match the current registry API in `ergon_core/api/registry.py` — if today's API uses decorators, the hook adapts to that. This is a shape not a contract.

**Session-entry:** `tests/e2e/conftest.py` does `import tests.e2e._fixtures  # noqa: F401` at module scope.

---

## 3. Per-env fixtures

### 3.1 ResearchRubrics

`tests/e2e/_fixtures/workers/researchrubrics_smoke.py`

```python
import json

from e2b_code_interpreter import AsyncSandbox

from tests.e2e._fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from tests.e2e._fixtures.smoke_base.subworker import SmokeSubworker, SubworkerResult
from tests.e2e._fixtures.smoke_base.worker_base import SmokeWorkerBase


class ResearchRubricsSmokeWorker(SmokeWorkerBase):
    type_slug = "researchrubrics-smoke-worker"
    leaf_slug = "researchrubrics-smoke-leaf"


class ResearchRubricsSubworker:  # implements SmokeSubworker structurally
    """Writes a deterministic markdown report + runs `wc -l` as the probe."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        path = f"/workspace/final_output/report_{node_id}.md"
        contents = (
            f"# Research report {node_id}\n\n"
            "Deterministic smoke output. Non-empty body required.\n"
        )
        await sandbox.files.write(path, contents)
        probe = await sandbox.commands.run(f"wc -l {path}", timeout=10)
        probe_stdout = probe.stdout.strip()
        # Persist probe JSON as an artifact the criterion will read.
        probe_path = f"/workspace/final_output/probe_{node_id}.json"
        await sandbox.files.write(
            probe_path,
            json.dumps({"exit_code": probe.exit_code, "stdout": probe_stdout}),
        )
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe_stdout,
            probe_exit_code=probe.exit_code,
        )


class ResearchRubricsSmokeLeafWorker(BaseSmokeLeafWorker):
    type_slug = "researchrubrics-smoke-leaf"
    subworker_cls = ResearchRubricsSubworker
```

`tests/e2e/_fixtures/criteria/researchrubrics_smoke.py`

```python
from typing import Any
from uuid import UUID

from ergon_core.api import CriteriaCheckError
from ergon_core.core.persistence.graph.models import RunGraphNode
from ergon_core.core.persistence.resources.models import RunResource
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.providers.blob.client import BlobClient

from tests.e2e._fixtures.smoke_base.criterion_base import SmokeCriterionBase


class ResearchRubricsSmokeCriterion(SmokeCriterionBase):
    type_slug = "researchrubrics-smoke-criterion"

    async def _verify_env_content(
        self, context, children: list[RunGraphNode],
        probes: dict[UUID, dict[str, Any]],
    ) -> None:
        for child in children:
            report = await _read_artifact(child.id, name_like="report_%.md")
            if not report.startswith(b"# Research report"):
                raise CriteriaCheckError(
                    f"{child.task_slug}: report missing `# Research report` header",
                )
            if len(report.strip()) < 20:
                raise CriteriaCheckError(
                    f"{child.task_slug}: report body too short ({len(report)} bytes)",
                )

    async def _verify_sandbox_setup(self, context) -> None:
        """Trivial env probe: bash + coreutils are present and produce
        expected output. Catches researchrubrics sandbox image regressions
        (e.g. missing `wc`, broken PATH, no /tmp write access).

        Attaches to the parent task's sandbox — same sandbox the parent
        worker ran in, kept alive by the runtime for criterion execution.
        """
        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
        # Exercise the 3 things a researchrubrics leaf actually needs:
        # write to tmp, run wc, and sh exit-code propagation.
        result = await sandbox.commands.run(
            "set -e; "
            "echo '# hello world' > /tmp/smoke_health.md && "
            "test \"$(wc -l < /tmp/smoke_health.md)\" = '1' && "
            "echo OK",
            timeout=10,
        )
        if result.exit_code != 0 or "OK" not in result.stdout:
            raise CriteriaCheckError(
                f"researchrubrics sandbox health failed: "
                f"exit={result.exit_code} stdout={result.stdout[:200]!r}",
            )
```

`_read_artifact` is a small helper colocated in the criterion module.

### 3.2 MiniF2F

`tests/e2e/_fixtures/workers/minif2f_smoke.py`

```python
LEAN_SOURCE = """\
theorem smoke_trivial : 1 + 1 = 2 := by norm_num
"""


class MiniF2FSmokeWorker(SmokeWorkerBase):
    type_slug = "minif2f-smoke-worker"
    leaf_slug = "minif2f-smoke-leaf"


class MiniF2FSubworker:
    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        path = f"/workspace/final_output/proof_{node_id}.lean"
        await sandbox.files.write(path, LEAN_SOURCE)
        probe = await sandbox.commands.run(
            f"lean --check {path} || true",  # smoke-level: we want file parse, not full kernel
            timeout=20,
        )
        probe_path = f"/workspace/final_output/probe_{node_id}.json"
        await sandbox.files.write(
            probe_path,
            json.dumps({"exit_code": probe.exit_code, "stdout": probe.stdout[:4096]}),
        )
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout.strip()[:4096],
            probe_exit_code=probe.exit_code,
        )


class MiniF2FSmokeLeafWorker(BaseSmokeLeafWorker):
    type_slug = "minif2f-smoke-leaf"
    subworker_cls = MiniF2FSubworker
```

`tests/e2e/_fixtures/criteria/minif2f_smoke.py`

```python
from e2b_code_interpreter import AsyncSandbox

HEALTH_THEOREM = """\
theorem health_check : 1 + 1 = 2 := by norm_num
"""


class MiniF2FSmokeCriterion(SmokeCriterionBase):
    type_slug = "minif2f-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        for child in children:
            source = await _read_artifact(child.id, name_like="proof_%.lean")
            text = source.decode("utf-8")
            if "theorem smoke_trivial" not in text:
                raise CriteriaCheckError(
                    f"{child.task_slug}: lean source missing theorem marker",
                )
            if ":=" not in text:
                raise CriteriaCheckError(
                    f"{child.task_slug}: lean source missing proof term `:=`",
                )

    async def _verify_sandbox_setup(self, context) -> None:
        """Compile a trivial theorem. Proves the Lean toolchain, Mathlib
        (for `norm_num`), and the sandbox's elan / `lean` wrapper are all
        wired up. This is the difference between "a file with `.lean` got
        written" and "Lean can actually typecheck in this image."

        Attaches to the parent task's sandbox; Lean is probably warm by
        now since the 9 leaves just ran against the same toolchain.
        """
        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
        path = "/tmp/smoke_health.lean"
        await sandbox.files.write(path, HEALTH_THEOREM)
        result = await sandbox.commands.run(
            f"lean --check {path}",  # no `|| true` — we want the real exit code
            timeout=60,               # generous; Lean should be warm post-leaves
        )
        if result.exit_code != 0:
            raise CriteriaCheckError(
                f"minif2f sandbox health failed: lean --check "
                f"exit={result.exit_code} "
                f"stdout={result.stdout[:300]!r} "
                f"stderr={result.stderr[:300]!r}",
            )
```

**Probe choice note (leaf side):** the `MiniF2FSubworker` leaf probe uses `lean --check || true` to keep leaf probe exit deterministic during first-boot toolchain warmup; the *criterion-side* health probe runs without `|| true` so a genuinely broken toolchain fails loudly. If the criterion-side probe is consistently slow, trim `HEALTH_THEOREM` to avoid `norm_num` / `Mathlib` — `theorem health_check : True := trivial` imports nothing and compiles in under a second.

### 3.3 SWE-Bench Verified

`tests/e2e/_fixtures/workers/swebench_smoke.py`

```python
PY_SOURCE = """\
def add(a, b):
    return a + b

if __name__ == "__main__":
    assert add(2, 3) == 5
"""


class SweBenchSmokeWorker(SmokeWorkerBase):
    type_slug = "swebench-smoke-worker"
    leaf_slug = "swebench-smoke-leaf"


class SweBenchSubworker:
    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        path = f"/workspace/final_output/patch_{node_id}.py"
        await sandbox.files.write(path, PY_SOURCE)
        probe = await sandbox.commands.run(
            f"python -m py_compile {path} && python {path}", timeout=20,
        )
        probe_path = f"/workspace/final_output/probe_{node_id}.json"
        await sandbox.files.write(
            probe_path,
            json.dumps({"exit_code": probe.exit_code, "stdout": probe.stdout[:4096]}),
        )
        return SubworkerResult(
            file_path=path,
            probe_stdout=probe.stdout.strip()[:4096],
            probe_exit_code=probe.exit_code,
        )


class SweBenchSmokeLeafWorker(BaseSmokeLeafWorker):
    type_slug = "swebench-smoke-leaf"
    subworker_cls = SweBenchSubworker
```

`tests/e2e/_fixtures/criteria/swebench_smoke.py`

```python
import ast


HEALTH_PY = """\
import sys
assert sys.version_info >= (3, 10), sys.version_info
print("HEALTH_OK")
"""


class SweBenchSmokeCriterion(SmokeCriterionBase):
    type_slug = "swebench-smoke-criterion"

    async def _verify_env_content(self, context, children, probes) -> None:
        for child in children:
            source = await _read_artifact(child.id, name_like="patch_%.py")
            try:
                tree = ast.parse(source.decode("utf-8"))
            except SyntaxError as e:
                raise CriteriaCheckError(f"{child.task_slug}: python AST parse failed: {e}")
            func_names = [
                node.name for node in ast.walk(tree) if isinstance(node, ast.FunctionDef)
            ]
            if "add" not in func_names:
                raise CriteriaCheckError(
                    f"{child.task_slug}: expected function `add`, got {func_names}",
                )

    async def _verify_sandbox_setup(self, context) -> None:
        """Proves Python 3.10+ is present, exits cleanly, and `pytest` is
        importable. These are the three things every swebench-verified leaf
        assumes about its sandbox image; surface regressions here instead of
        at evaluation time deep inside the runner.

        Attaches to the parent task's sandbox (kept alive for the criterion
        per RFC `sandbox-lifetime-covers-criteria`).
        """
        sandbox = await AsyncSandbox.connect(sandbox_id=context.sandbox_id)
        path = "/tmp/smoke_health.py"
        await sandbox.files.write(path, HEALTH_PY)
        # Two cheap checks rolled into one command:
        #   1. python runs and reports HEALTH_OK
        #   2. pytest is importable (no test discovery)
        result = await sandbox.commands.run(
            f"python {path} && python -c 'import pytest; print(pytest.__version__)'",
            timeout=15,
        )
        if result.exit_code != 0 or "HEALTH_OK" not in result.stdout:
            raise CriteriaCheckError(
                f"swebench sandbox health failed: "
                f"exit={result.exit_code} "
                f"stdout={result.stdout[:300]!r} "
                f"stderr={result.stderr[:300]!r}",
            )
```

### 3.4 Sad-path fixtures — researchrubrics cohort slot 3

The researchrubrics leg's cohort-of-3 is 2 happy + 1 sad. The sad slot uses `ResearchRubricsSadPathSmokeWorker`, which routes `l_2` through a failing leaf; the rest of the 9-subtask topology is unchanged. No separate matrix leg; no additional top-level run; no separate driver file. MiniF2F + SWE-bench cohorts stay 3-happy.

Invariants the sad slot exercises:

- **Partial work persists on FAILED leaf.** The failing subworker does real work (file write + sandbox command) **before** raising. Driver asserts the partial artifact landed as a `RunResource` and the pre-failure command emitted a WAL entry.
- **Static sibling failure semantics.** Line cascade (`l_1 → l_2 → l_3`) with l_2 forced to FAIL; `l_3` must end up BLOCKED/CANCELLED per [`rfcs/active/2026-04-17-static-sibling-failure-semantics.md`](../../../rfcs/active/2026-04-17-static-sibling-failure-semantics.md). Diamond + singletons in the same run must be unaffected.
- **Completion message suppression.** Sad-path leaf raises before reaching `_send_completion_message`, so exactly 8 ThreadMessages (not 9) exist on the smoke-completion thread for this run.

Fixtures live under `tests/e2e/_fixtures/`:

```python
# tests/e2e/_fixtures/workers/researchrubrics_smoke_sadpath.py

from e2b_code_interpreter import AsyncSandbox

from tests.e2e._fixtures.smoke_base.leaf_base import BaseSmokeLeafWorker
from tests.e2e._fixtures.smoke_base.subworker import SmokeSubworker, SubworkerResult
from tests.e2e._fixtures.smoke_base.worker_base import SmokeWorkerBase
from ergon_core.core.persistence.shared.types import AssignedWorkerSlug, TaskSlug
from ergon_core.core.runtime.services.task_management_dto import SubtaskSpec


class AlwaysFailSubworker:
    """Does TWO units of real work, then raises.

    Purpose: exercise the partial-work-persists-on-failure path. We want to
    prove that when a leaf fails mid-execution:

      1. Files it already wrote to /workspace/final_output/ still become
         RunResource rows (runtime persist step runs regardless of worker
         exit outcome).
      2. Sandbox commands it already ran still emit sandbox_command events
         + WAL entries (the command path writes synchronously).
      3. The leaf's own task row ends up FAILED (exception propagates).
      4. Downstream static siblings (l_3) end up BLOCKED/CANCELLED.
    """

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        # Action 1: write a partial artifact — must land as RunResource.
        partial_path = f"/workspace/final_output/partial_{node_id}.md"
        await sandbox.files.write(
            partial_path,
            (
                f"# Partial work {node_id}\n\n"
                "This content was written before a deliberate failure. "
                "If smoke sees this as a RunResource row, partial serialization works.\n"
            ),
        )

        # Action 2: run a sandbox command — must emit sandbox_command + WAL row.
        pre_check = await sandbox.commands.run(
            f"wc -l {partial_path}",
            timeout=5,
        )
        if pre_check.exit_code != 0:
            raise RuntimeError(
                f"AlwaysFailSubworker: precondition failed — expected wc to succeed "
                f"but got exit={pre_check.exit_code}. The sad-path design assumes "
                f"partial work completes cleanly before the deliberate raise.",
            )

        # Action 3: deliberate failure. Raises instead of returning exit_code=1
        # so the leaf task row is marked FAILED (not merely produces a failed
        # WorkerOutput).
        raise RuntimeError(
            f"SmokeSadPathError: deliberate failure of {node_id} after "
            f"writing {partial_path} and running probe (exit={pre_check.exit_code}). "
            "Smoke asserts the partial file + probe WAL survive.",
        )


class ResearchRubricsFailingLeafWorker(BaseSmokeLeafWorker):
    """Registered leaf that always fails after doing 2 units of work."""
    type_slug = "researchrubrics-smoke-leaf-failing"
    subworker_cls = AlwaysFailSubworker


class ResearchRubricsSadPathSmokeWorker(SmokeWorkerBase):
    """Parent worker that routes `l_2` to the failing leaf, everything else normal.

    Topology stays identical (still 9 subtasks, same deps); only the leaf
    binding for l_2 differs. `execute()` is still @final; the hook is
    `_spec_for`.
    """
    type_slug = "researchrubrics-sadpath-smoke-worker"
    leaf_slug = "researchrubrics-smoke-leaf"  # default for everything EXCEPT l_2

    FAILING_SLUGS = frozenset({"l_2"})
    FAILING_LEAF_SLUG = "researchrubrics-smoke-leaf-failing"

    def _spec_for(self, slug: str, deps: tuple[str, ...], desc: str) -> SubtaskSpec:
        leaf_slug = (
            self.FAILING_LEAF_SLUG if slug in self.FAILING_SLUGS else self.leaf_slug
        )
        return SubtaskSpec(
            task_slug=TaskSlug(slug),
            description=desc,
            assigned_worker_slug=AssignedWorkerSlug(leaf_slug),
            depends_on=[TaskSlug(d) for d in deps],
        )
```

Register these in `_fixtures/__init__.py` alongside the happy-path fixtures:

```python
from tests.e2e._fixtures.workers.researchrubrics_smoke_sadpath import (
    ResearchRubricsSadPathSmokeWorker,
    ResearchRubricsFailingLeafWorker,
)

# inside register_smoke_fixtures():
registry.register_worker(ResearchRubricsSadPathSmokeWorker)
registry.register_worker(ResearchRubricsFailingLeafWorker)
```

**No new criterion** for sad-path. The existing `ResearchRubricsSmokeCriterion` is reused; it will return a failed `CriterionResult` because `_check_children_completed` sees `l_2 != COMPLETED`, `l_3 != COMPLETED`. That's the correct outcome — we don't invent a new criterion, we prove the happy-path criterion correctly rejects a partially-failed run.

---

## 4. Benchmarks

No changes to the three production benchmarks' `Benchmark` subclasses. The existing `ResearchRubricsBenchmark`, `MiniF2FBenchmark`, `SweBenchVerifiedBenchmark` are used as-is.

Smoke submission passes `--worker {env}-smoke-worker --evaluator {env}-smoke-criterion` against the existing benchmark slug. The benchmark's own sandbox image is used; smoke does not provision a separate image.

The three existing `smoke_rubric.py` files in `ergon_builtins/benchmarks/{env}/` are **deleted**; smoke no longer uses rubric composition. Criterion is passed directly by slug.

---

## 5. Worker ABC contract expectations

Double-check against current code before coding:

- `Worker.__init__(self, *, name, model, task_id, sandbox_id)`.
- `Worker.execute(self, task, *, context)` returns `AsyncGenerator[GenerationTurn, None]`.
- `Worker.get_output(self, context)` returns `WorkerOutput(output, success, metadata)`.
- `WorkerContext` exposes `run_id`, `node_id`, `sandbox_id`, `execution_id`.
- `Criterion` subclasses set `type_slug: ClassVar[str]` and implement `async evaluate(context) -> CriterionResult`.
- `EvaluationContext` exposes `execution_id` (plus whatever `_pull_children` needs).

If any of these has moved by the time of the PR, the sketches must be updated; the invariants (no LLM, 9-subtask plan, sandbox connect by id, probe JSON artifact, env content check) remain.

---

## 6. Unit test coverage for these fixtures

Every class above gets a unit test under `tests/unit/` (no fixtures from `_fixtures/__init__.py` — unit tests construct classes directly):

| Test | What it asserts |
|---|---|
| `tests/unit/test_smoke_worker_base_final.py` | `SmokeWorkerBase.execute` is `@final`; subclass cannot override |
| `tests/unit/test_smoke_worker_plans_9_subtasks.py` | Parent plans exactly the 9 expected slugs with correct `depends_on` (using a fake `plan_subtasks` recorder) |
| `tests/unit/test_smoke_worker_turn_count.py` | Parent yields exactly `PARENT_TURN_COUNT` (3) turns, in order: planning → planned → awaiting |
| `tests/unit/test_smoke_leaf_turn_count.py` | Leaf yields exactly `LEAF_TURN_COUNT` (2) turns, in order: attaching → done |
| `tests/unit/test_base_smoke_leaf.py` | Existing test — retarget to new import path |
| `tests/unit/test_smoke_criterion_shape.py` | `_check_graph_shape` raises on missing/extra slugs |
| `tests/unit/test_smoke_criterion_completed.py` | `_check_children_completed` raises on non-COMPLETED child |
| `tests/unit/test_smoke_criterion_probe.py` | `_check_probes_succeeded` raises on non-zero exit |
| `tests/unit/test_env_criterion_verify_content.py` × 3 | `_verify_env_content` per env (fixture bytes in, pass/fail out) |
| `tests/unit/test_env_criterion_sandbox_setup.py` × 3 | `_verify_sandbox_setup` per env using a fake `AsyncSandbox` that records commands and returns canned `CommandResult`s. Asserts: (a) criterion calls `connect(sandbox_id=...)` with `context.sandbox_id`, (b) passes if exit_code==0 + expected marker present, (c) raises `CriteriaCheckError` on non-zero exit. **Never** exercises real E2B — kept to unit tier. |
| `tests/unit/test_registry_smoke_entries.py` | After import of `tests.e2e._fixtures`, registry contains exactly the 11 expected slugs (9 happy-path + `researchrubrics-sadpath-smoke-worker` + `researchrubrics-smoke-leaf-failing`) and none of the retired slugs |
| `tests/unit/test_smoke_worker_spec_for_override.py` | `SmokeWorkerBase._spec_for` is called for each of 9 slugs; default returns `self.leaf_slug`; sad-path subclass routes only `l_2` to failing leaf |
| `tests/unit/test_always_fail_subworker.py` | `AlwaysFailSubworker.work` — using a fake `AsyncSandbox` recorder — (a) writes partial file, (b) runs `wc -l`, (c) raises `RuntimeError` naming the node. Order of operations must be write-then-probe-then-raise (not probe-then-write) so partial artifact is guaranteed persisted before the raise |
| `tests/unit/test_leaf_sends_completion_message.py` | `BaseSmokeLeafWorker._send_completion_message` is invoked exactly once per happy-path `execute`, with `from_agent_id == f"leaf-{task_slug}"`, `to_agent_id == "parent"`, `thread_topic == "smoke-completion"`. Uses a fake `communication_service.save_message` recorder |
| `tests/unit/test_failing_leaf_skips_message.py` | `BaseSmokeLeafWorker.execute` raises before reaching `_send_completion_message` when subworker raises — asserts recorder has ZERO calls on the failing leaf path |

These unit tests run in `ci-fast` and don't need Docker. They catch 80% of regressions before we pay for an e2e matrix leg.

# 04 — Walkthrough: linear DAG, 4 tasks, 4 workers

> Concrete trace through the proposed model — author writes a script,
> definition lands in Postgres, container loads and runs. **This is the
> single source of truth for "what running end-to-end looks like."** Other
> docs in this folder describe shapes; this doc describes flow.
>
> Smells the trace surfaces are flagged in
> [`08-decisions-log.md#smells-the-walkthrough-surfaces`](08-decisions-log.md#smells-the-walkthrough-surfaces).

## Stage 1 — author API (in the user's process)

```python
from collections.abc import Mapping

from ergon_core.api import (
    Benchmark, Task, Sandbox, Worker, Criterion, Evaluator, Rubric,
    CriterionOutcome, Experiment, WeightedCriterion,
)
from ergon_builtins.workers import ReActWorker
from ergon_builtins.toolkits import (
    ResearchToolkit, PythonCodingToolkit, ReadOnlyFilesystemToolkit,
)
from ergon_builtins.sandboxes import (
    ResearchE2BSandbox, PythonSandbox,    # concrete Sandbox subclasses
)
# Note: toolkit and sandbox subclass imports come from ergon_builtins.
# `ergon_core.api` exports the abstract `Sandbox` base; concrete kinds
# live with the templates / setup logic that defines them.

class FourStepBench(Benchmark):
    type_slug = "four-step"

    def __init__(
        self, *,
        workers: Mapping[str, Worker],
        default_evaluator: Evaluator,
    ) -> None:
        self.workers = workers
        self.default_evaluator = default_evaluator

    def build_instances(self):
        return {
            "sample-1": [
                Task(
                    task_slug="research",
                    instance_key="sample-1",
                    description="Research the topic; write findings.md.",
                    worker=self.workers["researcher"],
                    sandbox=ResearchE2BSandbox(),
                    evaluators=(self.default_evaluator,),
                ),
                Task(
                    task_slug="code",
                    instance_key="sample-1",
                    description="Implement based on findings.md.",
                    worker=self.workers["coder"],
                    sandbox=PythonSandbox(pip_packages=("pandas", "requests")),
                    parent_task_slug="research",
                    dependency_task_slugs=("research",),
                    evaluators=(self.default_evaluator,),
                ),
                Task(
                    task_slug="review",
                    instance_key="sample-1",
                    description="Review the implementation; write review.md.",
                    worker=self.workers["reviewer"],
                    sandbox=PythonSandbox(),
                    parent_task_slug="code",
                    dependency_task_slugs=("code",),
                    evaluators=(self.default_evaluator,),
                ),
                Task(
                    task_slug="summarize",
                    instance_key="sample-1",
                    description="Summarize the prior three steps.",
                    worker=self.workers["summarizer"],
                    # Summarizer needs to read the prior tasks' resources; uses
                    # PythonSandbox so it can list and read the staged files.
                    # See decisions-log smell #1 about how cross-task data
                    # actually arrives in this sandbox.
                    sandbox=PythonSandbox(),
                    parent_task_slug="review",
                    dependency_task_slugs=("review",),
                    evaluators=(self.default_evaluator,),
                ),
            ]
        }

class AlwaysPass(Criterion):
    type_slug = "always-pass"
    slug: str = "always-pass"
    description: str = "Always passes (placeholder)."

    async def evaluate(self, *, task, worker_output, context, sandbox):
        return CriterionOutcome(slug=self.slug, name=self.slug,
                                 score=1.0, passed=True)

default_evaluator = Rubric(
    name="default",
    criteria=[WeightedCriterion(criterion=AlwaysPass(), weight=1.0)],
)

experiment = Experiment(
    benchmark=FourStepBench(
        workers={
            "researcher": ReActWorker(
                name="researcher", model="openai:gpt-4o",
                system_prompt="...", max_iterations=20,
                toolkit=ResearchToolkit(max_search_results=10),
            ),
            "coder": ReActWorker(
                name="coder", model="openai:gpt-4o",
                system_prompt="...", max_iterations=30,
                toolkit=PythonCodingToolkit(),
            ),
            "reviewer": ReActWorker(
                name="reviewer", model="anthropic:claude-sonnet-4",
                system_prompt="...", max_iterations=15,
                toolkit=PythonCodingToolkit(),  # same toolkit, different model + prompt
            ),
            "summarizer": ReActWorker(
                name="summarizer", model="openai:gpt-4o-mini",
                system_prompt="...", max_iterations=5,
                toolkit=ReadOnlyFilesystemToolkit(),
            ),
        },
        default_evaluator=default_evaluator,
    ),
)
experiment.validate()
handle = ExperimentService().persist_definition(experiment)
result = await ExperimentService().run_experiment(
    ExperimentRunRequest(experiment_id=handle.definition_id, wait=True),
)
```

**Author writes zero IDs.** Tasks get `task_id` at materialization, sandboxes
get `_runtime` at allocation, the framework owns identity throughout.

## Stage 2 — persisted to Postgres (in the API process)

`experiment.persist_definition()` decomposes into rows. Sketched as JSON
(real columns are typed pydantic-validated JSONB):

```sql
-- ExperimentDefinition (one row)
{
  id: <def_uuid>,
  benchmark_json: {
    "_type": "myproj.bench:FourStepBench",
    "...": "benchmark config, if any"
  }
}

-- ExperimentDefinitionInstance (one row, instance_key="sample-1")
{ id: <inst_uuid>, experiment_definition_id: <def_uuid>, instance_key: "sample-1" }

-- ExperimentDefinitionTask (4 rows)
[
  { id: <dtid_research>, instance_id: <inst_uuid>, task_slug: "research",
    task_json: {
      "_type": "ergon_core.api:Task",
      "task_slug": "research",
      "instance_key": "sample-1",
      "description": "Research the topic; write findings.md.",
      "worker": {
        "_type": "ergon_builtins.workers:ReActWorker",
        "name": "researcher",
        "model": "openai:gpt-4o",
        "system_prompt": "...",
        "max_iterations": 20,
        "toolkit": {"_type": "ergon_builtins.toolkits:ResearchToolkit",
                    "max_search_results": 10}
      },
      "sandbox": {"_type": "ergon_builtins.sandboxes:ResearchE2BSandbox",
                  "env": {}, "timeout_seconds": null, "requires_network": true},
      "evaluators": [{
        "_type": "ergon_core.api:Rubric",
        "name": "default",
        "criteria": [{
          "_type": "ergon_core.api:WeightedCriterion",
          "weight": 1.0,
          "criterion": {"_type": "myproj.bench:AlwaysPass",
                        "slug": "always-pass", "description": "..."}
        }]
      }],
      "parent_task_slug": null,
      "dependency_task_slugs": [],
      "task_payload": {}
    }
  },
  { id: <dtid_code>,    ..., task_slug: "code",      ..., parent: "research",   deps: ["research"] },
  { id: <dtid_review>,  ..., task_slug: "review",    ..., parent: "code",       deps: ["code"]    },
  { id: <dtid_summary>, ..., task_slug: "summarize", ..., parent: "review",     deps: ["review"]  },
]
```

**Note:** no `ComponentCatalogEntry`, no `worker_slug` indirection, no
experiment-level worker/evaluator/assignment tables. Each task row
self-describes every object it needs via `_type`: task, worker, toolkit,
sandbox, evaluator, criterion. `_task_id` (PrivateAttr) is naturally absent
from the dump; ditto `_runtime` on Sandbox.

## Stage 3 — run launch (in the API process)

`run_experiment` creates one `RunRecord` and dispatches to Inngest:

```sql
RunRecord { id: <run_uuid>, definition_id: <def_uuid>, status: "running", ... }
```

The `run_started` Inngest function then **copies** every
`ExperimentDefinitionTask` row into `run_graph_nodes`, preserving each
task's `id` as the per-run `task_id`, inlining the `task_json` snapshot,
and deriving edges from `dependency_task_slugs`.

```sql
run_graph_nodes (4 rows; (run_id, task_id) is the composite PK)
[
  { run_id: <run_uuid>, task_id: <dtid_research>, parent_task_id: null,
    task_json: { ...full Task JSON, including worker + sandbox + evaluators... },
    status: "pending", … },
  { run_id: <run_uuid>, task_id: <dtid_code>,     parent_task_id: <dtid_research>,
    task_json: {...}, status: "blocked", … },
  { run_id: <run_uuid>, task_id: <dtid_review>,   parent_task_id: <dtid_code>,
    task_json: {...}, status: "blocked", … },
  { run_id: <run_uuid>, task_id: <dtid_summary>,  parent_task_id: <dtid_review>,
    task_json: {...}, status: "blocked", … },
]
```

Three important properties of this copy:

1. **Identity preservation.** `task_id` is *literally* the definition
   row's `id`. No fresh UUID is generated for static tasks at run-launch.
   The same `task_id` will recur in every future run of this definition
   (uniqued per row by `run_id`).
2. **Self-contained task snapshot.** `task_json` is copied inline so the
   run is independent of definition mutation (we don't allow it, but if
   we ever did, in-flight runs would be unaffected).
3. **Worker/evaluator JSON is part of the task snapshot.** This is the
   object-first API choice: the runtime doesn't chase binding keys or
   load pools. If authors want five cohort variants with different
   workers, they build five `Experiment` objects with normal Python
   factory functions that pass different worker objects into the
   benchmark constructor.

Then for the root task (`research`, no dependencies), the runtime fires
`sandbox_setup` then `worker_execute` with payload
`(run_id, task_id=<dtid_research>)`.

## Stage 4 — `worker_execute` for one task (in the rollout container)

```python
# Inngest job payload carries: run_id, definition_id, task_id, execution_id.
# definition_task_id and node_id are gone; task_id is the canonical
# identity that points at the (run_id, task_id) row directly.
# definition_id may stay for logging/lookup, but worker/evaluator pools
# are no longer loaded; task_json is self-contained.

with get_session() as session:
    # ── 1. Repo calls return fully inflated typed objects — no dicts. ──
    # graph_repo.node returns a typed RunGraphNodeView whose `.task` is the
    # already-inflated Task — Task.from_definition is called inside the repo
    # and never in the job body.
    node = graph_repo.node(session, run_id=payload.run_id,
                                    task_id=payload.task_id)      # RunGraphNodeView

    # ── 2. Read the directly bound worker. ──
    task   = node.task                                # already inflated
    worker = task.worker                              # already inflated

    # task.sandbox is a typed Sandbox subclass with _runtime=None
    # (e.g. for the research task, task.sandbox is a ResearchE2BSandbox).
    # task.task_id returns payload.task_id; task.evaluators is the typed
    # tuple of Evaluators bound directly to this task; worker is the
    # fully-reconstructed ReActWorker (with its toolkit field) identical
    # to the author's original instance. The job body cannot tell whether the underlying
    # task_json arrived via "copied at run-launch from a definition" or
    # "written inline by a worker that spawned this child" — and it does
    # not need to. The dict→Task conversion is fully encapsulated in the repo.

# ── 3. Provision the sandbox via the lifecycle hub. ──
sandbox = await lifecycle_hub.acquire(
    task.sandbox, run_id=payload.run_id, task_id=node.task_id,
)
# Internally calls task.sandbox.provision() (or reuses an in-process
# retry attempt). task.sandbox._runtime is now attached; task.sandbox
# IS sandbox. See 03-runtime.md "SandboxLifecycleHub" for the exact
# reattach semantics (in-process only in v1; cross-process retry
# provisions fresh).

# ── 4. Build the runtime context (framework-only ctor). ──
# WorkerContext carries `task_id` as a public field so workers can read
# `context.task_id` symmetrically with `task.task_id` (same value);
# author code that wants identity has both surfaces. The framework
# wires the service PrivateAttrs via `_for_job`.
# See 03-runtime.md "Framework-side WorkerContext construction".
context = WorkerContext._for_job(
    run_id=payload.run_id,
    task_id=node.task_id,
    execution_id=payload.execution_id,
    definition_id=payload.definition_id,
    task_mgmt=task_mgmt_service,         # constructed once per job
    task_inspect=task_inspect_service,
    resource_repo=resource_repo,
)
# NOTE: no sandbox_id here — that's on `sandbox` (passed separately).

try:
    # ── 5. Run the worker. ──
    async for chunk in worker.execute(task=task, context=context):
        await persist_event(chunk)
    await persist_worker_output(execution_id=payload.execution_id, output=worker_output)

    # ── 6. Synchronously fan out one Inngest invocation per evaluator.
    #     Each ctx.step.invoke suspends worker_execute until that
    #     evaluate_task_run invocation returns, so the sandbox stays
    #     alive throughout. The payload is id-only; the eval worker
    #     reloads task state via the same graph_repo.node call we used
    #     in stage 4, this time passing sandbox_id so task.sandbox is
    #     re-attached live in the eval worker's process. ──
    await asyncio.gather(*[
        ctx.step.invoke(
            f"eval-{i}",
            evaluate_task_run,
            TaskEvaluateRequest(
                run_id=payload.run_id,
                task_id=node.task_id,
                execution_id=payload.execution_id,
                evaluator_index=i,
            ),
        )
        for i in range(len(task.evaluators))
    ])
finally:
    # ── 7. Settle the task; tear down sandbox; mark dependents unblocked.
    #     Release runs only after every step.invoke has returned. Eval
    #     workers never reach this branch — they only call sandbox.detach(),
    #     dropping their local _runtime while leaving the external
    #     sandbox alive for any sibling invocation still running. ──
    await lifecycle_hub.release(sandbox)   # calls sandbox.terminate()
```

The whole job is **typed-node load → provision → execute → release**.
No `session.get` in the job body, no
`import_component_string + model_validate` dance, no `Task.from_definition`
call in the job body either (it's invoked once inside `graph_repo.node`),
no registry lookup, no slug indirection, no per-benchmark sandbox manager
subclass dispatch, no template string lookup, no static/dynamic branching,
no `dict[str, Any]` ever crossing the repo boundary into the job body. Two
infrastructure concerns each have one canonical home: PG access *and*
JSON-to-typed reconstruction in the repos, and the public API surface
the job body sees is uniformly typed.

## Stage 5 — what runs next

`research` settles with `status: "completed"`. The runtime checks dependents
of `<task_uuid_research>` — finds `<task_uuid_code>`, sees its only
unsatisfied dep is now satisfied, transitions to `pending`, fires
`worker_execute` for the `coder` binding. The job's stage-4 step 3 calls
`PythonSandbox.provision()` (since `task.sandbox` is a `PythonSandbox`
this time, not a `ResearchE2BSandbox`). Same seven-step sequence. Repeat
for `review` and `summarize`.

`summarize` is technically an LLM-only task — but it picks `PythonSandbox`
in this walkthrough so it can read the prior tasks' resources from the
sandbox. (Genuinely zero-environment tasks are out of scope for this
redesign; they'll be covered when a generic `DefaultPythonSandbox` lands.
There is no no-op `Sandbox` subclass — one that satisfies the type
contract while no-op'ing `run_command` is a type-system lie we're
explicitly not shipping.)

## Stage 6 — example consumer tools (the runtime API in practice)

The 5-stage trace above shows the runtime calling `worker.execute(...)`.
What does the worker *do* inside `execute`? It uses `WorkerContext`'s
curated single-target methods for the common case, and drops to the
internal services in `core.application.*` directly for the rest. Two
example consumers, both grounded in the in-tree codebase.

### Consumer A — simple typed tool (the 90% case)

A manager worker that wants to fan out one subtask per source URL. Uses
**only** `WorkerContext` — single-target spawn, the child task is fully
object-bound, and the framework enforces containment.

```python
# ergon_builtins/tools/spawn_research_subtask.py
from typing import Literal
from pydantic import BaseModel
from ergon_core.api import Task, WorkerContext

class SpawnResearchSubtaskSuccess(BaseModel):
    kind: Literal["success"] = "success"
    task_id: str
    status: str
    model_config = {"frozen": True}

class ToolFailure(BaseModel):
    kind: Literal["failure"] = "failure"
    error: str
    model_config = {"frozen": True}

type SpawnResult = SpawnResearchSubtaskSuccess | ToolFailure


def make_spawn_research_subtask_tool(*, context: WorkerContext):
    """Build an LLM-callable tool that spawns one research subtask under
    the calling worker's task. Containment is a framework concern — the
    tool just constructs a fully-bound Task and calls context.spawn_task."""

    async def spawn_research_subtask(
        url: str, focus: str,
    ) -> SpawnResult:
        """Spawn a single researcher subtask for one URL.

        Args:
            url: The source URL the subtask should research.
            focus: One-line description of what the subtask should extract.
        """
        try:
            handle = await context.spawn_task(
                Task(
                    task_slug=f"research-{hash(url) & 0xffff:04x}",
                    instance_key=context.get_task(context.task_id).instance_key,
                    description=f"Research {url}: {focus}",
                    worker=ReActWorker(
                        name="researcher",
                        model="openai:gpt-4o",
                        system_prompt="Research this URL and write findings.",
                        max_iterations=20,
                        toolkit=ResearchToolkit(max_search_results=10),
                    ),
                    sandbox=ResearchE2BSandbox(),
                    evaluators=(),
                ),
            )
            return SpawnResearchSubtaskSuccess(
                task_id=str(handle.task_id), status="pending",
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return ToolFailure(error=str(exc))

    return spawn_research_subtask
```

What's worth noticing:

- **The child task is fully bound.** The worker object, sandbox, and
  evaluators live on the `Task`; `spawn_task` has no separate worker
  parameter and no experiment-level pool validation.
- **No subtree-membership check.** The framework enforces it inside
  `context.spawn_task` (and the other `WorkerContext` mutation
  methods). Toolkits stop carrying a TODO they had no way to actually
  solve.
- **No `ergon_core.core.*` imports.** Single-target spawn is on the
  curated surface; the tool only needs `ergon_core.api`.

### Consumer B — power tool that drops to the internal service (the escape hatch)

A manager worker that needs to atomically plan a sub-DAG of dependent
research tasks (cycles detected up-front, all-or-nothing). `plan_subtasks`
fails the `WorkerContext` curation rule (it's a batch op), so the
toolkit imports `TaskManagementService` directly. Same import path
`ergon_builtins/tools/subtask_lifecycle_toolkit.py` uses today; v1
doesn't try to relocate it.

```python
# ergon_builtins/tools/plan_research_subtasks_toolkit.py
from typing import Literal
from pydantic import BaseModel
from ergon_core.api import WorkerContext

# v1: the batch op stays on the internal service.
# Promote when there's a real third-party consumer.
from ergon_core.core.application.tasks.management import TaskManagementService
from ergon_core.core.application.tasks.models import SubtaskSpec   # slug-based

class PlanSubtasksSuccess(BaseModel):
    kind: Literal["success"] = "success"
    task_ids: dict[str, str]                # slug → task_id
    model_config = {"frozen": True}

class PlanFailure(BaseModel):
    kind: Literal["failure"] = "failure"
    error: str
    model_config = {"frozen": True}


def make_plan_research_subtasks_tool(
    *,
    context: WorkerContext,
    task_mgmt: TaskManagementService,
    research_worker: Worker,
):
    """Build a tool that atomically plans a sub-DAG of research tasks.
    Drops below WorkerContext because plan_subtasks is a batch op (fails
    the curation rule of single-target + high-frequency)."""

    async def plan_research_subtasks(
        plan: list[dict],     # [{slug, description, depends_on}]
    ) -> PlanSubtasksSuccess | PlanFailure:
        """Atomically materialise a sub-DAG. Cycles, duplicate slugs,
        and dependency references are all rejected up-front."""
        try:
            specs = [
                SubtaskSpec(
                    task=Task(
                        task_slug=item["slug"],
                        instance_key=context.get_task(context.task_id).instance_key,
                        description=item["description"],
                        worker=research_worker,
                        sandbox=ResearchE2BSandbox(),
                        evaluators=(),
                    ),
                    depends_on=list(item.get("depends_on", [])),
                )
                for item in plan
            ]
            # plan_subtasks is the internal service method. It already
            # exists and works today; v1 doesn't need to wrap it in a
            # public service class.
            result = await task_mgmt.plan_subtasks(
                run_id=context.run_id, parent_task_id=context.task_id,
                specs=specs,
            )
            return PlanSubtasksSuccess(
                task_ids={slug: str(tid) for slug, tid in result.items()},
            )
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            return PlanFailure(error=str(exc))

    return plan_research_subtasks
```

What's worth noticing:

- **The internal service import is the v1 escape hatch.** Same shape
  `ergon_builtins/tools/subtask_lifecycle_toolkit.py`,
  `ergon_builtins/tools/graph_toolkit.py`, and
  `ergon_cli/commands/workflow.py` all use today.
- **Containment is on the toolkit, not the framework.** When you
  bypass `WorkerContext`, you bypass its containment check. For
  toolkits operating on their own `(run_id, task_id)` scope (the
  common case) that's fine; for toolkits accepting target ids from an
  LLM, validate against `context.get_task(target_id)` first or do the
  descendant check yourself.
- **No public service class involved.** An earlier design wrapped this
  call site in `GraphMutator.for_worker(context).plan_subtasks(...)` —
  same shape, one extra public class, no v1 consumer that needed it.
  Promote when one shows up.

## Blast radius — files affected

What the trace above implies in code. Phase tags ([P1] / [P2] / [P3] /
[P4]) match [`09-implementation-plan.md`](09-implementation-plan.md). Paths are real as of
the current tree; verify against your branch before touching.

This is the **file-level inventory** of what changes; for the *why*
behind each ADD/DELETE pairing — i.e. "we're deleting `X` because we're
adding `Y` in the public API" — see the
[Core deduplication audit](../2026-05-08-authoring-api-redesign/05-migration.md#core-deduplication-audit).
The [Deletion checklist](../2026-05-08-authoring-api-redesign/05-migration.md#deletion-checklist-reviewer)
gives the `git grep` invocations the reviewer runs to verify nothing's
left dangling.

```
ergon/
├── ergon_core/ergon_core/
│   ├── api/                                                   # public authoring surface
│   │   ├── __init__.py                                        # MODIFY: drop TaskSpec, ComponentRegistry exports; add Sandbox, WeightedCriterion, SpawnedTaskHandle, new exception types [P1-P4]
│   │   ├── registry.py                                        # DELETE: ComponentRegistry replaced by _type discriminator + import_component_string [P1]
│   │   ├── benchmark/
│   │   │   ├── benchmark.py                                   # MODIFY: add Benchmark.from_definition classmethod [P1]
│   │   │   └── task.py                                        # MODIFY: add worker: Worker, sandbox: Sandbox, evaluators: tuple[Evaluator, ...], _task_id PrivateAttr, task_id property, from_definition classmethod; delete TaskSpec [P3]
│   │   ├── criterion/
│   │   │   ├── criterion.py                                   # MODIFY: add Criterion.from_definition [P1]; evaluate signature gains sandbox: Sandbox [P4]
│   │   │   └── context.py                                     # MODIFY: drop proxy methods; CriterionContext becomes pure data [P4]
│   │   ├── rubric/
│   │   │   ├── rubric.py                                      # MODIFY: add Rubric.from_definition [P1]; add WeightedCriterion wrapper [P4]
│   │   │   └── evaluator.py                                   # MODIFY: add Evaluator.from_definition [P1]
│   │   ├── sandbox/                                           # ADD: new public-API folder for the abstract base [P2]
│   │   │   ├── __init__.py                                    # ADD: re-export Sandbox base
│   │   │   ├── sandbox.py                                     # ADD: Sandbox(BaseModel, ABC) + _runtime PrivateAttr + abstract provision/terminate + from_definition + IO proxy methods
│   │   │   └── runtime.py                                     # ADD: SandboxRuntime protocol (the "live" backing object)
│   │   ├── worker/
│   │   │   ├── worker.py                                      # MODIFY: become BaseModel + ABC; add execute(task, *, context, sandbox); add from_definition [P1]; sandbox kwarg becomes non-optional [end of P2]
│   │   │   ├── context.py                                     # MODIFY: WorkerContext becomes BaseModel; add _task_mgmt / _task_inspect / _resource_repo PrivateAttrs; add curated single-target methods (spawn_task in step 16, then cancel_task/refine_task/restart_task + subtasks/descendants/get_task/resources in step 16a) — each delegates directly to the internal service [P3]
│   │   │   └── results.py                                     # MODIFY: add WorkerStreamItem (discriminated union); add SpawnedTaskHandle (.task_id, .wait()) — return type of WorkerContext.spawn_task [P3]
│   │   └── experiment.py                                      # ADD: canonical home of class Experiment — Pydantic BaseModel + requires_sandbox @model_validator(mode="after"); _persisted DefinitionHandle PrivateAttr. Lifted out of core.domain.experiments (audit #6) [P1]
│   ├── core/
│   │   ├── application/
│   │   │   ├── components/                                    # DELETE: whole folder dies [P1]
│   │   │   │   └── catalog.py                                 # DELETE: ComponentCatalogService → replaced by Worker/Task/etc.from_definition
│   │   │   ├── experiments/
│   │   │   │   ├── definition_writer.py                       # MODIFY: persist Worker pydantic JSON (not slug+recipe); persist Task with sandbox subclass [P1-P3]
│   │   │   │   ├── service.py                                 # MODIFY: static-on-dynamic dep validator [P3]. Note: Worker/Criterion `requires_sandbox` validation moves onto Experiment as a `@model_validator(mode="after")` (see 08-decisions-log.md "Worker → Sandbox compatibility checking"), so it fails at construction in the author's process — service-layer validation no longer needs to repeat it.
│   │   │   │   └── repository.py                              # MODIFY: add graph_repo.node returning RunGraphNodeView with task.worker/task.evaluators already inflated [P3]
│   │   │   ├── jobs/
│   │   │   │   └── worker_execute.py                          # MODIFY: RunGraphNodeView read, worker = task.worker, no import_component_string in body; inject TaskManagementService/TaskInspectionService/RunResourceRepository into WorkerContext at job start [P3]
│   │   │   ├── tasks/
│   │   │   │   ├── execution.py                               # MODIFY: rebuilt around RunGraphNodeView; no TaskSpec; no slug-based registry resolution [P3]
│   │   │   │   ├── management.py                              # MODIFY: add_subtask gains a Task-shaped path (taking task: Task directly; task carries worker/sandbox/evaluators) for WorkerContext.spawn_task [P3]. NOT made import-private — toolkits and CLI keep importing it directly.
│   │   │   │   └── inspection.py                              # MODIFY: minor — methods that WorkerContext exposes (list_subtasks, descendants, get_subtask) get whatever signature tweaks the facade needs; the rest stays as-is [P3]
│   │   │   └── resources/                                     # MODIFY (light): nothing forced; whatever scope dispatch WorkerContext.resources(scope=...) needs gets added [P3]
│   │   ├── domain/
│   │   │   └── experiments/
│   │   │       ├── experiment.py                              # DELETE: class Experiment lifts to ergon_core/api/experiment.py (audit #6) [P1]
│   │   │       ├── worker_spec.py                             # DELETE: WorkerSpec dies; Task.worker carries Worker instances directly (audit #2) [P1]
│   │   │       ├── handles.py                                 # unchanged — DefinitionHandle stays internal (return shape of persist_definition; held as Experiment._persisted PrivateAttr)
│   │   │       ├── validation.py                              # MODIFY: ExperimentValidationService keeps the cross-component rules engine; THINS to drop checks now done by *.from_definition / Experiment.@model_validator [P1]
│   │   │       └── __init__.py                                # MODIFY: drop Experiment + WorkerSpec re-exports; keep DefinitionHandle [P1]
│   │   ├── infrastructure/
│   │   │   ├── inngest/handlers/
│   │   │   │   ├── worker_execute.py                          # MODIFY: payload reshape — add definition_id, drop node_id [P3]
│   │   │   │   ├── persist_outputs.py                         # MODIFY: composite (run_id, task_id) refs [P3]
│   │   │   │   ├── evaluate_task_run.py                       # MODIFY: thin id-only payload, reload via graph_repo.node(..., sandbox_id=...), call criterion.evaluate directly, detach in finally [P4]
│   │   │   │   ├── cleanup_cancelled_task.py                  # MODIFY: composite-FK refs [P3]
│   │   │   │   └── cancel_orphan_subtasks.py                  # MODIFY: composite-FK refs [P3]
│   │   │   └── sandbox/
│   │   │       ├── manager.py                                 # DELETE: BaseSandboxManager + DefaultSandboxManager → per-Sandbox-subclass provision() [P2]
│   │   │       ├── lifecycle.py                               # MODIFY (or REPLACE): becomes SandboxLifecycleHub — small kind-agnostic acquire/release/terminate_all [P2]
│   │   │       ├── resource_publisher.py                      # MODIFY: read sandbox via Sandbox subclass, not BaseSandboxManager [P2]
│   │   │       ├── instrumentation.py                         # MODIFY: hook the new Sandbox lifecycle calls [P2]
│   │   │       └── event_sink.py                              # MODIFY: same — hooked into new lifecycle [P2]
│   │   └── persistence/
│   │       ├── components/                                    # DELETE: whole folder dies [P1]
│   │       │   └── models.py                                  # DELETE: ComponentCatalogEntry table → drop and recreate; no replacement (worker JSON lives inside task_json.worker, _type discriminator carries class identity)
│   │       ├── definitions/
│   │       │   └── models.py                                  # MODIFY: ExperimentDefinitionTask gains task_json column containing worker/sandbox/evaluators; ExperimentDefinitionWorker/ExperimentDefinitionTaskAssignment become unnecessary for authoring path [P1-P3]
│   │       └── graph/
│   │           ├── models.py                                  # MODIFY: RunGraphNode PK becomes composite (run_id, task_id); add task_json; drop id/node_id/definition_task_id/description/task_slug/instance_key/assigned_worker_slug; RunGraphEdge becomes composite-FK both sides; RunGraphAnnotation/Mutation likewise [P3]
│   │           └── status_conventions.py                      # MODIFY: any node-id-keyed helpers become (run_id, task_id)-keyed [P3]
│   └── tests/
│       └── unit/
│           ├── api/test_public_api_imports.py                 # MODIFY: drop TaskSpec/ComponentRegistry; add Sandbox, Experiment, SpawnedTaskHandle [P1-P3]
│           ├── api/test_task_spec_contract.py                 # DELETE: TaskSpec dies [P3]
│           ├── api/test_worker_contract.py                    # MODIFY: new execute signature, sandbox kwarg [P1]
│           ├── architecture/test_public_api_boundaries.py     # MODIFY: new boundary set [P1-P3]
│           ├── architecture/test_public_api_target_structure.py # MODIFY: same
│           ├── registry/test_component_registry.py            # DELETE [P1]
│           ├── registry/test_catalog_backed_registry_resolution.py # DELETE [P1]
│           ├── registry/test_react_factories.py               # MODIFY (or DELETE): per-benchmark *ReactWorker subclasses die [P1]
│           ├── registry/test_builtin_pairings.py              # MODIFY or DELETE: no registry/pool worker resolution remains [P1, P3]
│           ├── runtime/test_worker_execute_stream_contract.py # MODIFY: RunGraphNodeView read; worker = task.worker [P3]
│           ├── runtime/test_experiment_definition_writer.py   # MODIFY: Worker pydantic JSON; sandbox-on-Task [P1-P2]
│           ├── runtime/test_experiment_definition_service.py  # MODIFY: drop requires_sandbox cases (now an Experiment model_validator — covered by experiment unit tests) [P2]
│           └── sandbox/test_sandbox_reconnect.py              # MODIFY: SandboxLifecycleHub-based reconnect [P2]
│
├── ergon_builtins/ergon_builtins/
│   ├── registry.py                                            # DELETE [P1]
│   ├── registry_core.py                                       # DELETE [P1]
│   ├── registry_data.py                                       # DELETE [P1] — or trim to BUILTIN_WORKERS = {slug: import_path} for CLI surface only
│   ├── registry_local_models.py                               # MODIFY: keep LLM-backend registration; drop component-registration plumbing [P1]
│   ├── sandboxes/                                             # ADD: new module — per-kind Sandbox subclasses [P2]
│   │   ├── __init__.py                                        # ADD
│   │   ├── _e2b_base.py                                       # ADD: _E2BBackedSandbox shared parent (E2B client construction)
│   │   ├── lean.py                                            # ADD: LeanSandbox(_E2BBackedSandbox) — owns the Lean install
│   │   ├── python.py                                          # ADD: PythonSandbox(_E2BBackedSandbox) — pip install
│   │   ├── swebench.py                                        # ADD: SWEBenchSandbox(_E2BBackedSandbox) — repo clone
│   │   ├── research_e2b.py                                    # ADD: ResearchE2BSandbox(_E2BBackedSandbox)
│   │   └── gdpeval.py                                         # ADD: GDPEvalSandbox(_E2BBackedSandbox)
│   ├── toolkits/                                              # ADD or MOVE: one home for concrete _Toolkit subclasses [P1]
│   │   ├── __init__.py                                        # ADD
│   │   ├── minif2f.py                                         # MOVE from benchmarks/minif2f/toolkit.py: become pydantic, lose __init__(sandbox), gain build_tools(sandbox, task)
│   │   ├── swebench.py                                        # MOVE from benchmarks/swebench_verified/toolkit.py: same
│   │   ├── gdpeval.py                                         # MOVE from benchmarks/gdpeval/toolkit.py: same
│   │   └── research_rubrics.py                                # MOVE from benchmarks/researchrubrics/toolkit_types.py + tools/research_rubrics_toolkit.py
│   ├── tools/                                                 # NOT TOUCHED in this redesign:
│   │   ├── subtask_lifecycle_toolkit.py                       # unchanged — keeps `from ergon_core.core.application.tasks.management import TaskManagementService` (the v1 escape hatch). Containment-check TODO does NOT close here; only WorkerContext.cancel_task / refine_task / get_task enforce it. Migrate this module to the curated facade in a follow-up.
│   │   ├── graph_toolkit.py                                   # unchanged — same v1 escape hatch.
│   │   └── workflow_cli_tool.py                               # unchanged — same v1 escape hatch.
│   ├── workers/baselines/
│   │   └── react_worker.py                                    # MODIFY: ReActWorker takes _toolkit: _Toolkit field; _Toolkit ABC lives module-private here; no per-benchmark subclasses [P1]
│   └── benchmarks/
│       ├── minif2f/
│       │   ├── sandbox_manager.py                             # DELETE: → sandboxes/lean.py [P2]
│       │   ├── toolkit.py                                     # DELETE: → toolkits/minif2f.py [P1]
│       │   ├── worker_factory.py                              # MODIFY: returns ReActWorker(toolkit=MiniF2FToolkit(...)); no MiniF2FReactWorker subclass [P1]
│       │   ├── benchmark.py                                   # MODIFY: build_instances() returns Mapping[str, Sequence[Task]] with sandbox=LeanSandbox(...) on each Task [P2-P3]
│       │   └── __init__.py                                    # MODIFY: drop MiniF2FReactWorker re-export
│       ├── swebench_verified/
│       │   ├── sandbox_manager.py                             # DELETE: → sandboxes/swebench.py [P2]
│       │   ├── sandbox_manager_support.py                     # DELETE: → folded into sandboxes/swebench.py
│       │   ├── toolkit.py                                     # DELETE: → toolkits/swebench.py [P1]
│       │   ├── worker_factory.py                              # MODIFY: returns ReActWorker(toolkit=SWEBenchToolkit(...)) [P1]
│       │   ├── benchmark.py                                   # MODIFY: sandbox=SWEBenchSandbox(...) on each Task [P2-P3]
│       │   └── criterion.py                                   # MODIFY: evaluate(..., sandbox: Sandbox) directly [P4]
│       ├── researchrubrics/
│       │   ├── sandbox_manager.py                             # DELETE: → sandboxes/research_e2b.py [P2]
│       │   ├── toolkit_types.py                               # DELETE: → toolkits/research_rubrics.py [P1]
│       │   ├── worker_factory.py                              # MODIFY: returns ReActWorker(toolkit=ResearchRubricsToolkit(...)) [P1]
│       │   ├── benchmark.py                                   # MODIFY: sandbox=ResearchE2BSandbox(...) per Task [P2-P3]
│       │   └── vanilla.py                                     # MODIFY: drop slug-based factory [P1]
│       └── gdpeval/
│           ├── sandbox.py                                     # DELETE: GDPEvalSandboxManager → sandboxes/gdpeval.py [P2]
│           ├── sandbox_utils.py                               # DELETE or MOVE: helpers fold into sandboxes/gdpeval.py [P2]
│           ├── toolkit.py                                     # DELETE: → toolkits/gdpeval.py [P1]
│           ├── worker_factory.py                              # MODIFY: returns ReActWorker(toolkit=GDPEvalToolkit(...)) [P1]
│           └── benchmark.py                                   # MODIFY: sandbox=GDPEvalSandbox(...) per Task [P2-P3]
│
├── ergon_cli/ergon_cli/
│   └── commands/
│       └── workflow.py                                        # NOT TOUCHED — keeps existing imports of TaskManagementService / TaskInspectionService / WorkflowService internals. Migration to a public service tier is deferred (see 09-implementation-plan.md "What's deferred").
│
└── docs/
    ├── architecture/                                          # MODIFY (post-acceptance): update 01_public_api.md, cross_cutting/sandbox_lifecycle.md, etc. (see 09-implementation-plan.md "On acceptance")
    └── rfcs/active/2026-05-08-authoring-api-redesign/         # this folder — graduates to accepted/ post-migration
```

### Headline counts

| Action | ergon_core | ergon_builtins | ergon_cli | tests | total |
|---|---|---|---|---|---|
| ADD (new files) | 4 (`api/sandbox/{__init__,sandbox,runtime}.py` + `api/experiment.py` — last is the Experiment lift; not a new shell, the class definition itself moves here) | 11 (`sandboxes/*`, `toolkits/*`) | — | — | 15 |
| MODIFY | ~20 | ~9 (workers/baselines + benchmark dirs) | — | ~10 | ~39 |
| DELETE | 6 (`api/registry.py`, `application/components/`, `persistence/components/`, `infrastructure/sandbox/manager.py` partial, `core/domain/experiments/experiment.py`, `core/domain/experiments/worker_spec.py`) | 12 (`registry*.py`, per-benchmark `sandbox_manager.py` + `toolkit.py` + gdpeval `sandbox*.py`) | — | 3 | ~21 |

### What's notably *not* on the list

- `ergon_builtins/observability/`, `ergon_builtins/models/`,
  `ergon_builtins/common/`, `ergon_builtins/evaluators/criteria/` —
  unaffected. These don't touch the registry, the sandbox manager, or
  the worker construction surface.
- `ergon_builtins/tools/` — **unaffected in this PR.** An earlier
  draft migrated `subtask_lifecycle_toolkit.py`, `graph_toolkit.py`,
  and `workflow_cli_tool.py` to consume new public service classes;
  that's deferred.
- `ergon_cli/commands/workflow.py` — **unaffected in this PR.** Same
  reason — deferred along with the public service tier.
- `ergon_core/core/persistence/telemetry/`, `.../saved_specs/`,
  `.../imports/`, `.../context/`, `.../shared/` — unaffected. They
  reference runs/tasks via foreign key but don't carry component
  identity or sandbox state.
- `ergon_ingestion/` (external-run import) — unaffected. Writes runs
  straight to the persistence layer below the public API. (Already
  flagged in [`09-implementation-plan.md`](09-implementation-plan.md).)
- `ergon_core/core/rest_api/` — mostly unaffected; rollout/run-listing
  endpoints continue to read from the same persistence rows. The one
  spot that may need a touch is wherever `node_id` leaked into a
  response shape (none expected, but worth grepping during P3).
- `ergon_core/core/application/workflows/service.py` — unaffected.
  `WorkflowService` stays as today; the workflow CLI keeps importing
  it.

If you find a file the trace implies should change but it's not on this
list, that's a real omission — flag it in
[`08-decisions-log.md`](08-decisions-log.md) and add it here.

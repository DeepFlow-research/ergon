# Event Architecture

## System Overview

**Scope: ReAct Baseline Only**

Simple event-driven flow for running experiments and measuring clarification behavior.

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Experiment Runner                             │
│                   (Batch launcher for 200 tasks)                    │
└────────────────────────────────┬────────────────────────────────────┘
                                 │
                    POST run/start events
                                 │
                                 ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      Inngest Event Bus                               │
│                                                                      │
│  run/start ──────────► worker_execute                               │
│  execution/done ─────► run_evaluate                                 │
│                                                                      │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │
                           DB Read/Write
                                  │
                                  ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        PostgreSQL (7 tables)                         │
│  ┌───────────┐ ┌──────┐ ┌──────────┐ ┌─────────┐                   │
│  │experiments│ │ runs │ │ messages │ │ actions │                   │
│  └───────────┘ └──────┘ └──────────┘ └─────────┘                   │
│  ┌───────────┐ ┌───────────┐ ┌──────────────────┐                  │
│  │ resources │ │evaluations│ │criterion_results │                  │
│  └───────────┘ └───────────┘ └──────────────────┘                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Event Types

### Inngest Events

| Event | Trigger Source | Handler |
|-------|---------------|---------|
| `run/start` | Experiment runner | `worker_execute` |
| `execution/done` | worker_execute | `run_evaluate` |
| `evaluation/start` | run_evaluate | `evaluate_task_run` |
| `evaluation/criterion` | evaluate_task_run | `evaluate_criterion` |

All state is stored in `runs`, `messages`, `actions`, `criterion_results`, and `evaluations` tables. State can be reconstructed from timestamps.

---

## State Machine: Run

Simple linear flow:

```
        ┌─────────┐
        │ PENDING │
        └────┬────┘
             │ run/start event
             ▼
     ┌───────────────┐
     │   EXECUTING   │
     └───────┬───────┘
             │
             │  Worker executes task
             │  May call ask_stakeholder 0+ times
             │  Each call → Message + Action
             │
     ┌───────┴───────┐
     │               │
   success        error
     │               │
     ▼               ▼
┌──────────┐   ┌──────────┐
│EVALUATING│   │  FAILED  │
└────┬─────┘   └──────────┘
     │
     │ Score against ground truth
     │
     ▼
┌───────────┐
│ COMPLETED │
└───────────┘
```

---

## Function Definitions

### worker_execute

Execute the task with a ReAct worker that can ask questions.

```python
# inngest/functions.py
from h_arcane.inngest.client import inngest_client
from h_arcane.db import queries
from h_arcane.agents.worker import ReActWorker
from h_arcane.agents.stakeholder import RubricStakeholder
from h_arcane.agents.toolkit import WorkerToolkit
from paper_code_structure_plans.schemas.staged_rubric_schema import StagedRubric

@inngest_client.create_function(
    fn_id="worker-execute",
    trigger=inngest.TriggerEvent(event="run/start"),
    retries=2,
)
async def worker_execute(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    """
    Execute task with ReAct worker.
    
    Messages and actions are logged by WorkerToolkit during execution.
    All GDPEval tools execute inside E2B sandbox (see SANDBOX_ARCHITECTURE.md).
    """
    run_id = UUID(ctx.event.data["run_id"])
    
    # Load state
    run = await step.run("load-run", lambda: queries.runs.get(run_id))
    experiment = await step.run(
        "load-experiment",
        lambda: queries.experiments.get(run.experiment_id)
    )
    # Load input resources (stored with experiment_id, not run_id)
    input_resources = await step.run(
        "load-input-resources",
        lambda: queries.resources.get_by_experiment(experiment.id)
    )
    
    # Mark executing
    await step.run(
        "mark-executing",
        lambda: queries.runs.update(run_id, status="executing", started_at=datetime.utcnow())
    )
    
    # Create sandbox (see SANDBOX_ARCHITECTURE.md)
    from h_arcane.agents.sandbox import SandboxManager
    sandbox_manager = SandboxManager(run_id)
    await step.run("create-sandbox", lambda: sandbox_manager.create())
    
    try:
        # Upload inputs to sandbox
        await step.run(
            "upload-inputs",
            lambda: sandbox_manager.upload_inputs(input_resources)
        )
        
        # Upload tools to sandbox
        from h_arcane.agents.sandbox_executor import upload_tools_to_sandbox
        await step.run("upload-tools", lambda: upload_tools_to_sandbox(sandbox_manager))
        
        # Set sandbox manager globally for execute_in_sandbox()
        from h_arcane.agents.sandbox_executor import set_sandbox_manager
        await step.run("set-sandbox-manager", lambda: set_sandbox_manager(sandbox_manager))
        
        # Create stakeholder
        ground_truth = StagedRubric(**experiment.ground_truth_rubric)
        
        stakeholder = RubricStakeholder(
            ground_truth_rubric=ground_truth,
            task_description=experiment.task_description,
        )
        
        # Create toolkit (handles message/action logging, uses sandbox)
        toolkit = WorkerToolkit(
            run_id=run_id,
            stakeholder=stakeholder,
            sandbox_manager=sandbox_manager,
            max_questions=run.max_questions,
        )
        
        # Execute (tools execute in sandbox)
        worker = ReActWorker(model=run.worker_model)
        
        execution_output = await step.run(
            "execute-task",
            lambda: worker.execute(
                run_id=run_id,
                task_description=experiment.task_description,
                input_resources=input_resources,
                toolkit=toolkit,
            )
        )
        
        # Download all outputs from sandbox
        output_dir = Path(f"data/runs/{run_id}")
        output_dir.mkdir(parents=True, exist_ok=True)
        
        downloaded_files = await step.run(
            "download-outputs",
            lambda: sandbox_manager.download_all_outputs(output_dir)
        )
        
        # Register downloaded files as Resources
        for file_info in downloaded_files:
            await step.run(
                f"register-resource-{file_info['local_path']}",
                lambda fi=file_info: queries.resources.create(
                    run_id=run_id,
                    name=Path(fi["local_path"]).name,
                    mime_type=get_mime_type(fi["local_path"]),
                    file_path=fi["local_path"],
                    size_bytes=fi["size_bytes"],
                )
            )
        
        # Save output to run
        await step.run(
            "save-output",
            lambda: queries.runs.update(
                run_id=run_id,
                output_text=execution_output.output_text,
                output_resource_ids=[str(r.id) for r in execution_output.output_resources],
                questions_asked=toolkit.questions_asked,
            )
        )
        
        # Emit for evaluation
        await step.invoke(
            inngest.Event(
                name="execution/done",
                data={"run_id": str(run_id)},
            )
        )
        
    finally:
        # Always terminate sandbox
        await step.run("terminate-sandbox", lambda: sandbox_manager.terminate())
    
    return {
        "run_id": str(run_id),
        "questions_asked": toolkit.questions_asked,
    }
```

### run_evaluate

Evaluate execution against ground truth rubric.

**Note**: See [05_EVALUATION_ARCHITECTURE.md](./05_EVALUATION_ARCHITECTURE.md) for detailed evaluation architecture.

```python
@inngest_client.create_function(
    fn_id="run-evaluate",
    trigger=inngest.TriggerEvent(event="execution/done"),
    retries=1,
)
async def run_evaluate(
    ctx: inngest.Context,
    step: inngest.Step,
) -> dict:
    """
    Evaluate execution against ground truth rubric.
    
    Delegates to evaluate_task_run which orchestrates criterion evaluation.
    See 05_EVALUATION_ARCHITECTURE.md for details.
    """
    run_id = UUID(ctx.event.data["run_id"])
    
    # Mark evaluating
    await step.run(
        "mark-evaluating",
        lambda: queries.runs.update(run_id, status="evaluating")
    )
    
    # Load state
    run = await step.run("load-run", lambda: queries.runs.get(run_id))
    experiment = await step.run(
        "load-experiment",
        lambda: queries.experiments.get(run.experiment_id)
    )
    
    # Invoke evaluation (evaluate_task_run handles flattening, parallel evaluation, rebuilding)
    evaluation_result = await step.invoke(
        inngest.Event(
            name="evaluation/start",
            data={
                "run_id": str(run_id),
                "task_input": experiment.task_description,
                "agent_reasoning": run.output_text or "",
                "agent_output_resource_ids": run.output_resource_ids,
            },
        )
    )
    
    # Mark complete
    await step.run(
        "complete-run",
        lambda: queries.runs.update(
            run_id=run_id,
            status="completed",
            completed_at=datetime.utcnow(),
            final_score=evaluation_result["total_score"],
            normalized_score=evaluation_result["normalized_score"],
        )
    )
    
    return {
        "run_id": str(run_id),
        "normalized_score": evaluation_result["normalized_score"],
        "questions_asked": run.questions_asked,
    }
```

**Evaluation Flow**:
1. `run_evaluate` → invokes `evaluation/start` event
2. `evaluate_task_run` → flattens rubric, invokes `evaluation/criterion` for each criterion
3. `evaluate_criterion` → evaluates single criterion (code rule or LLM judge)
4. `evaluate_task_run` → rebuilds results, calculates aggregates, saves to DB

---

## FastAPI Integration

```python
# api/main.py
from fastapi import FastAPI
import inngest.fast_api

from h_arcane.inngest.client import inngest_client
from h_arcane.inngest.functions import worker_execute, run_evaluate

app = FastAPI(title="H-ARCANE Experiments")

# Register Inngest functions
inngest.fast_api.serve(
    app,
    inngest_client,
    [worker_execute, run_evaluate],
)

# API routes
@app.post("/runs/start")
async def start_run(experiment_id: UUID) -> dict:
    """Start a single run."""
    run_id = await create_run(experiment_id)
    
    await inngest_client.send(
        inngest.Event(
            name="run/start",
            data={"run_id": str(run_id)},
        )
    )
    
    return {"run_id": run_id}

@app.post("/experiments/run-batch")
async def run_batch(experiment_ids: list[UUID]) -> dict:
    """Start runs for multiple experiments."""
    run_ids = []
    
    for exp_id in experiment_ids:
        run_id = await create_run(exp_id)
        await inngest_client.send(
            inngest.Event(
                name="run/start",
                data={"run_id": str(run_id)},
            )
        )
        run_ids.append(run_id)
    
    return {"started": len(run_ids), "run_ids": run_ids}
```

---

## Execution Flow

```
[POST /runs/start]
         │
         ▼
    run/start event
         │
         ▼
┌─────────────────────────────────────┐
│       worker_execute                │
│  - Load experiment                  │
│  - Create stakeholder               │
│  - Create worker with tools         │
│  - Execute (ReAct loop)             │
│    └── Worker may call              │
│        ask_stakeholder 0+ times     │
│        Each call → Message + Action │
│  - Save outputs                     │
│  - Emit execution/done              │
└──────────────┬──────────────────────┘
               │
               ▼
      execution/done event
               │
               ▼
┌─────────────────────────────────────┐
│       run_evaluate                  │
│  - Load execution + outputs         │
│  - Run StagedRubric evaluation      │
│  - Store scores                     │
│  - Mark run complete                │
└──────────────┬──────────────────────┘
               │
               ▼
         Run complete
         (score + questions_asked logged)
```

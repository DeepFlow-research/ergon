# Immutable Data Refactor Proposal

> Goal: Eliminate mutable state patterns and make data flow explicit

## Current Problems

### 1. Action Mutation (Most Severe)

**Current flow:**
```python
# ReActWorker creates incomplete Action
action = Action(
    action_type="read_file",
    action_num=0,  # Set by worker
    input="...",
    output="...",
    agent_total_cost_usd=0.001,  # Worker knows this
    # run_id: NOT SET
    # agent_id: NOT SET
)

# worker_execute.py mutates it
action.run_id = run_id        # ← MUTATION
action.agent_id = agent_config.id  # ← MUTATION
queries.actions.create(action)
```

**Why it's bad:**
- Worker creates object, orchestration layer modifies it
- Violates single responsibility
- Hidden temporal coupling
- `WorkerContext` already has `run_id` and `agent_config_id` - worker could use them!

---

### 2. AgentConfig Duplication

**Current flow:**
```python
# worker_execute.py - creates NEW config every time
agent_config = queries.agent_configs.create(
    AgentConfig(run_id=run_id, name=worker.name, ...)
)
```

**Why it's bad:**
- Same worker creates multiple configs per run
- No deduplication by worker identity
- Linear run (3 tasks) creates 7 agent configs instead of 2

---

### 3. TaskExecution.agent_id Never Set

**Current flow:**
```python
# task_execute.py
execution = create_task_execution(run_id, task_id)  # agent_id = NULL

# Later, worker_execute.py creates agent_config
# But execution.agent_id is never updated!
```

**Why it's bad:**
- Can't trace which agent executed which task
- Foreign key exists but is always NULL

---

### 4. Run Completion Mutation

**Current flow:**
```python
# workflow_complete.py
run.status = RunStatus.COMPLETED
run.completed_at = completed_at
run.final_score = total_score
run.total_cost_usd = total_cost_usd
run.output_text = aggregated_output_text
run.execution_result = execution_result.model_dump()
queries.runs.update(run)
```

**Why it's (mildly) bad:**
- 6 separate field mutations
- Easy to forget one
- No compile-time guarantee all fields are set

---

## Proposed Solutions

### Solution 1: Actions Created Complete by Worker

**Key insight:** `WorkerContext` already has `run_id` and `agent_config_id`!

```python
# worker.py - WorkerContext already has:
class WorkerContext(BaseModel):
    run_id: UUID
    task_id: UUID
    agent_config_id: UUID | None  # ← Already exists!
    ...
```

**Change:** Worker creates complete Actions using context:

```python
# react_worker.py - NEW
def _extract_actions_from_result(self, result: RunResult, context: WorkerContext) -> list[Action]:
    actions = []
    for item in result.new_items:
        action = Action(
            run_id=context.run_id,              # ← From context
            agent_id=context.agent_config_id,   # ← From context  
            action_num=action_num,
            action_type=...,
            input=...,
            output=...,
        )
        actions.append(action)
    return actions
```

**Then in worker_execute.py:**
```python
# OLD (mutation)
for action in result.actions:
    action.run_id = run_id
    action.agent_id = agent_config.id
    queries.actions.create(action)

# NEW (actions already complete)
for action in result.actions:
    queries.actions.create(action)
```

**Files to change:**
- `h_arcane/benchmarks/common/workers/react_worker.py` - pass context to `_extract_actions_from_result`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py` - remove mutation
- `h_arcane/core/_internal/task/persistence.py` - remove mutation in `persist_actions`

---

### Solution 2: AgentConfig Get-or-Create Pattern

**Change:** Lookup existing config by worker_id, create only if not found.

```python
# queries.py - NEW method
class AgentConfigsQueries:
    def get_or_create(
        self,
        run_id: UUID,
        worker_id: UUID,
        defaults: AgentConfig,
    ) -> tuple[AgentConfig, bool]:
        """Get existing config or create new one.
        
        Returns:
            (config, created) - created=True if new record
        """
        with next(get_session()) as session:
            existing = session.exec(
                select(AgentConfig)
                .where(AgentConfig.run_id == run_id)
                .where(AgentConfig.worker_id == worker_id)
            ).first()
            
            if existing:
                return existing, False
            
            defaults.run_id = run_id
            defaults.worker_id = worker_id
            session.add(defaults)
            session.commit()
            session.refresh(defaults)
            return defaults, True
```

**Then in worker_execute.py:**
```python
# OLD
agent_config = queries.agent_configs.create(AgentConfig(...))

# NEW
agent_config, _ = queries.agent_configs.get_or_create(
    run_id=run_id,
    worker_id=worker.id,
    defaults=AgentConfig(
        name=worker.name,
        agent_type="react_worker",
        model=worker.model,
        system_prompt=worker.system_prompt,
        tools=[...],
    )
)
```

**Files to change:**
- `h_arcane/core/_internal/db/queries.py` - add `get_or_create`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py` - use `get_or_create`

---

### Solution 3: Link TaskExecution to Agent

**Option A:** Update TaskExecution after agent is determined

```python
# worker_execute.py
agent_config, _ = queries.agent_configs.get_or_create(...)

# Link execution to agent
queries.task_executions.set_agent(execution_id, agent_config.id)
```

**Option B:** Pass agent_config_id when creating TaskExecution (requires restructuring flow)

**Recommended:** Option A is simpler and doesn't require flow changes.

```python
# queries.py - NEW method
class TaskExecutionsQueries:
    def set_agent(self, execution_id: UUID, agent_id: UUID) -> None:
        """Set the agent_id on a task execution."""
        with next(get_session()) as session:
            execution = session.get(TaskExecution, execution_id)
            if execution:
                execution.agent_id = agent_id
                session.add(execution)
                session.commit()
```

**Files to change:**
- `h_arcane/core/_internal/db/queries.py` - add `set_agent`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py` - call `set_agent`

---

### Solution 4: Run Completion Data Class

**Create explicit completion data:**

```python
# results.py or new file
@dataclass
class RunCompletionData:
    """All data needed to complete a run. Immutable."""
    completed_at: datetime
    final_score: float | None
    normalized_score: float | None
    total_cost_usd: float
    output_text: str | None
    execution_result: dict
```

**Single completion method:**

```python
# queries.py
class RunsQueries:
    def complete(self, run_id: UUID, data: RunCompletionData) -> Run:
        """Mark run as completed with all completion data.
        
        Single atomic operation - all fields set together.
        """
        with next(get_session()) as session:
            run = session.get(Run, run_id)
            if not run:
                raise ValueError(f"Run {run_id} not found")
            
            run.status = RunStatus.COMPLETED
            run.completed_at = data.completed_at
            run.final_score = data.final_score
            run.normalized_score = data.normalized_score
            run.total_cost_usd = data.total_cost_usd
            run.output_text = data.output_text
            run.execution_result = data.execution_result
            
            session.add(run)
            session.commit()
            session.refresh(run)
            return run
```

**Then in workflow_complete.py:**
```python
# OLD (6 mutations)
run.status = RunStatus.COMPLETED
run.completed_at = completed_at
...
queries.runs.update(run)

# NEW (single explicit operation)
completion = RunCompletionData(
    completed_at=completed_at,
    final_score=total_score,
    normalized_score=normalized_score,
    total_cost_usd=total_cost_usd,
    output_text=aggregated_output_text,
    execution_result=execution_result.model_dump(mode="json"),
)
queries.runs.complete(run_id, completion)
```

**Files to change:**
- `h_arcane/core/_internal/task/results.py` - add `RunCompletionData`
- `h_arcane/core/_internal/db/queries.py` - add `complete` method
- `h_arcane/core/_internal/task/inngest_functions/workflow_complete.py` - use new pattern

---

### Solution 5: Fix Stakeholder Role

**Simple fix in worker_execute.py:**

```python
# OLD
AgentConfig(
    run_id=run_id,
    name=f"{stakeholder_display_name} Stakeholder",
    agent_type="stakeholder",
    model=stakeholder.model,
    ...
    # role defaults to "worker"
)

# NEW
AgentConfig(
    run_id=run_id,
    name=f"{stakeholder_display_name} Stakeholder",
    agent_type="stakeholder",
    role="stakeholder",  # ← Explicitly set
    model=stakeholder.model,
    ...
)
```

---

## Implementation Order

1. **Solution 5: Stakeholder role** (trivial, 1 line)
2. **Solution 2: AgentConfig get_or_create** (fixes duplicates)
3. **Solution 3: TaskExecution.agent_id** (depends on #2)
4. **Solution 1: Complete Actions** (biggest change, but isolated to worker)
5. **Solution 4: RunCompletionData** (nice-to-have, improves clarity)

---

## Summary of Benefits

| Before | After |
|--------|-------|
| Action created incomplete, mutated later | Action created complete by worker |
| 7+ AgentConfigs per linear run | 2 AgentConfigs (worker + stakeholder) |
| TaskExecution.agent_id always NULL | Properly linked to agent |
| Stakeholder role = "worker" | Stakeholder role = "stakeholder" |
| Run completion: 6 separate mutations | Single explicit `complete()` call |

---

## Estimated Effort

- Solution 5: ~5 minutes
- Solution 2: ~30 minutes  
- Solution 3: ~15 minutes
- Solution 1: ~45 minutes
- Solution 4: ~30 minutes

**Total: ~2 hours**

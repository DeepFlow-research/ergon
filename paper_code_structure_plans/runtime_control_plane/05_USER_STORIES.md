# User Stories

## Why This Exists

The design should be judged less by whether it sounds architecturally clean and more by whether it makes the important user paths feel simple and stable.

This document captures the main user stories the control-plane redesign should support.

The assumption for now is that the primary user is an advanced research engineer who wants:

- fast iteration on evals
- smooth switching between model sources
- room to grow into local-model and RL-driven workflows

## Story 1: Run A Benchmark On A Cloud Model

### Intent

The user wants to quickly run a benchmark on a provider model.

### Desired experience

```python
run = await client.evaluate(
    EvalSpec(
        benchmark="minif2f",
        split="valid",
        limit=100,
        cohort_name="gpt4o-smoke",
    ),
    model=ModelTarget(
        kind="provider",
        provider="openai",
        model_name="gpt-4o",
    ),
)
```

### Why it matters

This should be the simplest path.
No orchestration noise should appear if none is needed.

## Story 2: Run The Same Benchmark On An Already-Live Local Model

### Intent

The user already has a local or remote model endpoint running and wants to evaluate against it.

### Desired experience

```python
run = await client.evaluate(
    EvalSpec(
        benchmark="minif2f",
        split="valid",
        limit=100,
        cohort_name="qwen-local",
    ),
    model=ModelTarget(
        kind="endpoint",
        model_name="qwen-32b",
        version="local-dev",
        endpoint="http://localhost:8000",
    ),
)
```

### Why it matters

This is the first serious "local model" ergonomic target.
The eval path should remain identical; only the model target changes.

## Story 3: Launch A Local/Cluster Model Then Evaluate Against It

### Intent

The user does not already have a live model endpoint and wants Arcane to help launch one before evaluation.

### Desired experience

```python
run = await client.evaluate(
    EvalSpec(
        benchmark="minif2f",
        split="valid",
        limit=100,
        cohort_name="qwen-managed",
    ),
    model=ModelTarget(
        kind="managed",
        model_name="qwen-32b",
        version="candidate-17",
        launch=LaunchSpec(
            backend="slurm",
            accelerator="a100:2",
            launcher_config={"partition": "gpu"},
        ),
    ),
)
```

### What should happen

Under the hood:

1. provision serving
2. wait for readiness
3. register / resolve `ModelTarget`
4. submit evaluation

### Why it matters

This is the path that connects "simple eval ergonomics" to "managed local model infrastructure" without changing the higher-level evaluation abstraction.

## Story 4: Re-run The Same Eval Against Multiple Models

### Intent

The user wants to keep the eval fixed and compare models.

### Desired experience

```python
eval_spec = EvalSpec(
    benchmark="minif2f",
    split="valid",
    limit=100,
)

models = [
    ModelTarget(kind="provider", provider="openai", model_name="gpt-4o"),
    ModelTarget(kind="endpoint", model_name="qwen-32b", endpoint="http://localhost:8000"),
]

for model in models:
    await client.evaluate(eval_spec, model=model)
```

### Why it matters

This is probably the most central day-to-day workflow.
The design should make this feel natural.

## Story 5: A Training Loop Produces A New Policy Version And Arcane Evaluates It

### Intent

The user has a training system outside Arcane that produces a new checkpoint or served policy version.

### Desired experience

The training system should only need to produce a new `ModelTarget` or `PolicyVersion` reference.
Arcane should not need a separate evaluation abstraction just because the model came from training.

Example:

```python
run = await client.evaluate(
    eval_spec,
    model=ModelTarget(
        kind="endpoint",
        model_name="qwen-70b",
        version="v43",
        endpoint="http://serving.cluster/qwen-70b-v43",
    ),
)
```

### Why it matters

This is the bridge to larger async RL or post-training systems.
Arcane should consume new model targets, not require a new product surface for each training setup.

## Story 6: Async RL With Draining And Promotion

### Intent

The user eventually wants Arcane to support a larger control-loop that:

- serves `v_k`
- runs rollouts
- drains rollout creation
- trains to produce `v_{k+1}`
- promotes new serving
- resumes rollout generation

### Desired experience

This should be modeled through control-plane resources, not hidden hooks.

The user or orchestrator should be able to do something conceptually like:

```python
group = await client.create_rollout_group(eval_spec, model_target)
await client.set_rollout_group_state(group.id, "draining")
window = await client.seal_training_window(group_ids=[group.id])
job = await client.launch_training(window.id, trainer_spec)
policy = await client.register_policy_version(job.id)
await client.promote_policy_version(policy.version)
```

### Why it matters

Even if this does not ship immediately, the runtime and persistence model should already leave room for it.

## Story 7: Train A Large Local Model With Managed Serving And Managed Training

### Intent

The user wants to run RL or post-training around a large local model such as a 70B checkpoint.

### Desired experience

The user should be able to:

1. define the eval / rollout environment once
2. point Arcane at a managed model target
3. let Arcane coordinate serving, rollout draining, training, and promotion

Conceptually:

```python
group = await client.create_rollout_group(
    eval_spec,
    model=ModelTarget(
        kind="managed",
        model_name="llama-2-70b",
        version="v_k",
        launch=LaunchSpec(
            backend="cloud-provider",
            accelerator="h100:8",
        ),
    ),
)

await client.set_rollout_group_state(group.id, "draining")
window = await client.seal_training_window(group_ids=[group.id])
job = await client.launch_training(window.id, trainer_spec)
policy = await client.register_policy_version(job.id)
await client.promote_policy_version(policy.version)
```

### Why it matters

This is the first real stress test of whether the four-plane model is operationally useful and not just conceptually clean.

## Story 8: CLI Use Should Mirror The Same Concepts

### Intent

The user sometimes wants a CLI path instead of Python.

### Desired experience

Cloud:

```bash
magym eval run \
  --benchmark minif2f \
  --split valid \
  --limit 100 \
  --model openai:gpt-4o
```

Endpoint:

```bash
magym eval run \
  --benchmark minif2f \
  --split valid \
  --limit 100 \
  --model-endpoint http://localhost:8000 \
  --model-name qwen-32b
```

Managed:

```bash
magym eval run -f experiment.yaml
```

### Why it matters

The CLI should mirror the same API concepts rather than inventing a separate mental model.

## Story 9: Users Should Not Have To Think In Scheduler Primitives First

### Intent

The user wants to evaluate a model, not design a Slurm job graph every time.

### Desired experience

Scheduler details should appear only when the model target is managed and only under a launch-oriented subobject or config.

### Why it matters

This keeps Arcane focused on evaluations and model targets rather than leaking infra-specific complexity into the default path.

## Story 10: One Concrete Backend Exists Even If The Model Is Abstract

### Intent

The user agrees with keeping the architecture backend-flexible, but wants one real implementation that actually works.

### Desired experience

The docs and product should make it clear that:

- Arcane is backend-flexible in principle
- Arcane ships with one recommended first concrete backend path
- future backends are substitutions, not architecture rewrites

### Why it matters

Without one concrete path, the design risks feeling like a generic abstraction exercise rather than a system that can actually be built and used.

## Final Product Reading

If these stories are supported well, Arcane should feel like:

- a runtime-backed evaluation system
- with stable evaluation definitions
- and cleanly swappable model targets
- that can later plug into larger RL systems without redesigning the basic evaluation flow

That is the user-experience bar these docs are trying to hit.

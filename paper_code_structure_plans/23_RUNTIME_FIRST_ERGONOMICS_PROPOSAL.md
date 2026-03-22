# Runtime-First Ergonomics Proposal

## Problem Statement
One of the deepest ergonomic problems in the current system is that the project is carrying two competing identities at the same time:

- a Python library / SDK where users construct tasks, workers, and workflows directly in process
- a containerized runtime platform where orchestration, persistence, sandboxing, dashboarding, and recovery actually happen

Both of these are legitimate product directions. The awkwardness comes from trying to preserve the feeling that they are one thing all the way through execution, even though they have very different boundary conditions.

The specific pain point this creates is visible in the CLI/runtime split. The CLI runs outside Docker, while the actual orchestration runtime lives inside Docker. That means the system has to bridge a real process boundary. Right now that boundary is not fully embraced as a first-class architectural fact, so parts of the codebase end up behaving as though rich Python object identity can somehow survive a runtime handoff. That is what creates awkward decision boundaries and the feeling that the system is not quite sure whether it is a library, a runtime, or both.

My view is that the project will become much more coherent if it explicitly chooses a primary identity and treats the other form as a supporting layer rather than a competing one.

## Core Recommendation
The cleanest direction is to make the project **runtime-first, with an SDK/client authoring layer**, rather than pretending the main execution path is a pure in-process library call.

That means:

- the **runtime** owns orchestration, persistence, retries, execution state, sandbox lifecycle, and dashboard/event emission
- the **CLI** becomes a control-plane client for that runtime
- the **Python SDK** becomes an authoring and submission layer for workflows, workers, and execution requests
- true in-process execution still exists, but as an explicit mode rather than the hidden assumption underneath the main runtime path

This is not an argument against having a good library API. It is an argument for making the real architectural center of gravity explicit. Once a system has Dockerized services, a DB, Inngest orchestration, sandbox lifecycle, and dashboard state, it is no longer "just a library." At that point it is a runtime system with a library surface, and the ergonomics improve when the architecture admits that honestly.

## The Architectural Mistake To Avoid
The main thing I would avoid going forward is this pattern:

- construct rich Python objects outside the runtime
- cross a real process boundary
- then try to preserve the illusion that the runtime still has access to those live objects as if process locality were incidental

That approach is the root cause of a lot of awkwardness. It tends to produce in-memory registries, partial reconstruction hacks, implicit lifecycle assumptions, and confusion about where the actual source of truth lives.

Once the CLI and runtime are in different processes, the safe crossing point is not live Python object identity. The safe crossing point is a serialized contract.

That serialized contract should be the first-class handoff format for:

- workflow submission
- worker definitions
- evaluator configuration
- benchmark configuration
- run requests
- runtime state transitions

In other words, the boundary should be "specs and events," not "objects and ambient memory."

## Proposed Mental Model
I would describe the system in terms of three layers.

### 1. Authoring Layer
This is the Python-facing part that researchers and developers use to define what they want to run.

Its job is:

- define `Task`, `Workflow`, `WorkerSpec`, evaluator specs, and benchmark config
- validate those structures
- serialize them into runtime-safe request models

This is the part that should feel like a library. It should be ergonomic, composable, pleasant to use in notebooks and scripts, and honest about whether execution will happen locally or in the runtime.

### 2. Runtime Layer
This is the containerized execution system.

Its job is:

- accept submitted run requests
- materialize workers from persisted specs
- manage task execution attempts
- orchestrate the workflow
- persist actions, resources, and evaluations
- emit dashboard and trace events
- handle cleanup, retries, recovery, and observability

This is the actual operational core of the product. It should be the place where durability and correctness guarantees live.

### 3. Control Plane Layer
This is the CLI and any thin client wrappers around the runtime.

Its job is:

- submit runs
- inspect runs and cohorts
- stream logs and status
- launch local dev services
- manage a local runtime environment
- point at local or remote runtime targets

This should feel like talking to a service, not like sneaking Python objects across the boundary and hoping the runtime can find them later.

## The Ergonomic Principle
The most important ergonomic improvement is to make execution mode explicit rather than implicit.

I would recommend supporting three distinct modes:

1. `local`
2. `runtime`
3. `remote`

### Local
`local` means true in-process execution. This is for:

- notebooks
- research iteration
- lightweight development
- tight debugging loops
- unit-style experimentation

In this mode, the system can legitimately work with live Python object identity because there is no process boundary to cross.

### Runtime
`runtime` means execution against the local Dockerized runtime. This is for:

- realistic orchestration
- dashboard-backed runs
- sandbox execution
- retry/recovery behavior
- testing the actual platform path

In this mode, execution should happen via a serialized request submitted to the runtime, not by trying to preserve the illusion that the worker object from the caller process is still the real runtime worker.

### Remote
`remote` means the same submission model as `runtime`, but pointed at a shared or deployed environment.

This mode becomes much easier to support once the local runtime path is already designed around explicit serialization and client/runtime separation.

## Why Explicit Modes Help
Right now the system is paying a tax for trying to hide architectural reality:

- library ergonomics at the call site
- runtime complexity under the hood

That creates confusion because the user is not always told when they are in a true in-process world versus when they are in a runtime world with durability, orchestration, and service boundaries.

Explicit modes solve that by making the tradeoff visible and intentional. Researchers still get a good Python experience, but they also understand whether they are invoking a local executor or submitting a runtime job. This gives the system room to be honest about its architecture without becoming clunky.

Instead of one ambiguous execution story, the project gets three clear stories:

- "I want to prototype quickly" -> `local`
- "I want the real local platform path" -> `runtime`
- "I want shared infrastructure" -> `remote`

That is a much more satisfying ergonomic model than trying to make all three feel identical internally.

## What The CLI Should Become
The CLI should stop feeling like the place where execution truly lives and instead feel like the operator interface for the runtime.

A better CLI shape would emphasize verbs like:

- `magym dev up`
- `magym dev down`
- `magym run submit`
- `magym run status`
- `magym run watch`
- `magym run inspect`
- `magym cohort list`
- `magym logs tail`

This is a more natural interface for a runtime product. It also makes Docker feel like part of the intended platform rather than an implementation detail the system is trying to pretend does not exist.

The CLI can still be pleasant and researcher-friendly. It just should not need to carry hidden assumptions about runtime-local object access. Its responsibility is to submit specs, query the runtime, and help operators navigate the system cleanly.

## What The SDK Should Become
The SDK should narrow to the things that genuinely benefit from being Python-native:

- workflow and task definitions
- worker specs
- evaluator definitions or specs
- serialization helpers
- local execution helpers
- runtime submission client

This would make the SDK much more coherent. It would no longer need to implicitly act as a transport mechanism for live worker instances into a containerized runtime. Instead, it would author, validate, serialize, and submit the things the runtime needs.

That still leaves room for a very nice user-facing API. In fact, it likely improves the API because it removes the need to conceal awkward boundary crossings behind what appears to be a normal library call.

## The Product Truth
Reading the project as it exists today, my honest assessment is that it wants to be:

**a runtime platform with a Python authoring SDK**

That is the framing I think would produce the cleanest architecture and the best ergonomics.

Trying to preserve the identity of "primarily a library" while the actual product logic depends on orchestration, services, persistence, and Docker is what creates the unsatisfying middle state. Once the system admits that the runtime is the center, the surrounding ergonomics become easier to design intentionally.

## A Practical Boundary Rule
I would use the following rule of thumb when deciding what belongs where:

If a feature depends on:

- durability
- retries
- sandbox lifecycle
- orchestration
- dashboard visibility
- persistent state
- recovery after interruption

then it belongs to the **runtime**.

If a feature depends on:

- authoring
- composition
- validation
- local experimentation
- notebook ergonomics
- Python-native workflow definition

then it belongs to the **SDK / library layer**.

This boundary is much easier to defend than an ad hoc split based on convenience.

## Concrete Implementation Direction
If redesigning toward this model, I would do the following.

### 1. Explicitly declare the project runtime-first
Document the architecture clearly: the runtime is the execution authority, the SDK is for authoring and local mode, and the CLI is the control plane.

This matters because architecture confusion is often downstream of naming confusion. Once the project says what it is, lots of smaller decisions become easier.

### 2. Introduce explicit execution backends
I would add a backend abstraction or execution target model such as:

- `LocalExecutionBackend`
- `RuntimeExecutionBackend`
- `RemoteExecutionBackend`

The goal is not heavy abstraction for its own sake. The goal is to make the execution target explicit and let the ergonomics reflect architectural reality.

### 3. Define serializable submission specs
The runtime handoff should be a real contract, for example:

- `WorkerSpec`
- `WorkflowSubmissionSpec`
- `RunRequest`
- `EvaluationSpec`

The CLI and SDK should submit these specs to the runtime rather than depending on object continuity or ambient memory.

### 4. Keep true local execution as a first-class development mode
The system should still support a real in-process path for research ergonomics. That mode is valuable. But it should be explicit, and it should not distort the architecture of the runtime path.

### 5. Remove ambient cross-boundary assumptions from the runtime path
This includes things like:

- in-memory worker registries
- process-local object recovery assumptions
- logic that depends on the caller process having already created execution state in memory

The runtime path should be reconstructable from persisted specs and durable state.

## Suggested API Shape
One possible API direction would be:

```python
result = await execute_task(task, backend="local")
```

for real in-process execution, and:

```python
run = await submit_workflow(workflow_spec, backend="runtime")
```

or:

```python
client = ArcaneClient(target="local-runtime")
run = await client.submit(workflow_spec)
```

for runtime-backed execution.

This gives users ergonomic symmetry without pretending the two execution models are identical internally.

## Why This Is Better
This proposal improves ergonomics not by hiding the architecture more aggressively, but by making it easier to understand.

Researchers still get:

- a friendly Python authoring interface
- a usable local mode
- a simple way to submit and inspect runs

Operators and future maintainers get:

- a clear runtime boundary
- cleaner control-plane semantics
- better support for retries, recovery, and observability
- fewer hidden process-local assumptions

And the codebase gets a more honest center of gravity, which usually translates into better long-term maintainability.

## Closing View
The uncomfortable feeling you described is real and structurally justified. The current design is carrying a split brain:

- library-style ergonomics on the surface
- runtime-platform reality underneath

The cleanest way out is not to choose one and abandon the other. It is to explicitly choose the runtime as the execution authority and let the library become what it should be: an authoring and client layer with a real local mode.

That gives the project a satisfying answer to the question of what it is:

`arcane_extension` is a runtime platform for orchestrated agent workflows, with a Python SDK for authoring, local experimentation, and runtime submission.

## Concrete Migration Plan
The safest way to move toward a runtime-first architecture is not to rewrite everything around a new abstraction in one pass. The right strategy is to introduce the new model in parallel with the old one, gradually move execution authority toward the runtime, and only remove the current cross-boundary assumptions once the new path is proven. The goal should be to improve correctness and ergonomics without breaking the workflows that are currently letting research move quickly.

The plan below is intentionally staged so that each phase gives you a real architectural benefit on its own. That way, even if the full migration takes time, the system becomes cleaner and more reliable at each step rather than only paying off at the very end.

### Phase 0: Name The Architecture And Freeze The Direction
The first phase is mostly architectural clarification rather than code movement. The project should explicitly state that it is moving toward a runtime-first model with an SDK/client layer and an explicit local mode. This should be written down in the relevant planning docs and reflected in the language used in the CLI help, README, and internal architecture notes.

The purpose of this phase is to prevent the migration from becoming a collection of local fixes with inconsistent intent. Right now the codebase can still justify both "this is a library" and "this is a runtime platform," which makes local design choices feel ambiguous. Once the direction is explicit, future changes can be evaluated against that target. If a design depends on process-local object continuity in the serious runtime path, that should immediately read as suspicious.

The deliverable for this phase is a short architectural position statement and a small terminology cleanup. For example, use language like "submit to runtime" rather than "execute in CLI" for runtime-backed flows, and describe `execute_task()` as local-mode execution unless explicitly routed through the runtime. This sounds soft, but it matters because naming is what keeps a migration coherent.

### Phase 1: Introduce Explicit Execution Modes Without Breaking Existing APIs
The first real code change should be to introduce explicit execution modes while preserving backward compatibility. The important thing is not to force a big front-end API break immediately, but to stop leaving execution semantics implicit. The obvious initial target is something like `backend="local"` versus `backend="runtime"` on the top-level execution/submission path, or an adjacent pair of APIs if that reads more cleanly.

At this stage, local mode can continue to use the existing in-process behavior, while runtime mode can initially delegate to the current orchestration path. The main value is that the caller is now making a meaningful architectural choice, and the code can start reflecting that choice explicitly. Even before the runtime path is fully cleaned up, this change improves ergonomics because the user is no longer asked to pretend that all execution modes are the same thing.

The key compatibility rule in this phase is that existing research workflows should keep working with minimal disruption. If current users call `execute_task(task)` and expect a simple local behavior, that should remain valid, at least temporarily. The migration should add clarity first, then stricter separation later.

### Phase 2: Define And Persist Submission Specs
The next phase is to formalize the boundary contract. Introduce serializable models for the runtime handoff, such as `WorkerSpec`, `WorkflowSubmissionSpec`, `RunRequest`, and any evaluator or benchmark config specs that need to cross the boundary. These should be explicit models, not loosely structured JSON blobs, because the whole point is to replace ambient assumptions with durable contracts.

Once those specs exist, workflow submission should persist or transmit them directly rather than depending on live worker objects surviving into the runtime environment. At first, this can coexist with the current registry-based path if needed. For example, the runtime can persist the spec even if it still also stores the live worker locally as a temporary compatibility measure. The point is to establish the new source of truth before deleting the old path.

This phase is where the migration starts becoming structurally meaningful. Once the runtime has enough information to reconstruct what it needs from persisted specs, the container boundary stops being awkward and starts becoming normal. That is the beginning of a real runtime architecture rather than a library that happens to have a container around it.

### Phase 3: Introduce A WorkerFactory And Runtime Reconstruction Path
With persisted specs in place, the next step is to make the runtime actually reconstruct workers from those specs. This should be done through a dedicated `WorkerFactory` or similar service rather than by scattering reconstruction logic across different execution functions. The factory should be responsible for turning a persisted worker spec into a runtime worker instance with the right model, prompts, benchmark configuration, and toolkit expectations.

Initially, this reconstruction path should be added in parallel with the in-memory worker lookup path. In other words, if the spec exists and reconstruction succeeds, use it. If not, temporarily fall back to the legacy registry behavior. This lets you deploy and test the new approach without making the whole system brittle during migration. Over time, the fallback can be removed once the spec-backed path is proven.

This is also the phase where you begin to reclaim conceptual cleanliness. Once `worker_execute` gets a worker from a factory that is backed by durable runtime data, it stops having to rely on the illusion that the caller's object identity still matters. That is the transition from "cross-process library trick" to "real runtime execution."

### Phase 4: Split Local Execution From Runtime Submission More Clearly
Once worker specs and runtime reconstruction exist, the system should separate local execution and runtime submission at the API and CLI level more clearly. This does not necessarily require a large user-facing break, but it does require the code to stop conflating "run now in this Python process" with "submit a run to the orchestrated system."

At this point I would seriously consider making the user-facing model more explicit, for example:

- `execute_task(..., backend="local")` for in-process execution
- `submit_workflow(...)` or a client-based submission API for runtime execution

The CLI should begin shifting toward operator verbs rather than pretending to host the real execution itself. Commands like "submit," "watch," "inspect," and "tail logs" become much more natural once the runtime is recognized as the execution authority.

This phase is important ergonomically. It is the point where the user-facing story starts to match the architecture. The system becomes easier to explain because it is no longer trying to use one mental model for two very different execution paths.

### Phase 5: Remove The In-Memory Worker Registry From The Runtime Path
Only after the spec-backed runtime path is proven should the in-memory worker registry be removed from the serious runtime path. This is a key sequencing point: if you delete the old mechanism too early, you risk introducing instability during the transition. If you keep it too long, it remains a source of conceptual and operational confusion.

The removal should be strict for runtime-backed execution. By the end of this phase, the runtime path should be fully reconstructable from persisted specs and durable state. That means no hidden dependency on `store_workers_from_task()`, no expectation that `benchmark_run_start` and `worker_execute` share process memory, and no fallback to ambient worker lookup in the runtime flow.

This does not mean every trace of the worker registry must disappear immediately. It may still be acceptable to keep an in-process helper for pure local execution if that remains the simplest local-mode implementation. The key is that it becomes a local-mode implementation detail rather than an architectural dependency of the runtime system.

### Phase 6: Tighten Runtime Contracts And Execution Services
Once the boundary is real, the surrounding contracts should be cleaned up. This is where I would introduce the narrower protocols and service decomposition discussed elsewhere: `WorkerFactory`, `ExecutionContextBuilder`, `WorkerRunner`, `ActionRecorder`, `ExecutionPersister`, and `DashboardPublisher`. By this phase, those abstractions will be easier to define correctly because the runtime boundary itself is no longer fuzzy.

This is also the right time to replace weak `Any`-based fields in the runtime path with small protocols. The goal is not to make every dynamic thing statically perfect. The goal is to make the runtime interfaces explicit enough that different parts of the system can evolve independently without hidden assumptions. Once the architecture is runtime-first, this sort of contract cleanup starts paying off much more than it does in the current ambiguous state.

I would avoid doing too much of this earlier. If you try to perfect the internal abstractions before the architectural boundary is fixed, you risk polishing the wrong shape. Once the handoff model is explicit, however, the right service seams become much more obvious.

### Phase 7: Redesign The CLI As A Control Plane
After the runtime path is clearly authoritative, the CLI can be redesigned around what it actually is: a control-plane tool for researchers and operators. This is the phase where commands should become more obviously service-oriented, and where local developer workflows like `dev up` / `dev down` / `run submit` / `run watch` start to feel like the main path rather than bolt-ons around an implicit library execution model.

This is also the moment to improve the quality of user feedback. A runtime-first CLI should tell the user whether they are in local mode, runtime mode, or remote mode; where the run is being executed; how to inspect it; and what kind of guarantees they are getting. That is an ergonomic win not because it hides complexity, but because it makes complexity legible and well-managed.

The main risk here is overcomplicating the CLI before the lower layers are ready. That is why this phase comes after the execution path has already been made honest. Once the runtime/SDK split is real, the CLI redesign becomes a simple expression of that split rather than another source of architectural confusion.

### Phase 8: Add Invariants And Recovery Tests For The New Model
The final phase is to harden the new architecture with tests that validate the things the migration was meant to improve. These should include recovery-from-spec behavior, runtime reconstruction correctness, local versus runtime behavior parity where appropriate, action attribution correctness under the new execution model, and explicit tests that prove the runtime no longer depends on process-local worker state.

This phase matters because migrations often stop at "the code is cleaner now" without fully proving that the new invariants hold. Here, the key invariants are architectural: runtime execution must be reconstructable from durable state; local execution must remain ergonomic; the runtime submission path must not depend on caller memory; and the CLI must be an honest client of the runtime rather than a hidden host of execution state.

When this phase is done well, the codebase gets more than a new shape. It gets new guarantees. That is what makes the migration worth doing.

## Migration Order Summary
If reduced to the shortest sensible sequence, the migration order should be:

1. Declare the architecture and terminology.
2. Add explicit execution modes.
3. Define serializable workflow and worker specs.
4. Persist submission specs on the runtime path.
5. Add a spec-backed `WorkerFactory`.
6. Separate local execution from runtime submission more clearly.
7. Remove the in-memory worker registry from runtime-backed execution.
8. Tighten internal contracts and split runtime services.
9. Redesign the CLI around control-plane semantics.
10. Add recovery and invariants tests around the new model.

## What Not To Do
There are a few migration mistakes I would actively avoid.

Do not try to delete the current path in one pass. That risks turning an architectural cleanup into a destabilizing rewrite. The right move is to introduce the new model in parallel, prove it, and then deprecate the legacy assumptions.

Do not over-abstract too early. If the runtime boundary is still conceptually fuzzy, a lot of internal abstraction work will just be rearranging the old ambiguity into cleaner-looking modules. Get the boundary right first, then harden the internals around it.

Do not sacrifice local research ergonomics in the name of architectural purity. Local mode is genuinely valuable. The goal is not to eliminate it. The goal is to stop letting local-mode assumptions leak into the runtime architecture.

## Expected End State
If the migration is successful, the final shape should feel much more natural:

- researchers define workflows and workers through a Python SDK
- local experimentation uses an explicit in-process mode
- runtime-backed execution is submitted through a clear client/runtime boundary
- the CLI acts as a control plane for the runtime
- the runtime reconstructs everything it needs from durable state and persisted specs
- Docker stops feeling like an awkward implementation detail and starts feeling like the obvious home of the execution platform

That would give the system a much cleaner answer to the question that is currently bothering you. It would no longer be trying to decide whether it is a library or a runtime while executing. It would know: it is a runtime platform, and the library is how you author and talk to it.

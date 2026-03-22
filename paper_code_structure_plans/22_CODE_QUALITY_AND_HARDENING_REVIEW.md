# Arcane Extension Code Quality And Hardening Review

## Scope
This note consolidates the prior assessment of:

- `arcane_extension`
- `manager_agent_gym` as the earlier iteration
- what would move `arcane_extension` closer to a 9/10
- the messiest / highest-risk part of the current codebase
- what to do to bulletproof it
- a rough read on the engineering capability signaled by these codebases

This is a static code-read judgment, not a runtime or benchmark-performance evaluation.

## Executive Summary
`arcane_extension` is a meaningfully cleaner and better-shaped codebase than `manager_agent_gym`. It has clearer package boundaries, a more coherent public API, stronger architectural intent, and somewhat better repo hygiene. It still reads as a serious research/internal platform rather than a fully hardened product or library.

The main thing holding it back is not the overall architecture, but the runtime seam where worker execution, worker identity, action tracing, persistence, and dashboard attribution all meet. That seam is powerful and already fairly thoughtful, but it still relies on some implicit assumptions and some post-hoc reconstruction that make it the highest-risk part of the system.

## Overall Quality Ranking
If ranking the two codebases by general code hygiene and writing quality:

1. `arcane_extension`
2. `manager_agent_gym`

The gap is real but not enormous.

## Arcane Extension Assessment
### What is strong
- Better package boundary discipline than the older repo.
- Clearer split between public API and internal machinery.
- Good use of modern Python patterns: Pydantic v2, SQLModel, typed DTO-style models, explicit config.
- Strong architectural intent around benchmarks, orchestration, dashboard events, and persistence.
- Better top-level API ergonomics than `manager_agent_gym`.
- Reasonable test taxonomy and evidence of deliberate testing strategy.

### What keeps it out of the top tier
- CI does not appear to run `pytest`, so behavior is not enforced as part of the main quality gate.
- The execution/runtime seam still carries too many responsibilities.
- Some key runtime boundaries are weakly typed.
- Some attribution and identity logic is inferred rather than first-class.
- There are still places where operator-facing documentation and actual runtime assumptions can drift.

### Rough score
- `arcane_extension`: about `7/10`, potentially higher if the hardening work lands well

## Manager Agent Gym Assessment
### What is strong
- Ambitious platform-level thinking.
- Broad test surface and signs of a serious research-engineering workflow.
- Good evidence of architectural intent around schemas, workflows, agent abstractions, and evaluation.
- Strong examples/docs investment relative to a typical research repo.

### What is weaker
- Repo hygiene is rougher due to heavier workspace clutter and broad dependency scope.
- Packaging is less cleanly separated between runtime, research, docs, and dev concerns.
- The top-level package surface is much thinner / less polished.
- Documentation and real code layout show more drift.
- Large core modules accumulate a lot of responsibility.

### Rough score
- `manager_agent_gym`: about `6.5-7/10`

## Why Arcane Feels Better Than MA-Gym
The clearest improvement is not that `arcane_extension` is smaller or simpler. It is that it shows better engineering judgment around boundaries.

Notable improvements:

- More coherent public API surface.
- Better separation of internal vs public concepts.
- Better directional movement toward typed contracts.
- Better structure around benchmark registry and orchestration.
- More evidence of intentional cleanup rather than pure accumulation.

`manager_agent_gym` feels like a strong exploratory platform. `arcane_extension` feels like the same person learning how to turn exploratory platform code into a more maintainable system.

## What Would Bring Arcane Extension To A 9
The codebase does not need a totally different architecture to reach a 9/10. It needs stronger confidence machinery and harder runtime boundaries.

### Highest-leverage upgrades
1. Add real Python test execution to CI.
2. Tighten the worker execution seam so runtime identity and persistence are explicit rather than implied.
3. Make action attribution first-class in storage instead of inferred later.
4. Replace weak `Any`-style runtime contracts with narrower protocols.
5. Reduce dependency on process-local assumptions.
6. Keep docs, setup requirements, and runtime expectations fully aligned.
7. Keep decomposing high-responsibility execution/orchestration paths into smaller units.

### What a 9/10 version would feel like
A 9/10 version would feel like the same system, but one where:

- refactors are safer
- failures are easier to replay and diagnose
- worker/task/action identity is deterministic
- horizontal scaling or process separation is less scary
- setup and CI are trustworthy
- the project is less dependent on author memory/context

## The Messiest Part
The messiest part of the current codebase is not the sandbox package by itself. The sandbox code has already improved materially by being split into a package rather than remaining one giant file.

The messiest part is the **worker execution boundary**:

- `h_arcane/benchmarks/common/workers/react_worker.py`
- `h_arcane/core/_internal/task/inngest_functions/worker_execute.py`
- `h_arcane/core/_internal/task/worker_context.py`
- `h_arcane/core/_internal/api/runs.py`
- the related action / task execution persistence models

### Why this seam is the riskiest
This seam currently combines:

- worker instance transport
- worker reconstruction / retrieval
- toolkit injection
- vendor/framework transcript interpretation
- action extraction
- persistence
- tracing
- dashboard event attribution

Each individual part is understandable, but together they create a zone where correctness depends on multiple implicit assumptions lining up.

## Specific Fragilities
### 1. Process-local worker registry
Worker instances are passed through an in-memory global mapping keyed by `task_id`. That means execution relies on process locality and lifecycle assumptions.

Why this is fragile:

- restart-sensitive
- hard to scale across processes
- easy to leak lifecycle state
- harder to reason about deterministically than persisted worker specs

### 2. Action lineage is not first-class
`Action` has `run_id` and `agent_id`, but not `task_id` or `task_execution_id`. The run snapshot layer later infers task mapping heuristically.

Why this is fragile:

- action attribution can become ambiguous
- dashboards and detail views may show the wrong task associations
- the system has to guess relationships that should be stored explicitly

### 3. Actions are reconstructed from framework transcript shape
`ReActWorker` extracts actions by parsing `pydantic_ai` message objects and matching tool calls with later returns.

Why this is fragile:

- depends on vendor/framework transcript structure
- harder to guarantee as the framework evolves
- partial failures become recovery puzzles instead of straightforward event logs
- auditability depends on interpretation rather than on native recording

### 4. Weak runtime typing exactly where the system is most dynamic
Important execution context fields such as toolkit, sandbox, and tracing hooks still rely on `Any` or loose contracts.

Why this is fragile:

- contract drift is easier
- integration bugs move from type-check time to runtime
- worker authors get less help from the type system

### 5. Too many responsibilities cross the same seam
The runtime path currently does too much in one flow:

- context building
- worker execution
- action interpretation
- action persistence
- trace emission
- dashboard publication

This is manageable today, but it is the place most likely to turn into a maintenance bottleneck.

## What To Do To Bulletproof It
### 1. Replace the in-memory worker registry with persisted worker specs
The first change I would make is to remove the process-local `_TASK_WORKERS` mapping from the critical path and replace it with a persisted worker description. Concretely, that means introducing a small serializable model such as `WorkerSpec` or `WorkerRuntimeSpec` that captures the minimum information needed to rebuild a worker inside the execution environment: worker type, model, worker config, benchmark name, and any worker-specific options needed for construction. That spec should be persisted alongside the run or task execution metadata rather than stored only in memory.

Once that exists, `benchmark_run_start` and `execute_task()` should stop relying on `store_workers_from_task()` as the primary mechanism for passing worker instances across the runtime boundary. Instead, they should persist the worker spec when the workflow is created, and `worker_execute` should reconstruct the worker from that spec using a `WorkerFactory`. The same applies to the seeded experiment flow: rather than reconstructing a `ReActWorker` and then pushing it into an in-memory dictionary with `store_worker_for_tree()`, the flow should record the spec that says "for this run, this task tree uses this worker configuration" and let execution retrieve it deterministically.

The reason this matters is that the current approach only works because several assumptions happen to hold at once: the relevant functions run in the same container, the process stays alive, memory has not been cleared, and no future scaling strategy breaks locality. Those are acceptable assumptions in a proof-of-concept but not in a hardened execution system. A persisted worker spec makes the system process-safe, retry-safe, and far easier to reason about under failure, because the source of truth moves from transient runtime state into durable data.

This would also improve testing quality. Tests would be able to assert that a given run can be resumed, retried, or replayed from persisted metadata without having to reconstruct fragile setup state in memory. That is a very large step toward making the orchestration layer feel like infrastructure rather than a clever in-process pipeline.

### 2. Add `task_id` and `task_execution_id` to `Action`
The second change is to make action lineage explicit in the schema instead of inferred later. Today `Action` records know about `run_id` and `agent_id`, but they do not directly record the task or execution attempt that produced them. I would extend the `Action` model to include `task_id` and `task_execution_id`, add the corresponding indexes, and update the action creation flow so those fields are set at the moment the action is created rather than reconstructed afterward.

That change should flow through the runtime in a straightforward way. `worker_execute` already knows `task_id` and `execution_id` at the point it invokes the worker. The execution context passed to the worker should include those identifiers as first-class fields, and any action built during the run should carry them. Then `queries.actions.create()` persists them as direct facts. The run detail API no longer needs to infer task ownership via `agent_mapping`, default task fallbacks, or "exactly one candidate task" logic, because the action itself can answer the question of where it came from.

The reason I would prioritize this highly is that attribution bugs are the kind that corrode trust quietly. If a dashboard or run detail page shows an action under the wrong task, the system can still look superficially healthy while giving a false operational picture. This is worse than a loud crash because it undermines observability. Once action lineage is first-class, snapshot generation becomes much simpler, the API becomes less heuristic, and the audit trail becomes much stronger.

This would also set up later improvements cleanly. Once actions are directly keyed to tasks and execution attempts, it becomes much easier to reason about retries, partial failures, per-task telemetry, and any future replay or debugging tools. It turns actions from "events we interpreted later" into "immutable facts attached to a specific execution attempt."

### 3. Make action recording a first-class execution concern
The third change is to stop treating transcript parsing as the canonical way actions enter the system. Right now `ReActWorker` builds the action trace by walking framework message objects, tracking pending tool calls, and pairing them with later returns. That is sophisticated and useful, but it should not be the primary source of truth for execution facts. I would introduce an `ActionRecorder` or `ToolInvocationRecorder` that records action start, completion, failure, timing, input, output, and error as part of the real tool invocation lifecycle.

In practice, that means wrapping or instrumenting tool execution at the point where the system knows a tool was actually invoked, rather than reconstructing that fact after the model run ends. If the worker framework allows hooks around tool calls, use those hooks. If not, wrap the benchmark tools in recorder-aware callables before giving them to the agent. The resulting recorder should be responsible for emitting durable action objects tied to the current `task_id`, `task_execution_id`, `agent_config_id`, and `run_id`. Transcript parsing can remain for debugging and richer telemetry, but it should become secondary and optional rather than foundational.

This matters because the current design couples your core action history to the internal message semantics of `pydantic_ai`. If the framework changes how messages are represented, if a partial failure interrupts the transcript in an odd place, or if the model emits a surprising sequence of parts, your core execution history becomes harder to trust. First-class recording reduces that vendor coupling and replaces "best-effort interpretation" with a stronger invariant: if a tool really executed, the system recorded it as it happened.

This is also the change that most directly improves replayability and debugging. A real action recorder gives you a cleaner timeline, simpler failure semantics, and more confidence that the persisted trace matches actual runtime behavior. That is exactly the sort of foundation you want if this system is going to become more production-like over time.

### 4. Split the execution seam into explicit services
The fourth change is structural: split the runtime seam into a small set of explicit services so that each part owns one kind of responsibility. Right now the worker execution path effectively does context assembly, worker access, framework execution, action extraction, persistence, trace emission, and dashboard publishing in one broad flow. Even when the code is readable, that shape makes it harder to modify one concern without accidentally affecting another.

The target structure I would aim for is something like: `WorkerFactory` to construct runtime workers from persisted specs; `ExecutionContextBuilder` to assemble a typed `WorkerContext`; `WorkerRunner` to invoke the worker and normalize success/failure; `ActionRecorder` to own action facts; `ExecutionPersister` to persist actions, outputs, task execution updates, and any related metadata; and `DashboardPublisher` to convert persisted facts into dashboard events. These do not have to be large classes, but they should be explicit seams with clear inputs and outputs.

The reason for doing this is not abstraction for its own sake. It is to make the runtime path easier to reason about and safer to evolve. Right now, if you want to change action attribution, add replay support, or improve tracing, you have to work inside a path where the responsibilities are tightly interleaved. Explicit services reduce the blast radius of changes, make tests more targeted, and make it easier to describe the architecture to future contributors without relying on tacit knowledge.

This sort of decomposition also tends to reveal missing invariants. Once you force yourself to define what, say, `ExecutionPersister` consumes and what `DashboardPublisher` publishes, you quickly see where the system is still relying on partially interpreted state or incidental ordering. That is why this change is not just cleanup; it is a mechanism for surfacing and eliminating hidden coupling.

### 5. Strengthen runtime protocols
The fifth change is to tighten the type contracts at the runtime boundary, especially in `WorkerContext` and the benchmark toolkit interfaces. I would replace the loose `Any` fields for toolkit, sandbox, trace sink, and trace context with small protocols that describe exactly what the worker is allowed to rely on. For example, the worker-facing sandbox contract probably does not need the entire concrete E2B type. It likely needs a compact protocol exposing the specific command, file, and code-execution methods the worker uses. The same applies to toolkit and tracing.

Concretely, that means introducing narrow interfaces such as `ToolkitProtocol`, `SandboxProtocol`, `TraceSinkProtocol`, and perhaps a minimal typed context object for trace propagation. `WorkerContext` should carry those protocol types, and `BaseToolkit` should stop returning raw `list` or other weakly typed structures where more specific return types are available. The goal is not perfect static typing of every dynamic part of the system. The goal is to make the integration contract legible, enforceable, and easier to evolve safely.

This matters because the most dynamic part of the system is also the part doing the most important work. When that seam is typed as `Any`, a lot of integration mistakes move from development time into runtime behavior. You lose autocomplete, lose type-checking value, and make it easier for worker and orchestration code to drift apart silently. Tight protocols convert a fuzzy boundary into a real contract that both sides can depend on.

This also improves the extensibility story. If you eventually want more than one worker type, more than one toolkit implementation, or a different sandbox backend, protocol-oriented contracts will make those additions feel like supported extensions instead of special-case hacks. That is a hallmark of a system that is maturing well.

### 6. Make lifecycle cleanup explicit
The sixth change is a transitional hardening step: if the in-memory registry remains for any period of time, cleanup needs to become explicit and enforced. Right now the project has cleanup helpers such as `clear_worker()` and `clear_workers_from_task()`, but the important thing is not whether the helpers exist. The important thing is whether the lifecycle guarantees are built into the runtime so that cleanup happens under success, failure, timeout, interruption, and retry paths.

In practical terms, I would add `finally`-based cleanup in every execution path that currently stores workers in memory, and I would make that cleanup visible in tests. If workflow execution starts and then errors halfway through, the system should still release the process-local worker state. If a seeded experiment flow reconstructs workers for an entire tree, that state should not remain indefinitely after the run finishes. If multiple test runs happen in one long-lived process, earlier worker registrations should not leak into later runs. Those need to become tested lifecycle guarantees, not good intentions.

This matters because process-local state has a habit of becoming "fine until it suddenly is not." Leaks here do not always cause immediate crashes; they often create the worst class of bugs: nondeterministic failures, stale lookups, surprising cross-test contamination, and weird local-only behavior that disappears when reproduced differently. Explicit cleanup turns this from an ambient assumption into something the runtime actually enforces.

Even if you fully remove the registry later, doing this interim hardening still has value. It reduces the current system's fragility immediately and gives you a cleaner baseline from which to migrate toward persisted worker specs. In other words, it is worth doing even if it is not the final architecture.

### 7. Add invariants-focused tests
The seventh change is to build a test layer around invariants rather than only around happy-path behavior. The runtime seam is most vulnerable not to obvious syntax bugs, but to subtle correctness failures under multi-task attribution, retries, interruptions, and partially completed tool activity. The test suite should therefore target those cases directly rather than relying mostly on normal end-to-end success scenarios.

The specific test cases I would add are the ones most aligned with the current risk profile: a single worker reused across multiple tasks in one workflow; an interrupted or failed worker run that still emits a partial trace; retries or multiple execution attempts for one task; action attribution under multi-task runs; recovery assumptions when orchestration state is rebuilt; and the correctness of run-detail/dashboard snapshots when multiple related entities exist. These tests should be written at the level where the invariant lives. For example, attribution tests should assert on persisted action lineage and API snapshots, not only on internal helper behavior.

The reason this matters is that the hardest bugs in this system are not "the function crashed immediately." They are "the system mostly worked, but the persisted truth is wrong or ambiguous." Those bugs are exactly what invariants-focused tests are good at catching. They force you to make the runtime's guarantees explicit: what must always be true after a retry, what must always be true about action ownership, what must always be true after partial failure, and what the dashboard is allowed to assume.

This kind of testing is also what makes future refactors much safer. If you are going to replace the worker registry, change action recording, or decompose the execution seam, you need tests that protect the behavioral truths of the system rather than just the shape of the current implementation. That is how you harden a fast-moving research codebase without freezing it.

## Suggested Hardening Order
If optimizing for leverage and safety, the suggested order is:

1. Add `task_id` and `task_execution_id` to `Action`.
2. Remove heuristic action-to-task inference from `runs.py`.
3. Introduce a persisted worker spec and phase out `_TASK_WORKERS`.
4. Move to first-class action recording.
5. Tighten worker/runtime protocols.
6. Expand tests around invariants and recovery.
7. Add fast `pytest` runs to CI if not already present.

## Capability / Seniority Signal
Based on `manager_agent_gym` and `arcane_extension`, the engineering signal is roughly:

- clearly beyond junior
- strong mid-level to senior from code alone
- very plausibly senior research engineer
- startup/founding environment fit is strong
- staff-level upside is visible, but not fully proven just from codebase hardening and abstraction discipline yet

### What these codebases signal positively
- strong systems-building instinct
- ability to architect research platforms rather than isolated scripts
- comfort spanning ML, orchestration, backend, tools, and evaluation
- ability to iterate and improve architectural shape over time

### What would signal the next level
The next level is less about building something complex and more about:

- simplifying complex systems into cleaner ones
- creating hard-to-break defaults and invariants
- making a broader team faster through architecture and process choices
- turning research systems into durable operational infrastructure

## Final Judgment
`arcane_extension` is a good codebase with strong research-engineering taste and clear improvement over the earlier repo. The main thing to harden is not the broad architecture but the execution seam where worker state, action traces, and persistence intersect.

That seam is the best target for serious engineering improvement because it is where the project is most likely to suffer from:

- incorrect attribution
- difficult-to-replay failures
- hidden process-local assumptions
- vendor-coupled runtime behavior
- subtle breakage under scale or retries

If this area is cleaned up and backed by stronger CI/test guarantees, `arcane_extension` could move from a good internal research platform toward something that genuinely feels 9/10 in engineering quality.

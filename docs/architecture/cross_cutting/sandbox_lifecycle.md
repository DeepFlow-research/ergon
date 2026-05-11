# Cross-Cutting — Sandbox Lifecycle

## Purpose

The sandbox is the live environment shared by worker execution and task evaluation. A worker writes files and intermediate state into the sandbox; evaluators and criteria may inspect that same environment before teardown. Lifecycle ownership is coordinated by the runtime, not by benchmark workers.

## Current Abstractions

- **`Sandbox`** is the public benchmark-authored definition. It declares how to provision and terminate an environment.
- **`SandboxRuntime`** is the internal protocol that backs public operations such as command execution and file I/O.
- **`SandboxLifecycleHub`** is the framework-owned coordinator that acquires, caches, releases, and discards live sandbox instances for `(run_id, task_id)`.
- **Builtin E2B sandboxes** derive from the public `Sandbox` base through direct E2B adapters. The old `BaseSandboxManager` / `DefaultSandboxManager` path has been removed.

## Control Flow

```
task ready
  -> worker_execute resolves RunGraphNodeView.task
  -> SandboxLifecycleHub.acquire(run_id, task_id, task.sandbox)
  -> Sandbox.provision() creates the live runtime if needed
  -> Worker.execute(task, context, sandbox) runs with the live public Sandbox
  -> evaluator dispatch passes the same task Sandbox to criteria
  -> runtime releases or discards the sandbox through SandboxLifecycleHub
```

## Invariants

1. **Sandbox lifecycle is framework-owned.** Workers and criteria receive a `Sandbox` object; they do not construct provider clients directly or close shared task sandboxes on their own.
2. **The task sandbox is keyed by `task_id`.** The graph and telemetry no longer use a separate node identity for lifecycle lookups.
3. **Criteria receive capabilities explicitly.** `CriterionContext` remains pure data and criteria use the `sandbox` argument for live environment access.
4. **Resource materialization is sandbox-owned.** Workflow services should not copy resources directly into live environments; public sandbox operations own that boundary.
5. **Builtin setup belongs to sandbox definitions/toolkits.** Benchmark-specific manager subclasses are gone. If a benchmark needs a special template, use a concrete `Sandbox` subclass or toolkit spec rather than reintroducing manager-backed setup.

## Anti-Patterns

- Reintroducing `BaseSandboxManager` or manager-backed public sandboxes.
- Creating a fresh provider sandbox inside a criterion instead of using the task sandbox passed by the runtime.
- Closing or killing a sandbox from worker code as part of normal success.
- Duplicating lifecycle identity with `node_id` when `task_id` is already the canonical key.

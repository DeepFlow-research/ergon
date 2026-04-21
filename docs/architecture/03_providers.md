# 03 — Providers

## 1. Purpose

The providers layer is Ergon's boundary between runtime code and external execution substrates. It owns four concerns: resolving `model_id` strings to `pydantic_ai.models.Model` instances, provisioning and tearing down E2B sandboxes via per-benchmark manager subclasses, surfacing sandbox state transitions as dashboard events, and publishing worker outputs as content-addressed blobs that evaluators can re-read. Everything that crosses the process boundary (LLM API, container runtime, blob storage) is routed through this layer so the runtime, workers, and evaluators stay substrate-agnostic.

## 2. Core abstractions

| Name | Kind | Location | Freeze status | Owner |
| --- | --- | --- | --- | --- |
| `_BACKEND_REGISTRY` | module-level dict | `ergon_core/core/providers/generation/model_resolution.py` | Frozen shape; entries grow via registration. | Providers layer. |
| `resolve_model_target` | function | `ergon_core/core/providers/generation/model_resolution.py` | Public, frozen signature. Returns `ResolvedModel`. | Providers layer. |
| `register_model_backend` | function | `ergon_core/core/providers/generation/model_resolution.py` | Public, frozen signature. | Providers layer; callers are backend modules executing at import time. |
| `BaseSandboxManager` | abstract class + singleton | `ergon_core/core/providers/sandbox/manager.py` | Shape stable; `event_sink` activation path in flux. | Providers layer. |
| `DefaultSandboxManager` | concrete class | `ergon_core/core/providers/sandbox/manager.py` | Frozen. | Providers layer. |
| `SWEBenchSandboxManager`, `MiniF2FSandboxManager`, `ResearchRubricsSandboxManager` | concrete subclasses | `ergon_builtins/` | Owned per benchmark; singletons. | Benchmark authors. |
| `SandboxEventSink` | `typing.Protocol` | `ergon_core/core/providers/sandbox/event_sink.py` | Frozen protocol; activation path in flux. | Providers layer. |
| `NoopSandboxEventSink`, `DashboardEmitterSandboxEventSink` | implementations | `ergon_core/core/providers/sandbox/event_sink.py` | Frozen. | Providers layer. |
| `SandboxResourcePublisher` | class | `ergon_core/core/providers/sandbox/resource_publisher.py` | Frozen API; storage backend swappable via `ERGON_BLOB_ROOT`. | Providers layer. |
| `TransformersModel` | `pydantic_ai.models.Model` subclass | `ergon_builtins/ergon_builtins/models/transformers_backend.py` | Frozen. | ML team (TRL training loop callers). |

### 2.1 Generation registry

`_BACKEND_REGISTRY` is a prefix-keyed dispatch table of resolver callables. `resolve_model_target` splits the target on its first colon, dispatches to the resolver, and returns a `ResolvedModel` wrapping either a `pydantic_ai.models.Model` instance or a passthrough string. Unknown prefixes fall through to a passthrough `ResolvedModel` — PydanticAI's own `infer_model` is invoked on use. Backends mutate the registry at import time; the builtins pack registers all four in a single loop at `ergon_builtins/ergon_builtins/registry.py:81`.

The four prefixes registered today are `vllm:*` (local vLLM server via PydanticAI's `OpenAIChatModel`), `openai:*` / `anthropic:*` / `google:*` (passthrough to `infer_model`), and `transformers:*` (custom `TransformersModel` for TRL-trained checkpoints not served over vLLM).

Workers are expected to hold no hardcoded SDK client constructions (`AsyncOpenAI`, `anthropic.Client`, `genai.Client`). This is an invariant (Section 4), not a coincidence, and is currently honored — enforcement is grep discipline.

### 2.2 Sandbox managers

`BaseSandboxManager` is both abstract and a **singleton per subclass**. The singleton is load-bearing: criteria and workers reconnect to a running sandbox by re-instantiating the subclass and calling `get_sandbox(task_id)`, which reads shared class-level state. This works only because all actors run inside the same Python process; see Section 4, invariant 3.

A `template: ClassVar[str] | None` names the E2B template. Subclasses usually set the class attribute; `SWEBenchSandboxManager` instead assigns `self.template` in `__init__` from a pinned-template-id file written by `ergon benchmark setup swebench-verified`, because its template is rebuilt periodically.

Three lifecycle hooks are defined for subclasses:

- `_create_directory_structure` — concrete on the base class; lays out `/inputs`, `/workspace`, `/skills`, `/tools` and smoke-tests writability. Override only if the default set is wrong.
- `_install_dependencies` — abstract today; expected to become optional with a concrete no-op default (tracked by the process-state RFC below).
- `_verify_setup` — concrete no-op; override to raise on template/env mismatch.

`create()` takes a sandbox key, run id, timeout, envs, and display-task id. The `sandbox_key` / `task_id` / `display_task_id` triplet is **debt**: in every current call site they collapse to one value, except the SWE-Bench evaluator criterion which spawns a fresh `uuid4()`. The three-parameter shape is kept because it appears in every caller; collapse is scoped in `docs/rfcs/active/2026-04-18-sandbox-manager-key-cleanup.md`.

`event_sink` is a **constructor** parameter, not a `create()` kwarg. Because the subclass is a singleton, the first construction wins; subsequent constructions with a non-None `event_sink` silently overwrite the shared instance's sink. That stomp is a latent race tracked in `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md` (P3); the fix direction is a class-level `set_event_sink()` setter called once at app init.

**Sandbox lifecycle is per-task.** One sandbox per task per run, kept alive across all of `Worker.execute()`'s generator turns, across the task-completion boundary, and through the full fan-out of evaluator criteria. Teardown runs only after every criterion terminates, via the static `BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)` invoked from `ergon_core/core/runtime/inngest/check_evaluators.py:82`. The static method is the sole cross-process teardown path — it does not touch class-level state, which is why Inngest steps can call it without sharing process identity with the worker. Teardown does NOT run during `finalize_success`. See `cross_cutting/sandbox_lifecycle.md` for the definitive treatment.

There is no `reconnect()` method. In-process criteria reconnect via `get_sandbox(task_id)` reading shared class state. Cross-process criteria (production case: SWE-Bench) spawn a fresh sandbox of their own rather than reconnecting. Moving "reconnect" onto a real cross-process primitive is the subject of `docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md`.

### 2.3 DefaultSandboxManager

`DefaultSandboxManager` is the documented default for benchmarks whose only requirement is the stock E2B image: no pinned template, no install step, no verify step.

Its `create()` overrides the base to gracefully skip provisioning when `E2B_API_KEY` is absent, returning the `SANDBOX_SKIPPED` sentinel; downstream task-events machinery short-circuits on that sentinel. This is what makes stub-mode CI runs work without an E2B key — the worker runs, the criterion evaluator runs, and no sandbox is provisioned.

### 2.4 SandboxEventSink

`SandboxEventSink` is a `typing.Protocol` with async hooks for sandbox create, per-command execution, and close. Two implementations ship: `NoopSandboxEventSink` (default) and `DashboardEmitterSandboxEventSink` (forwards to the dashboard emitter).

**Status as of 2026-04-18: unwired on the live path.** Every `BaseSandboxManager` construction site omits `event_sink=`, so every manager runs with the noop default (grep `SandboxManager(` for the call sites). There is no second, inline path — `dashboard_emitter.sandbox_*` has zero callers anywhere in the tree. Consequence: the dashboard's sandbox view populates only on cold-start via the REST snapshot in `build_run_snapshot()`. Symptom tracked in `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md`.

The broader `DashboardEmitter` surface is similarly partial: most of its typed methods (including the sandbox trio and `resource_published`) are defined but unwired. Tracked in `docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md`.

### 2.5 SandboxResourcePublisher

`SandboxResourcePublisher` is a content-addressed blob store writer. The blob root is `ERGON_BLOB_ROOT` (default `/var/ergon/blob`). Its contract:

1. Workers write files under a configured sandbox directory (default `/workspace/final_output/` as `RunResourceKind.REPORT`; managers override `publish_dirs` to add more).
2. `publisher.sync()` lists each directory, reads bytes, SHA-256-hashes, and writes to `<blob_root>/<hash[:2]>/<hash>`.
3. Writes are atomic on POSIX (`.tmp` then rename); hash collisions short-circuit.
4. One `run_resources` row is appended per new hash; content-hash dedup keeps repeated `sync()` calls idempotent.
5. Non-filesystem artifacts (e.g. `WorkerOutput` fields) go through `publish_value(kind, name, content, ...)`, which writes through the same blob path without listing a directory.

Workers never write to `<ERGON_BLOB_ROOT>` directly; the publisher is the single writer (invariant 6).

There is no `dashboard_emitter.resource_published` call from `publish()` today; the dashboard picks up resources only via the cold-start REST snapshot. Evaluator retrieval is ad-hoc — each criterion reads `run_resources` directly and re-reads blob bytes. Unification behind `CriterionRuntime.read_resource(name)` is scoped in `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md`.

### 2.6 Template registry / benchmark setup

There is no centralized template registry. Each benchmark that needs a custom Docker template owns its own Dockerfile, inside-image setup script, and pinned-template-id file under its benchmark directory; SWE-Bench (`ergon_builtins/benchmarks/swebench_verified/sandbox/`) is the reference. A CLI subcommand `ergon benchmark setup <slug>` builds the template and writes the pin.

The decentralized shape means `ergon benchmark setup` iterates over whatever subcommands happen to be registered — a new benchmark shipping with a required template but forgetting the subcommand registration will be silently skipped. A `TEMPLATE_REGISTRY` closing this hole is scoped in `docs/rfcs/active/2026-04-18-template-spec-public-api.md`.

## 3. Control flow

```
Worker.execute()
    |
    +-> resolve_model_target(self.model)  -->  ResolvedModel
    |       (prefix dispatch; 4 backends + fallthrough to infer_model)
    |
    +-> ManagerClass()                    (singleton; returns cached instance)
    |   ManagerClass().create(sandbox_key=task_id, run_id=run_id, ...)
    |       +-> per-key asyncio.Lock, idempotent on existing sandbox
    |       +-> AsyncSandbox.create(template=<pinned>, ...)
    |       +-> register in class-level state
    |       +-> event_sink.sandbox_created  (noop today)
    |       +-> _create_directory_structure / _install_dependencies / _verify_setup
    |
    +-> yield GenerationTurn per LLM call
    |       sandbox.commands.run(...) for tool calls
    |       resource_publisher.sync() on final outputs
    |
    +-> worker returns -> task COMPLETED event
            |
            v
        check_evaluators fans out criteria
            criteria reconnect via ManagerClass().get_sandbox(task_id)
                (works because singleton + shared class state;
                 cross-process criteria spawn a fresh sandbox instead)
            criteria read resources via direct run_resources DB read
            |
            v
        all criteria done -> BaseSandboxManager.terminate_by_sandbox_id(sandbox_id)
            (static, cross-process)
        -> finalize_success
```

Movement of data across this diagram:

- **Model id (string) flows down** into `resolve_model_target` and emerges as a `ResolvedModel`. No model object escapes back up — the worker owns it for its lifetime.
- **`sandbox_key` flows into `create`**; the returned E2B `sandbox_id` is persisted on the execution row. That id is the durable link criteria use — for in-process reconnect or cross-process teardown.
- **Sandbox bytes flow out** via the resource publisher, which writes once to the content-addressed blob store and records a `run_resources` row. The blob store is the single source of truth for cross-process data; the DB row is an index.
- **Events flow out** via `SandboxEventSink` — currently unwired on the live path (Section 2.4).

## 4. Invariants

1. **One entry point to LLM resolution.** Every model reference goes through `resolve_model_target`. Enforced by grep discipline and review; no runtime check.
2. **Backends register at import time.** `register_model_backend` must be called before any caller hits `resolve_model_target`. Enforced by the builtins pack running its registration loop at import, before any worker module imports.
3. **Singleton managers hold authoritative sandbox state.** A subclass's class-level state is the only source of truth for in-process reconnect. Enforced by `__new__` caching the instance and `get_sandbox` reading the class dict. Applies only within a single Python process; cross-process actors must use `terminate_by_sandbox_id` or provision their own sandbox.
4. **Sandbox lifecycle is per-task.** Enforced by `create` accepting `sandbox_key` and by the worker runtime persisting `sandbox_id` on the execution row.
5. **Sandbox lives across evaluator fan-out.** Teardown runs at the end of `check_evaluators`, not at worker completion, not in `finalize_success`. Enforced by the evaluator harness, not by the manager itself.
6. **Resource publication is content-addressed.** The publisher hashes before storing and is the single writer to `<ERGON_BLOB_ROOT>`. Repeated `sync()` calls against unchanged bytes are no-ops.

### 4.1 Known limits

- **Sandbox event sink unwired.** All construction sites omit `event_sink=`; the singleton holds the noop default, so sandbox lifecycle is not visible on the live dashboard path. Tracked in `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md`.
- **Constructor `event_sink` stomp.** Because subclasses are singletons and `__init__` conditionally overwrites the sink, any late re-construction with a non-None sink silently replaces the active sink on every in-flight task. Filed at `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md` (P3).
- **On-crash sandbox leak.** Sandbox cleanup is best-effort. If `check_evaluators` crashes before teardown, the remote E2B sandbox leaks until E2B's 30-minute idle timeout fires. Acceptable: the E2B timeout is the canonical safety net.
- **Class-dict unbounded growth.** Manager class-level state is cleared only inside `terminate()`. Any task that never reaches `terminate()` leaks its entries for the process lifetime. Acceptable for research workloads with bounded process lifetimes.
- **Blob store has no GC.** The publisher writes under the blob root and never deletes. Tracked as P4 in `docs/bugs/open/2026-04-18-blob-store-no-gc.md`.
- **Key-triplet debt.** `sandbox_key` / `task_id` / `display_task_id` collapse to one value in every production call site.
- **No `reconnect()` method.** Cross-process criteria must spawn their own sandbox (see `ergon_builtins/benchmarks/swebench_verified/criterion.py:66`).

## 5. Extension points

### 5.1 Add a new LLM backend

1. Write a resolver that maps `"myprefix:foo"` to a `pydantic_ai.models.Model` instance wrapped in `ResolvedModel`.
2. Register it in the builtins-pack registration loop so `register_model_backend` is called at import time.
3. Ensure the builtins pack is imported before any worker that references `myprefix:*` model ids.
4. Add an entry to `LLMProvider` and `PROVIDER_KEY_MAP` in `ergon_cli/onboarding/profile.py` so onboarding prompts for the key or server URL.

### 5.2 Add a new sandbox manager

1. Subclass `BaseSandboxManager`.
2. Set `template: ClassVar[str]` on the class, or override `__init__` to assign `self.template` from a pinned-id file if the template is rebuilt periodically (`SWEBenchSandboxManager` is the reference).
3. Implement `_install_dependencies` (required today; expected to become optional). Override `_verify_setup` if you need a smoke check. `_create_directory_structure` is concrete — override only if the default set is wrong.
4. Use the subclass at call sites as `ManagerClass().create(...)`. Treat the class as a singleton — re-instantiation is how callers acquire the cached instance.
5. Do NOT pass `event_sink=` at construction today; the stomp described in Section 2.2 makes that unsafe. The eventual path is a class-level setter called once at app init.
6. Register no registry entry — managers are discovered by the benchmarks that import them directly.

### 5.3 Add a new sandbox Docker template

1. Create the Dockerfile and inside-image setup script under `ergon_builtins/benchmarks/<slug>/sandbox/`.
2. Add a pinned-template-id file populated by the setup subcommand.
3. Add a CLI subcommand `ergon benchmark setup <slug>` that builds the template and writes the pin.
4. Use `ergon_builtins/benchmarks/swebench_verified/sandbox/` as the reference.

## 6. Anti-patterns

- **Importing an LLM SDK directly in a worker.** Bypasses backend registration, onboarding key flow, and future instrumentation. No current offenders — keep it that way.
- **Constructing an `AsyncSandbox` directly from worker or criterion code.** Go through a manager subclass; the manager owns template pinning, directory scaffolding, singleton state, event emission, and the teardown contract.
- **Passing `event_sink=` at manager construction.** The constructor stomps the sink on the shared singleton. Today: do nothing; leave the noop default. Eventual path: the class-level setter.
- **Reaching for `dashboard_emitter.sandbox_*()` as a workaround for the unwired sink.** Adding inline emitter calls trades one wiring bug for two.
- **Hardcoding a template string in a manager.** E2B templates are rebuilt when the Dockerfile changes; a literal id in code breaks on CI rebuild. Use a pin file, as `SWEBenchSandboxManager` does.
- **Reading `run_resources` rows directly from a criterion.** Works today but couples every criterion to the blob store schema. The unified entry point will be `CriterionRuntime.read_resource(name)`.
- **Calling instance `terminate(task_id)` from a cross-process actor.** The instance method relies on the singleton's class-level state, which is not shared across processes. Use the static `terminate_by_sandbox_id(sandbox_id)` for cross-process teardown.

## 7. Follow-ups

Active RFCs relevant to the providers layer:

- `docs/rfcs/active/2026-04-17-sandbox-event-sink-activation.md` — install the event sink via a class-level setter at app init.
- `docs/rfcs/active/2026-04-18-sandbox-manager-process-state.md` — reform class-level state so rollout paths stop depending on a single Python process; owns the class-dict growth limit, criterion reconnect, and the shared-state race.
- `docs/rfcs/active/2026-04-18-sandbox-manager-key-cleanup.md` — collapse the `sandbox_key` / `task_id` / `display_task_id` triplet.
- `docs/rfcs/active/2026-04-18-dashboard-event-wiring-enforcement.md` — wire the remaining `DashboardEmitter` methods or delete them, with a lint guard.
- `docs/rfcs/active/2026-04-17-criterion-runtime-di-container.md` — expose `get_sandbox()` and `read_resource(name)` through `CriterionRuntime`.
- `docs/rfcs/active/2026-04-17-sandbox-lifetime-covers-criteria.md` — formalize the sandbox-timeout invariant (sandbox timeout >= `task_timeout + max_criterion_timeout`).
- `docs/rfcs/active/2026-04-18-template-spec-public-api.md` — centralized `TEMPLATE_REGISTRY` with `TemplateSpec` entries.

Open bugs:

- `docs/bugs/open/2026-04-17-sandbox-event-sink-unactivated.md` — sink never fires on the live path.
- `docs/bugs/open/2026-04-18-sandbox-manager-shared-state-race.md` — P3.
- `docs/bugs/open/2026-04-18-blob-store-no-gc.md` — P4.
- `docs/bugs/open/2026-04-18-dashboard-emitter-methods-not-wired.md` — most emitter methods have no callers.

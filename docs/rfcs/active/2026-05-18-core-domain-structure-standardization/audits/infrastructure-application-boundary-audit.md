# Infrastructure/Application Boundary Audit

Date: 2026-05-18

Audited against PR 16 head in the main checkout.

## Boundary Rule

The target direction is port-and-adapter style:

```text
inbound adapters -> application use cases / views
application use cases -> application ports -> infrastructure implementations
```

Application owns business operations. Infrastructure adapts external systems
and frameworks. If infrastructure needs an operation that application already
knows how to perform, infrastructure must delegate to that application boundary
or implement a narrow application-declared port. It should not reimplement a
parallel copy locally.

Infrastructure should own framework and external-system adapters:

- Inngest function registration and transport concerns;
- dashboard event transport;
- E2B SDK calls and sandbox command/file proxies;
- tracing sinks and span export;
- process startup wiring.

Application should own use-case decisions:

- runtime lifecycle and propagation policy;
- run graph view assembly;
- resource persistence semantics;
- event payload contracts that are product/API contracts rather than transport
  implementation details;
- deprecated compatibility domains such as cohorts until they are removed.

The useful question during cleanup is therefore not only "which folder should
this live in?" It is:

> Does application already have a service, view, repository, or policy for
> this operation shape?

If yes, remove the duplicate infrastructure-side implementation and route
through that application operation. If no, extract the operation into
application first, then keep infrastructure as the adapter.

## Dashboard

The dashboard boundary is currently the largest infrastructure/application
mix. `infrastructure/dashboard/emitter.py` is partly a transport adapter: it
builds typed event contracts and sends them through the Inngest client. That
part belongs in infrastructure. But the module also owns application behavior:
`emit_cohort_updated_for_run()` reaches into the cohort read-model service,
recomputes cohort state, fetches a summary, and emits it. That is command/query
logic behind an infrastructure import path.

`infrastructure/dashboard/event_contracts.py` is not just infrastructure glue.
It defines generated frontend contracts and imports view DTOs such as
`RunTaskEvaluationDto`, communication DTOs, `CohortSummaryDto`, and
`GraphMutationRecordDto`. These models are product-facing event DTOs shared by
backend and dashboard generation. Keeping them under `infrastructure` makes the
contracts look like an implementation detail of the emitter, when they are
actually part of the dashboard/API contract surface.

The tree-building path is duplicated across application and infrastructure.
`application/jobs/start_workflow.py` imports dashboard contract types
(`TaskTreeNode`, `WorkerRef`) and contains `_build_task_tree_for_run()`, which
queries `RunGraphNode`, `RunGraphEdge`, and definition worker rows, then adapts
them to the dashboard tree. That is view assembly, not job orchestration.
It overlaps with the proposed `views` boundary and with the
existing run snapshot builders under `application/read_models`. PRD 06 deletes
`WorkerRef`, `TaskTreeNode`, and `_build_task_tree_for_run()` by changing
`workflow.started` to carry the existing `RunSnapshotDto` view.

Dashboard emission is also wired into application services directly. Task
execution, task management, worker execution, evaluation, communication, and
workflow completion all import `get_dashboard_emitter()` or the emitter type.
The calls are pragmatic today, but they mean command services know the concrete
dashboard transport. A cleaner target is an application-level event publisher
or listener interface, with the dashboard emitter registered as one
infrastructure subscriber.

This should not be implemented as a mechanical folder move. The dashboard event
path should reuse the run snapshot view rather than carrying its own
second graph-to-tree implementation. Likewise, cohort refresh should not remain
a dashboard helper with a new import path; it should become a deprecated
application cohort compatibility operation until the dashboard deletes cohorts.

Recommended target:

```text
views/dashboard_events/
  contracts.py          # generated dashboard event DTOs
  cohort_events.py      # temporary deprecated cohort refresh/summary emission helper
  graph_mutations.py    # RunGraphMutation -> GraphMutationRecordDto mapping

infrastructure/dashboard/
  emitter.py            # sends already-built event DTOs through Inngest
  provider.py           # process-level emitter wiring
```

This move should be paired with the view/cohort refactor. Cohort events
should remain clearly marked deprecated until the dashboard refactor removes
cohort concepts.

Directionality rule for dashboard:

- application may define dashboard event contracts or a `DashboardEventPublisher`
  port;
- infrastructure may implement that port by sending through Inngest;
- application services should not import the concrete `DashboardEmitter`;
- dashboard infrastructure should not import cohort services or view
  repositories directly.

## Sandbox

The sandbox code is closer to a real infrastructure adapter, but it still mixes
three responsibilities.

`infrastructure/sandbox/manager.py` owns E2B lifecycle for the manager-style
sandbox path: create/connect/kill, directory bootstrap, dependency install
hooks, input upload/download helpers, in-process registries, and event sink
emission. Those E2B SDK interactions belong in infrastructure. The risk is that
the v2 public `Sandbox.provision()` path now also provisions sandboxes directly,
so the codebase has two sandbox ownership paths: object-bound public sandbox
instances and `BaseSandboxManager`. The application jobs call the public
sandbox path in `sandbox_setup.py`, while cleanup still terminates through
`terminate_external_sandbox()` -> `BaseSandboxManager.terminate_by_sandbox_id()`.
That bridge is useful during the current transition, but the final owner should
be explicit: application lifecycle decides when to terminate; infrastructure
performs termination by sandbox id.

`infrastructure/sandbox/event_sink.py` is a mostly healthy adapter boundary.
It defines a `SandboxEventSink` protocol plus no-op, dashboard, Postgres, and
compound sinks. The duplication risk is not the protocol. The risk is that the
Postgres sink writes telemetry rows directly while other telemetry writes are
owned by application repositories/services. If sandbox telemetry is intended to
be append-only infrastructure observability, this is acceptable. If those rows
feed dashboard/read-model product state, the write should move behind an
application telemetry/resource service.

`infrastructure/sandbox/instrumentation.py` is also a reasonable adapter. It
wraps E2B command/file/run-code calls and emits command events. It should stay
infra as long as it does not decide task status, run state, or resource
semantics.

`infrastructure/sandbox/resource_publisher.py` is the real duplication hotspot.
It scans sandbox directories, reads files through the sandbox adapter, hashes
content, writes a content-addressed blob, deduplicates rows, guesses MIME type,
and appends `RunResource` rows through `RunResourceRepository`. The external
filesystem reads and blob writes are infrastructure concerns, but the append
policy, dedup semantics, resource kind mapping, and DTO creation are
application/resource concerns. `application/jobs/persist_outputs.py` already
states that `SandboxResourcePublisher` is the single authoritative path from
sandbox to resources, but that authority currently lives under
`infrastructure`.

This should be fixed by splitting operation shape from adapter shape. The
application operation is "publish these sandbox outputs as run resources with
canonical dedup, kind, MIME, metadata, and append-only row semantics." The
infrastructure operations are "list/read files in a sandbox" and "write bytes
to a blob store." If resource logic already exists in
`application/resources/repository.py` or read-model resource helpers, reuse or
extend it there. Do not leave a second resource append policy inside sandbox
infrastructure under a tidier name.

Recommended target:

```text
application/resources/
  service.py            # publish sandbox outputs; owns dedup/resource semantics
  repository.py         # append/list/get RunResource rows
  models.py             # RunResourceView and command/result DTOs

infrastructure/sandbox/
  files.py              # E2B file listing/reading adapter
  blob_store.py         # content-addressed local blob store
  instrumentation.py    # command/file proxy event emission
  lifecycle.py          # terminate external sandbox by id
  manager.py            # E2B manager compatibility path, if still needed
```

The next implementation should not stuff this into the runtime-domain merge.
It is a separate resource boundary cleanup with tests around dedup, MIME
selection, blob path stability, and `persist_outputs` behavior.

Directionality rule for sandbox:

- application owns when to provision, publish, and terminate;
- application may depend on `SandboxFileReader`, `BlobStore`, and
  `SandboxTerminator` ports;
- infrastructure implements those ports with E2B and local filesystem code;
- infrastructure sandbox modules should not append `RunResource` rows directly
  once the application resource service exists.

## Inngest

The Inngest boundary is mostly clean after PR 16. Handler modules under
`infrastructure/inngest/handlers` primarily parse `ctx.event.data`, configure
function metadata, and delegate to `application/jobs/*`. That is the right
shape for infrastructure.

There are two cleanup notes. First, `infrastructure/inngest/contracts.py` is a
re-export layer for application job models. That is not harmful, but it is
more indirection than ownership. Job payload/result schemas already live in
`application/jobs/models.py`; handlers can import them directly unless the team
wants a deliberate transport contract facade.

Second, `cancel_orphan_subtasks.py` still carries a TODO asking whether each
handler should become a module that owns its own logic and contracts. The audit
answer is no for infrastructure handlers: they should stay adapters. If logic
needs a clearer home, it should move from `application/jobs` into the runtime
application domain, not into Inngest handler modules.

This is a good example of the intended directionality. Inngest handlers are
inbound adapters. They may know about Inngest triggers, retries, cancellation
configuration, output types, and `ctx.event.data`. They should not become owners
of task lifecycle, propagation, cleanup, or event fanout policy. If a handler
needs reusable behavior, that behavior belongs in application runtime/jobs and
the handler calls it.

Recommended target:

```text
infrastructure/inngest/
  client.py
  registry.py
  handlers/

application/jobs/
  models.py             # keep job payload/result contracts here while jobs exist

application/runtime/
  ...                   # eventual owner of reusable runtime lifecycle policy
```

## Tracing

Tracing is mostly healthy infrastructure. `infrastructure/tracing` owns
deterministic trace/span id generation, context factories, attribute
normalization, no-op and OpenTelemetry sinks, and exported facade functions.
Application jobs emit `CompletedSpan` records at use-case boundaries, which is
acceptable observability code rather than duplicated domain behavior.

The one boundary smell is that `contexts.py` encodes the runtime span
hierarchy: workflow root, task execute, sandbox setup, worker execute, persist
outputs, propagation, workflow completion/failure, evaluation task, and
criterion spans. That mirrors runtime lifecycle concepts. This is acceptable as
long as tracing context factories remain pure naming/id helpers and do not make
lifecycle decisions. If the runtime domain merge lands, the tracing hierarchy
should be reviewed against the new runtime module names, but it does not need
to move into application.

Recommended target: keep tracing under infrastructure. Add a short ownership
comment to `contexts.py` if this RFC becomes an implementation plan:

> Trace context factories may mirror runtime concepts, but must stay pure:
> deterministic ids, parent/child links, and relational ids only. They must not
> inspect persistence, start jobs, emit dashboard events, or choose lifecycle
> transitions.

Directionality rule for tracing:

- application use cases may emit span facts through a tracing port;
- infrastructure owns id generation, normalization, and sink implementation;
- tracing modules may mirror lifecycle names for observability, but must not
  become an alternate lifecycle model.

## REST App Startup

`rest_api/app.py` initializes infrastructure adapters during FastAPI lifespan:
database setup, rollout service, dashboard emitter provider, sandbox event
sink composition, and Inngest serving. This is appropriate startup wiring.

The only caveat is that it currently wires the sandbox event sink only onto
`DefaultSandboxManager`. If concrete sandbox manager subclasses remain after
the public object-bound sandbox path settles, startup should install the sink
for every live manager class or delete the manager-class registry entirely.
This is not application duplication, but it is a lifecycle wiring risk.

## Cross-Cutting Duplications To Resolve

1. Dashboard event DTOs are generated product contracts but live under
   infrastructure. Move or rename them into a view/contract boundary.

2. Dashboard workflow tree assembly lives inside `application/jobs/start_workflow.py`
   and imports dashboard DTOs directly. Before moving it, compare it with
   existing run snapshot/read-model view logic and extract any shared
   graph traversal or task summary behavior once.

3. Cohort recompute-and-emit logic lives under `infrastructure/dashboard`.
   Move it to a deprecated cohort/view compatibility operation until the
   dashboard removes cohorts. Do not let the dashboard emitter own recompute
   policy.

4. Application services import the concrete dashboard emitter. Introduce a
   small application event/listener interface if this keeps spreading.

5. Sandbox resource publication owns application resource semantics under an
   infrastructure path. Split sandbox file/blob adapters from the application
   resource service policy, and reuse existing `application/resources` logic
   rather than creating a second append/dedup implementation.

6. Sandbox lifecycle still bridges object-bound public sandboxes through
   manager termination. Keep the application decision point in cleanup jobs,
   but make the infrastructure termination path explicitly id-based and
   manager-compatibility-only.

7. Inngest handler TODOs should resolve toward thinner handlers and stronger
   application runtime services, not toward handler-owned domain modules.

## Suggested PR Slices

### PR A: Dashboard View Boundary

Move dashboard event contracts and workflow tree assembly into an application
view/contract package. Leave `DashboardEmitter` as infrastructure
transport. Characterize `workflow.started`, graph mutation, task status,
evaluation update, context event, and communication event payloads before
moving imports. As part of the characterization, identify whether existing
run snapshot/read-model code already implements graph traversal, task summary,
or resource summary logic that the dashboard tree can reuse.

### PR B: Deprecated Cohort Boundary

Move cohort event refresh logic out of infrastructure and into an explicitly
deprecated cohort compatibility module. Add the file-level TODO already agreed
for the dashboard refactor: cohorts are confirmed deprecated in v2 and should
be removed from the UI/backend compatibility layer later.

### PR C: Sandbox Resource Service Split

Create an application resource publication service that owns dedup, resource
kind, MIME, metadata, and row append semantics. Keep E2B file reads and blob
filesystem writes in infrastructure. Update `persist_outputs` and toolkit
publish paths to call the application service. The service should reuse
`RunResourceRepository` and existing resource DTOs rather than reimplementing
row append/dedup policy inside sandbox infrastructure.

### PR D: Inngest Cleanup And Boundary Tests

Delete the handler TODO, keep `infrastructure/inngest/contracts.py` only for
transport/framework contracts, and add architecture tests for:

- `infrastructure/inngest/handlers` may import `application/jobs`, but not the
  other way around;
- infrastructure dashboard transport may not import cohort services;
- infrastructure sandbox resource adapters may not append `RunResource` rows
  directly after PR C.
- application services may not import concrete dashboard/Inngest/E2B/tracing
  implementations except in composition roots or explicitly approved bootstrap
  modules.

### PR E: Tracing Ownership Comments

Add lightweight docstrings/comments and tests, if useful, that tracing context
factories are pure observability helpers. This can be folded into whichever PR
touches runtime module names.

# MA-Gym native Ergon implementation plan

## Code file change map

The annotated tree lists the actual implementation files against the inspected
Ergon base. No production files are removed. Scenario definitions are adapted
from the pinned source; evidence inventories are linked below the code map.

```text
ergon/
  .dockerignore # add: exclude credentials, local dependencies and run data from image builds
  Dockerfile # edit: install the API/CLI from the workspace lock on Linux
  docker-compose.yml # edit: allow an explicit image tag while retaining the normal stack
  docs/
    architecture/
      01_public_api.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      02_runtime_lifecycle.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      03_providers.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      04_persistence.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      05_dashboard.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      06_builtins.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      09_manager_gym.md # add: record implemented contracts, fidelity decisions and acceptance evidence
      README.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
      cross_cutting/
        artifacts.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
        error_propagation.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
        sandbox_lifecycle.md # edit: record implemented contracts, fidelity decisions and acceptance evidence
    rfcs/
      active/
        2026-09-07-manager-gym-port/
          README.md # add: record implemented contracts, fidelity decisions and acceptance evidence
          capability-mapping.md # add: record implemented contracts, fidelity decisions and acceptance evidence
          ergon-way-audit.md # add: record implemented contracts, fidelity decisions and acceptance evidence
          prd.md # add: record implemented contracts, fidelity decisions and acceptance evidence
    superpowers/
      plans/
        2026-09-07-manager-gym-native-port.md # add: record implemented contracts, fidelity decisions and acceptance evidence
  ergon-dashboard/
    src/
      features/
        evaluation/
          contracts.ts # edit: retain nullable evaluation score contracts
          selectors.test.ts # edit: verify incomplete evaluation rendering and contract compatibility
          selectors.ts # edit: show incomplete evaluation and preserve null in parent rollups
      generated/
        events/
          schemas/
            DashboardTaskEvaluationUpdatedEvent.schema.json # edit: regenerate nullable evaluation REST/event contracts
            DashboardWorkflowStartedEvent.schema.json # edit: regenerate nullable evaluation REST/event contracts
        rest/
          contracts.ts # edit: regenerate nullable evaluation REST/event contracts
          openapi.json # edit: regenerate nullable evaluation REST/event contracts
  ergon_builtins/
    AGENTS.md # edit: document the native MAG entrypoints and existing composition owners
    ergon_builtins/
      benchmarks/
        manager_gym/
          NOTICE # add: retain the pinned source revision and MIT attribution
          __init__.py # add: define the native MAG package
          actions.py # add: preserve the 13 typed source actions
          baselines.py # add: implement RandomV2 and one-shot bulk policies with source fallback
          communication.py # add: scope the six model tools over native communication
          definitions/
            __init__.py # add: retain executable pinned callable and rubric definitions
            common_evaluators.py # add: retain executable pinned callable and rubric definitions
            constraint_evaluator.py # add: retain executable pinned callable and rubric definitions
            operational_efficiency_evaluator.py # add: retain executable pinned callable and rubric definitions
            scenario_constraints.py # add: retain executable pinned callable and rubric definitions
            stakeholder_evaluator.py # add: retain executable pinned callable and rubric definitions
          inference.py # add: bind all roles to internal Qwen and record bounded inference settings
          manager.py # add: checkpoint one manager Worker and apply actions through existing native APIs
          outputs.py # add: retain typed role outputs and decode nested JSON transport
          prompts/
            __init__.py # add: retain the pinned role/manager/judge prompt
            ai_agent_prompts.py # add: retain the pinned role/manager/judge prompt
            decomposition.py # add: retain the pinned role/manager/judge prompt
            human_agent_prompts.py # add: retain the pinned role/manager/judge prompt
            judge.py # add: retain the pinned role/manager/judge prompt
            manager.py # add: retain the pinned role/manager/judge prompt
            stakeholder_prompts.py # add: retain the pinned role/manager/judge prompt
            worker.py # add: retain the pinned role/manager/judge prompt
          rubric.py # add: execute pinned criteria and aggregate frozen-snapshot stakeholder utility
          sample.py # add: build normal episode and frozen re-evaluation samples
          scenario_catalog.py # add: register the 20 pinned scenario factories explicitly
          scenarios/
            __init__.py # add: port pinned scenario factory, team, preferences or resources
            airline_launch_program/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            banking_license_application/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            brand_crisis_management/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            data_science_analytics/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            enterprise_saas_negotiation_pipeline/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            genai_feature_launch/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            global_product_recall/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            icap/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            ipo_readiness_program/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            legal_contract_negotiation/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            legal_global_data_breach/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            legal_litigation_ediscovery/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            legal_m_and_a/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            marketing_campaign/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            mnc_workforce_restructuring/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            orsa/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            pharmaceutical_product_launch/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            stakeholders.py # add: port pinned scenario factory, team, preferences or resources
            standard_rules.py # add: port pinned scenario factory, team, preferences or resources
            supply_chain_planning/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            tech_company_acquisition/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preference.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
            uk_university_accreditation/
              __init__.py # add: port pinned scenario factory, team, preferences or resources
              preferences.py # add: port pinned scenario factory, team, preferences or resources
              team.py # add: port pinned scenario factory, team, preferences or resources
              workflow.py # add: port pinned scenario factory, team, preferences or resources
          source-manifest.json # add: record original source-file hashes
          source_types.py # add: adapt source authoring/projection schemas without importing its scheduler
          state.py # add: project native results, timelines, public observations and snapshot hashes
          workers.py # add: execute AI/human/stakeholder roles with PostgreSQL workload inputs and E2B outputs
      llm/
        providers/
          openai_compatible.py # edit: preserve gateway paths and use configured secret binding
      sandbox/
        e2b_runtime.py # edit: read bytes and detach without calling a nonexistent SDK close method
    tests/
      unit/
        builtins/
          benchmarks/
            manager_gym/
              test_actions.py # add: verify native MAG contracts, compatibility and failure behavior
              test_catalog.py # add: verify native MAG contracts, compatibility and failure behavior
          common/
            test_e2b_runtime.py # add: verify native MAG contracts, compatibility and failure behavior
            test_openai_compatible_models.py # edit: verify native MAG contracts, compatibility and failure behavior
  ergon_core/
    ergon_core/
      api/
        rubric/
          evaluator.py # edit: add opt-in incomplete failure policy with compatible zero default
        worker/
          context.py # edit: expose native checkpointed waits and pending Task replacement through WorkerContext
          results.py # edit: return full persisted completion, attempt identity and timeout information
          worker.py # edit: separate configured actor binding from executable Worker type
      core/
        application/
          communication/
            models.py # edit: add idempotency key and message metadata contracts
            service.py # edit: lock message sequencing and deduplicate keyed sends atomically
          context/
            service.py # edit: reuse identical persisted context chunks on replay; reject mismatches
          evaluation/
            mappers.py # edit: preserve criterion provenance and normalized aggregate scale
            service.py # edit: persist opted-in failed evaluations as incomplete/null
            summary.py # edit: retain criterion metadata and nullable normalized score
          resources/
            publishing.py # edit: retain typed checkpoint results through existing resource rows and blob storage
          runtime/
            graph_repository.py # edit: share a nonblocking sample lock, validate pending edges and inspect cancellation cause
            lifecycle.py # edit: release late dependents and keep explicit cancellations cancelled
            orchestration.py # edit: represent skipped stale/duplicate task-ready events without an attempt
            task_execution.py # edit: check state/prerequisites atomically before claim; preserve concrete Worker type
            task_inspection.py # edit: read latest native attempt and full WorkerOutput
            task_management.py # edit: make existing spawn/refine/cancel/restart paths atomic and replay-compatible
            task_models.py # edit: carry optional Task/dependency replacement through existing commands
          samples/
            materialization.py # edit: persist configured actor binding separately from code type
        infrastructure/
          sandbox/
            resource_publisher.py # edit: use distinct temporary files for concurrent atomic blob publication
        jobs/
          sample/
            cleanup/
              contract.py # edit: report the complete owned sandbox set while retaining the legacy field
              job.py # edit: cancel remaining native task attempts and close all owned sample sandboxes
          task/
            evaluate/
              job.py # edit: propagate evaluator failure policy through the normal job
            execute/
              contract.py # edit: allow skipped dispatch results to have no attempt ID
              job.py # edit: skip stale ready events without emitting fabricated execution/terminal results
            worker_execute/
              composition.py # add: inject native artifact retention into worker checkpoint execution
              inngest.py # edit: stop invoked workers on native sample and task cancellation
              job.py # edit: bind native continuation and memoize existing task mutations/rejections
        persistence/
          telemetry/
            models.py # edit: add native message constraints/metadata
        views/
          rl/
            actor_state.py # edit: reconstruct actor identity without confusing it with Worker class
          samples/
            evaluation_mapping.py # edit: retain null incomplete totals in native read models
            models.py # edit: make incomplete evaluation DTO scores nullable
    migrations/
      versions/
        00000004_message_idempotency.py # add: repair historical sequences and add native message uniqueness
        00000005_message_metadata.py # add: persist non-null native message metadata on fresh and existing databases
    tests/
      unit/
        api/
          worker/
            test_smoke_worker_serialization.py # add: verify native MAG contracts, compatibility and failure behavior
            test_worker_context_facade.py # edit: verify native MAG contracts, compatibility and failure behavior
        architecture/
          test_single_alembic_head.py # edit: verify native MAG contracts, compatibility and failure behavior
        core/
          application/
            jobs/
              test_worker_execute_live_sandbox_attach.py # edit: verify native MAG contracts, compatibility and failure behavior
            tasks/
              test_spawn_dynamic_task_dispatch.py # edit: verify native MAG contracts, compatibility and failure behavior
        registry/
          test_inngest_job_registry.py # edit: verify native MAG contracts, compatibility and failure behavior
        runtime/
          test_failure_error_json.py # edit: verify native MAG contracts, compatibility and failure behavior
          test_graph_worker_identity.py # edit: verify native MAG contracts, compatibility and failure behavior
          test_manager_gym_preport_proof.py # add: verify native MAG contracts, compatibility and failure behavior
          test_native_manager_contracts.py # add: verify native MAG contracts, compatibility and failure behavior
          test_spawned_task_handle.py # edit: verify native MAG contracts, compatibility and failure behavior
          test_worker_checkpoint_artifacts.py # add: verify native MAG contracts, compatibility and failure behavior
          test_worker_context_containment.py # edit: verify native MAG contracts, compatibility and failure behavior
  examples/
    manager_gym/
      README.md # add: document deployment, operation and verification
      acceptance.py # add: run/resume contract, pilots and catalog; verify/export native evidence
      cancellation.py # add: prove cancellation prevents delayed spawning and closes both running E2B tasks
      compose.acceptance.yml # add: disable API hot reload during durable native execution
      preflight.py # add: check model schemas, catalog and nonsecret resolved profile
      reevaluate.py # add: submit a linked native evaluation of an unchanged frozen snapshot
      submit.py # add: submit explicit scenario records through Environment and Experiment
  pyproject.toml # edit: scope lint exceptions to pinned source fallback behavior and MAG entrypoints
  tests/
    fixtures/
      mag_contract.py # add: verify native MAG contracts, compatibility and failure behavior
      mag_preport.py # add: verify native MAG contracts, compatibility and failure behavior
      smoke_components/
        smoke_base/
          leaf_base.py # edit: verify native MAG contracts, compatibility and failure behavior
    integration/
      restart/
        test_reactivation.py # edit: verify native MAG contracts, compatibility and failure behavior
      test_mag_runtime_concurrency.py # add: verify native MAG contracts, compatibility and failure behavior
```

## Scope and settled decisions

Charlie authorized full implementation on September 13, following the bounded
proofs. This document replaces the earlier PRD/RFC/roadmap as the single scope
and implementation record. The source inventories and failed proof receipts
remain evidence; their old implementation proposals do not override this file.

The acceptance outcome is to run all 20 registered MA-Gym scenarios through
native Ergon on a small training-account Linux VM, using standing internal
Qwen and E2B task sandboxes. Evaluation comes first; RL integration is later.
Native agents, task assignment, messaging, rubrics and ordinary sample records
are required. Ergon owns scheduling, dependency release and result visibility.
No source collection barrier or parallel task runtime is implemented.

Source: `3f7a5d4af1d31abaedbedd525a0090452926fef4`; Ergon base:
`6910ecfc74807209b86db5c6f063ac9932b462a0`; native version: `mag-native-v1`.
The catalog contains 694 authored nodes, 541 leaves, 1,281 composed rubric
definitions and 1,230 selected terminal criteria (876 LLM / 354 callable).

## Implemented composition

`EpisodeConfig` records enter `Environment.from_records` and `Experiment.submit`.
One root `EpisodeTask` binds the real manager Worker, existing E2BSandbox and
native MAGRubric. The manager checkpoints each observation and model decision
inside its existing Worker invocation. It calls the existing spawn/refine/cancel
facade; actual team work becomes direct native children. There is no Task per
decision, clock Worker, runtime registry, custom Environment subclass or new
sandbox backend.

Unassigned leaves and composites remain authored input. On assignment their
logical IDs bind to fully configured native Tasks, with inherited/composite
prerequisites expanded to leaf IDs. Prerequisites must be bound first.
Unclaimed Task payloads, assigned Workers and dependencies can be replaced
atomically through native refinement. Running/terminal replacement is rejected.
Cancellation uses the normal native cascade. Capacity stays informational:
there are no actor queues or implicit same-actor ordering edges.

AI, human and stakeholder work use native Workers with distinct configured
actor keys. Human input captures completed PostgreSQL attempts, exact attempt
IDs, accounted hours, messages and predecessor resources once at invocation
start. Declared initial inputs and completed prerequisite outputs define the resource scope. Concurrent starts may observe the same history. The source fatigue,
quality, speed, wage and misunderstanding formulas remain; the misunderstanding
branch's omission from fatigue-hours/count is retained. Real task dependencies
provide ordering where the manager authors it. The LLM receives typed inputs,
not a SQL tool. Scripted stakeholder tick behavior is a benchmark function
whose messages use the native stakeholder identity; assigned stakeholder work
is a real LLM Worker.

Decision indices drive team/preference events and the delayed stakeholder
outbox. They never gate result visibility. Simulated labor, decision count and
wall time are separate. Stop decisions at the horizon/end request/completion,
drain admitted native work, cancel leftovers at the shared drain deadline,
then freeze the root output and evaluate it through ordinary evaluator jobs.

All six reachable source communication tools use the existing native message
store. Sends have deterministic idempotency keys and native actor identity;
reads are participant-scoped and messages are visible while work is running.
The pinned runner bypasses ToolFactory defaults when these tools are present,
so unused placeholder search/code/break tools are not falsely advertised.

The manager and judge retain the pinned source's 300-character resource previews;
AI/human task prompts use 200 characters per input resource. Manager observations
show the latest ten messages with 140-character content previews and ten action
briefs. Full artifacts, messages and typed prerequisite results remain in native
storage and the frozen snapshot. Callable rubrics use the complete requested
context. The pinned LLM rubric path has no explicit scope and renders the source
workflow summary; it does not serialize the entire ValidationContext to the model.
An exploratory build passed full documents instead, exceeded Qwen's input window,
and was corrected before final acceptance.

## Every core change and why it is required

| Existing owner | Change and demonstrated need | Compatibility boundary |
|---|---|---|
| Worker and materialization; task preparation; actor RL view | Separate optional actor_key/binding_key from concrete Worker type so two humans of the same class remain different actors and execute the correct code. | Existing workers default to type_slug. No new actor table. |
| WorkerContext and SpawnedTaskHandle | Expose BaseModel-valued native checkpoints and bounded descendant waits returning full output, status, attempt, error and timestamps. Native continuation proof demonstrated the need. | Unbound wait still raises; timeout does not cancel; containment/self-wait checks remain. No source timing emulation. |
| Worker invocation and existing sample cleanup job | Stamp the sandbox on its attempt before worker execution, including error/wait paths. Apply native sample/task cancellation to invoked workers; reject spawning under terminal parents/samples and late claims; preserve cancelled attempts against late finalizers. Sample cancellation closes all attempt and lifecycle-recorded sandbox IDs through existing cleanup owners. | A live exploratory manager spawned after cancellation and reopened sandboxes. A delayed-spawn E2B probe now tests the complete cancellation path. Successful parent completion still allows already-admitted children to finish. |
| Existing step-aware worker job | Memoize refine/cancel/restart as already done for spawn; checkpoint expected mutation rejections and rethrow outside the step boundary. | One runtime and existing APIs; no benchmark deduplication service. |
| Worker checkpoint artifacts | Keep large typed step results in the existing SampleResourcePublishService/blob store; Inngest stores verified hash/size references. An autonomous ICAAP pilot hit the engine's 32 MB aggregate state limit. | No benchmark storage backend or scheduler. Native resource rows/exports retain all checkpoint bytes; missing/corrupt blobs fail replay without a new model call. |
| ContextEventService | Reuse matching persisted attempt chunks during replay and fail on a mismatch. | Existing context storage/uniqueness is unchanged. Provider response-before-checkpoint loss is not solved. |
| RuntimeGraphRepository | Share a sample lock across mutation/claim; use PostgreSQL FOR NO KEY UPDATE and acquire it off the event loop. Validate dependency references/cycles before replacement and read fresh locked rows. | SQLite remains supported. Existing graph/WAL is authoritative. Fixes a real PostgreSQL continuation deadlock. |
| TaskManagementService and command models | Atomic pending Task/dependency replacement; late-dependent readiness dispatch; sample-locked spawn/cancel/refine/restart. | Preserve Task identity and description-only callers; no running executable mutation or new scheduling API. |
| TaskExecutionService, preparation/result DTOs and execute job | Recheck status/dependencies at claim; skip stale/duplicate ready events without another attempt or fabricated terminal event. | Ordinary valid dispatch is unchanged. |
| Native lifecycle | Only cancellations caused by downstream invalidation may reactivate when dependencies resatisfy. | An explicit manager cancellation stays cancelled; explicit restart remains available. |
| TaskInspectionService | Read the latest native attempt's full persisted WorkerOutput and timestamps for bound waits. | Reuses existing output/attempt rows, no result inbox. |
| CommunicationService/models and telemetry schema | Thread lock before sequencing/key lookup; unique thread+sequence and thread+key; persist message metadata; reject conflicting key reuse. | Unkeyed callers still work. Real PostgreSQL concurrent send and historical migration tests pass. |
| Migrations 00000004/00000005 | Repair old duplicate message sequences deterministically, add constraints/idempotency/metadata, tolerate fresh metadata-created databases. | Retains all old messages; reapplying migration logic is tested. |
| Evaluator, EvaluationService, summary/mappers and evaluate job | Opt-in incomplete/null failure persistence; retain criterion metadata; mark MAG's aggregate scale as normalized 0–1. | Default failure_policy remains zero for existing evaluators. All source criteria must be present for a numeric MAG utility. |
| Sample evaluation DTOs and generated REST/event readers | Preserve null incomplete totals through native inspection and dashboard. | Existing numeric evaluations remain numeric. |

Adjacent fixes remain in their existing owners: the E2B adapter now returns
bytes and detaches without calling a nonexistent SDK close method; the existing
OpenAI-compatible resolver preserves the gateway path and uses configured
credentials; the Dockerfile installs the locked workspace. No core change
implements MAG clocks, fatigue, grading formulas or a benchmark scheduler.

## Scoring, replay and evidence

Source callable factories and prompt definitions remain executable code; JSON
records contain typed data, not serialized closures. Each terminal definition
becomes a normal native Criterion over one frozen snapshot. Preference groups
use sum(raw)/sum(max), then final preference weights determine utility.
Diagnostics remain saved and excluded from the headline score. Source cadence
quirks are retained; optional tick grading is deferred.

Expected policy mistakes and misunderstanding can score poorly. Infrastructure
failure, a missing criterion, snapshot mismatch or exhausted judge errors make
the evaluation incomplete/null. The normal dashboard labels it Incomplete and
does not silently average away invalid children. The acceptance runner checks
criterion identity/count, snapshot hash and utility independently from saved
rows, and checks E2B absence after native terminal cleanup.

Native workflow checkpoints preserve captured observations, decisions, draws
and task-tool call order. Successful model transcripts/usage remain native
context records. A crash/provider exception before a response is checkpointed
can lose that call's transcript/usage; no exactly-once provider guarantee is
made. Source RandomV2 and assign-all fallback behavior is recorded explicitly.
Frozen re-evaluation creates a separate sample linked to the original ID/hash;
the CLI rejects schema changes that would rewrite the stored snapshot.

## Runtime profile and operating procedure

Use [the executable runbook](../../../examples/manager_gym/README.md). The
temporary acceptance machine uses Ubuntu 24.04, 4 vCPU / 16 GiB, encrypted
100 GiB storage, and the standard four-service Ergon Compose stack in the
training account. Each executable Task uses E2B. The VM filesystem retains
native database/artifact data; it is not the task runtime.

All roles route through the standing `qwen3-8-27b-28` training gateway using
configured secret storage. No standing GPU replicas are modified. The observed
deployment has five ready replicas on vLLM 0.28.0. Record its image digest and
weight location; an endpoint name is not an immutable checkpoint identifier.
No external-model or search fallback is configured.

The integration profile records 32,768 output tokens, a 2,048-token per-request
thinking budget, 300-second request timeout, 600-second operation timeout,
12-request limit and two validation retries. The thinking cap addresses an
observed full-worker 32,768-token exhaustion and was verified against the
standing endpoint before use. Temperatures: manager/AI/stakeholder/estimator/
judge 0, human 0.7, decomposition 1. These are comparison conditions, not a claim
that Qwen reproduces the upstream o3 policy distribution.

Default horizon is 50 decisions, indices 0–49. Seven scenarios have later
events; this is an integration profile, not a complete-timeline study. The
observed E2B account permits at most one hour. Manager wall budget is 2,400
seconds, terminal drain 600 seconds; grading also needs time before expiry.
Do not reduce rubric coverage to meet the deadline. Serial grading remains the
native execution model until measured evidence justifies changing that owner.

“For free” means reuse standing internal model capacity. CPU, disk and E2B still
consume resources; billing is unknown unless separately verified. Simulated
wages/token prices are not infrastructure billing.

## Implementation and acceptance sequence

| Stage | Implementation / acceptance artifact | Status |
|---|---|---|
| 1. Characterize | Pinned source, 20 scenarios, 85 feature dispositions, exact 1,281-definition manifest and 1,230 terminal selection | Implemented; source inventory and offline callable checks pass |
| 2. Repair native contracts | Existing E2B/provider/runtime/message/evaluation owners; no second scheduler | Implemented; unit, real PostgreSQL concurrency/migration and continuation proofs pass |
| 3. Native benchmark | All actions, three manager modes, AI/human/stakeholder roles, messaging/timelines, native criteria and frozen re-evaluation | Implemented; full unit validation tracked in acceptance evidence |
| 4. Linux/E2B contract | Locked Linux deployment, doctor, real role schemas, dependency/human/edit/cancel/message/decomposition/artifact/grading/cleanup contract | Build-v5 role preflight, delayed cancellation and native composition contract pass |
| 5. Autonomous pilots | Legal e-discovery, ICAAP, marketing, banking license; seed 0, normal native work and every terminal criterion | Build-v5 legal and ICAAP running; four pilots must pass before catalog expansion |
| 6. Full catalog | All 20 seed-0 scenarios, reusing pilots only under identical code/model/config | Required; per-sample ledger is the authority, not this checklist |
| 7. Review/export/cleanup | Curated receipt, raw native records/context/blobs, database backup, dashboard screenshot, owned resource closure, PR review | Required before completion |

The final acceptance report must retain every attempted sample ID and failed
build/configuration, native task/actor/model records, messages/resources,
criterion counts and recomputed utility, usage/attempt counts, observed
deployment settings, wall time and sandbox closure. Private raw traces stay in
run evidence; curated aggregates/provenance belong in the PR. Export the
database and blob store before deleting the dedicated VM/SG/key. Leave standing
GPU capacity untouched. No healthy endpoint, submitted wrapper or aggregate
score substitutes for these gates.

## Full feature disposition manifest

These 85 stable identifiers preserve the original inventory. “Retained” means
definitions/formulas under recorded inputs, not identical source scheduling or
statistical score parity. The dispositions below describe implemented behavior
or an explicit deferred profile; the acceptance ledger establishes live proof.

| ID | Source feature | Implementation disposition |
|---|---|---|
| F01 | 20 registered Python scenario factories and their initial resources | Retained: all 20 pinned Python factories, initial resources and source/license hashes are packaged. |
| F02 | Scenario × seed × persona × horizon × model configuration | EpisodeConfig records compose through Environment.from_records; one root EpisodeTask per Sample. Source metadata records the inference profile. |
| F03 | Unassigned, assigned, atomic and composite logical tasks | Source Task descriptions remain authored input until assignment; bindings link logical IDs to authoritative native Tasks. No second execution graph. |
| F04 | Dependencies, parent-to-leaf propagation and composite readiness | Inherited/composite prerequisites expand to native leaf dependencies. The existing scheduler alone releases work. |
| F05 | Observation construction registers leaves and updates readiness | Observation is read-only; prepare the complete logical inventory without invoking source readiness mutations. |
| F06 | Logical task mutations during an episode | Unbound plan edits and atomic native pre-claim replacement are implemented; reject running/terminal executable changes. |
| F07 | UUID resources, dependency inputs and generated outputs | Existing resource rows/blobs with producer/logical ID linkage. A worker receives only declared initial inputs plus completed native prerequisite outputs, never all unrelated workflow resources. |
| F08 | Scheduled joins and removals with public team descriptions | Team timelines run at manager decision indices. Removal restricts new assignments; admitted native work follows its existing lifecycle. |
| F09 | Capacity metadata is not enforced by source dispatch | Source capacity is informational. No actor queue or implicit serialization. An early implementation added actor-order edges; these were removed before final acceptance. |
| F10 | Numeric initial preferences are present in stakeholder public profile | Retain the initial public stakeholder profile, including its numeric preference summary. Future schedules/current private changes and rubric definitions stay private. |
| F11 | Scenario creation has random identifiers and Python callables | Retain callable factories as code and typed projection data; deterministic logical IDs derive from version/scenario/seed/source paths. |
| F12 | Upstream server, streaming demo, file log layout and snapshot restoration | Ergon lifecycle/inspection replaces source server/log layout; upstream engine remains development-only. |
| A01 | `assign_task` | Implemented: plan assignment, native compilation and unclaimed-task rebinding; reject running reassignment. |
| A02 | `create_task` | Implemented: typed plan creation and existing spawn path once bindings exist. |
| A03 | `remove_task` | Implemented: remove unbound input or native cancel; retain history and successor consequences. |
| A04 | `refine_task` | Implemented: plan edits and atomic native pre-claim description/estimate/instruction updates. |
| A05 | `add_task_dependency` | Implemented: plan edge addition or native pending-task dependency replacement with cycle checking. |
| A06 | `remove_task_dependency` | Implemented: plan/native pending edge removal; native readiness recomputation releases work. |
| A07 | `decompose_task` | Native helper inference, validated child plans and inherited resources/dependencies. |
| A08 | `inspect_task` | Public description, native status and authorized resources; successful query fixture required. |
| A09 | `get_workflow_status` | Read-only native result/status, composite and cost projection. |
| A10 | `get_available_agents` | Current public roster; capacity metadata is informational. |
| A11 | `get_pending_tasks` | Separate unbound descriptions from native pending/blocked tasks and unresolved bindings. |
| A12 | `send_message` | Native scoped communication with deterministic action idempotency key. |
| A13 | `noop` | One decision plus bounded native waiting on active work; no collection phase. |
| A14 | Manager `request_end_workflow`, defined outside default actions | Deferred manager interface expansion; retain worker-originated end signal. |
| G01 | CoT manager: fresh observation-driven prompt, dynamic legal ID schemas, one structured action | Fresh one-action prompt in one checkpointed manager Worker; source resource/message/action previews keep prompts bounded while native storage retains full evidence. The pinned source helper disables dynamic ID enum generation; preserve typed action schemas and validate IDs in the action path. |
| G02 | RandomV2: chooses an action class randomly, then uses an LLM | RandomV2 selects one feasible action class, calls Qwen with that schema and records source model-error fallback. No new Worker or task runtime. |
| G03 | Assign-all: LLM bulk assignment with fallback | One Qwen bulk mapping, source fallback for gaps/errors, composite-to-leaf expansion, native admission in dependency order, then no-ops. Explicit model honored. |
| G04 | AI worker: persona/configuration, structured resources, tools and reported costs | Retain source role prompts, 200-character input-resource previews, typed output and communication tools via native inference; full prerequisite outputs stay available to native code. |
| G05 | Human worker: LLM roleplay with personality, expertise and work style | Native human roleplay with immutable typed input state and source persona. |
| G06 | Human fatigue: `min(hours_worked_today × fatigue_rate, 0.5)` | Retain min(prior accounted hours × fatigue_rate, 0.5); read eligible completed native attempts once at invocation start. |
| G07 | Human quality: Gaussian noise minus fatigue, clamped to [0,1] | Retain Gaussian quality minus fatigue and clamp to [0,1]; persist draw. |
| G08 | Human speed: independent Gaussian multiplier with minimum 0.1 | Retain independent Gaussian speed with minimum 0.1; no new fatigue-speed coupling. |
| G09 | Human duration: provided estimate or auxiliary LLM estimate; normal path applies speed; cost uses hourly rate | Retain estimate/auxiliary inference, duration rules and wage cost; estimator uses internal Qwen. |
| G10 | Human misunderstanding: LLM wrong-work path can report success; duration/cost still accrue | Retain source misunderstanding behavior, including omitted fatigue-hours/count accrual. Episode labor and wage cost still accrue. |
| G11 | “Today” has no actual daily reset; break tool does not reset fatigue | Retained absence of daily reset/recovery; no new workday model. |
| G12 | Overlapping work for one human can observe mutable state at timing-dependent moments | Concurrent invocations can see the same completed history. Persist exact input attempt IDs and sampled effects; no actor serialization or admission barrier. |
| G13 | Stakeholder assigned work uses an LLM | Native stakeholder assigned-work inference with independent configured identity. |
| G14 | Stakeholder tick policy uses rules/RNG, personas and a delayed outbox | Source scripted stakeholder rules/RNG and outbox run as a manager-owned benchmark function, with native actor-attributed messages. Assigned stakeholder work is a native LLM Worker. |
| G15 | Stakeholder policy repeatedly scans recent 20 messages without deduplication | Retain repeated recent-message scanning; distinguish generated replies from delivery retries. |
| G16 | Decomposition and human estimation have auxiliary model calls | Decomposition and human estimation use checkpointed inference within their owning Worker. Capture native transcript/usage; no empty helper Task per call. |
| G17 | Actual runner-installed tools differ from ToolFactory defaults; some names duplicate | The pinned runner installs six communication tools; its nonempty additional-tools list bypasses ToolFactory defaults. Port the actually reachable tool set. |
| G18 | Placeholder search/analysis/code/break tools | Unused source placeholder search/analysis/code/break tools are not installed by this profile. Adding real tools is deferred. |
| G19 | Model settings and seed forwarding differ between SDK paths | All roles and judges use explicit internal Qwen. Record max tokens, request/operation limits, temperatures and the verified 2,048-token thinking budget. |
| G20 | Randomness partly uses module-global state | Purpose-scoped RNG derives from episode seed, actor/task and decision index. Draws/results are checkpointed; live model and asynchronous timing determinism are not promised. |
| C01 | Direct, multicast and broadcast messaging | Existing Thread/ThreadMessage store; recipient-scoped direct/multicast/broadcast tools. |
| C02 | Recent, sender/conversation, thread and task filters | Native participant-scoped recent/conversation/task message reads preserve ordering and filters. No duplicate message store. |
| C03 | Messages readable during still-running work | Messages available while sender is running; never delayed until worker output. |
| C04 | Stakeholder reply latency and scheduled preference/team events | Decision index drives team/preference events and stakeholder reply delays; it never gates completion or native dependency release. |
| C05 | Worker end-workflow signal | Typed end request stops new decisions then drains created work. |
| C06 | One manager action each discrete timestep; collect old work before dispatching new work | Accepted native scheduler change: immediate ordinary dependency/result behavior. |
| C07 | Prior-work collection uses a shared 300-second wall-clock timeout | Source shared collection timer is not reproduced. WorkerContext waits support actual continuation; the root has one explicit terminal drain deadline. |
| C08 | Simulated human duration does not determine task finish tick | Simulated hours are metrics; native runtime completion determines result availability. |
| C09 | Total simulated hours sum labor; AI reported duration derives from inference wall time | Retain reported labor/inference-duration measures; separate wall time, GPU usage and provider cost. |
| C10 | Default 50-step run executes 0–49, excluding later events | 50 manager decisions at indices 0–49; events at 50+ require a recorded longer profile. |
| C11 | Completion, end request and horizon are benchmark end reasons | Stop decisions at completion, worker end request or decision budget; drain admitted work, freeze root output, then native evaluator jobs score it. |
| C12 | In-flight work at termination or parent failure | Native cancellation/failure owns in-flight tasks. Policy-cancelled prerequisites are valid outcomes; missing progress and execution/model failures produce incomplete grading. |
| C13 | Retried/delayed delivery of actions and results | Reuse native durable task tools and checkpoints. Replay identical persisted context; raise on mismatch. No second journal or exactly-once provider claim. |
| C14 | Crash recovery and saved snapshots | Native step suspension/replay is supported. Captured final snapshots can be re-evaluated. Transparent recovery of a provider response lost before checkpoint remains outside the guarantee. |
| E01 | All 1,281 composed rubric definitions, including callables and prompt text | All 1,281 definitions are packaged; exact source names, maxima and prompt hashes are checked against the row manifest. |
| E02 | Default runner evaluates at completion | Retain ordinary terminal selection: 1,230 criteria, comprising 876 LLM and 354 callable definitions across the catalog. |
| E03 | Optional each-tick evaluation, forced checkpoints and `BOTH` enum | Preserve cadence metadata and source ON_COMPLETION selection quirks, including exclusion of preference BOTH rows. Optional tick execution is deferred. |
| E04 | Callable return normalization and clamping to each rubric's maximum | Retain source return normalization, raw evidence and per-rubric clamping. |
| E05 | LLM boolean/category/numeric output interpretation | Retain interpretation and source no-scope workflow renderer with 300-character resource previews; callable context remains complete. Qwen replaces the source judge model explicitly. |
| E06 | Preference groups use `sum(raw)/sum(max)` regardless of advertised aggregation strategy | Retain executed sum(raw)/sum(max) preference-group formula. |
| E07 | Utility is sum of preference-group score × final preference weight | One root episode score using frozen final preference weights. |
| E08 | Goal, constraints, efficiency and communication workflow evaluators | Diagnostics remain inspectable in that evaluation and never enter utility. |
| E09 | Scheduled preference update currently mutates earlier snapshots | Fix future preference updates mutating earlier snapshots; copy-on-update history is part of mag-native-v1. |
| E10 | Rubric judge-model override currently ignored | Honor and record the explicit judge model through the existing resolver. |
| E11 | Source silently turns some judge errors/refusals into zero | Exhausted judge/model or infrastructure errors opt into native incomplete/null. Do not replace missing scores with zero. |
| E12 | Source executes rubrics concurrently, semaphore default 100; Ergon executes sequentially | Use the existing serial evaluator. No benchmark grading scheduler or new criterion concurrency layer; monitor the one-hour E2B limit. |
| E13 | Default context includes workflow/preferences/tick; registered extra requests use manager actions and messages by sender | Freeze complete native workflow projection; map decision index explicitly into source context fields. |
| E14 | Some declared context channels are placeholders or unrequested by this catalog | Retain catalog-used context only; no invented private information or silent placeholder defaults. |
| E15 | Re-evaluation of saved final state | make_snapshot_reevaluation_sample and reevaluate.py submit a separate native sample linked to the original sample/hash. Reject schema rewrites of exported JSON. |
| E16 | General reward aggregators, alternative projections and dense reward vector | Raw preference scores retained; alternative reward projections and dense RL rewards deferred. |
| O01 | Standard samples, attempts, generations, messages, resources and evaluation summaries | Existing SampleRecord, graph, attempts, context, messages, resources and evaluation summaries own all execution evidence. |
| O02 | Human state from PostgreSQL | Code supplies typed fatigue inputs from completed PostgreSQL attempts, with exact source attempt IDs. No raw SQL tool or extra fatigue table. |
| O03 | Logical tick, actor ID, task ID, sampled effects and committed sequence | Decision/logical/native/actor IDs, input attempt sets and draws are evidence; runtime owns status. |
| O04 | Infrastructure error versus valid low score | Null incomplete score survives native jobs, persistence, REST/events and dashboard rollups; numeric zero remains a valid score. |
| O05 | Sandbox/runtime composition | Reuse E2BSandbox/E2BSandboxRuntime and native per-task setup/reattachment/cleanup. The VM filesystem holds retained blobs only. |
| O06 | Usage/cost | Retain successful inference usage, native attempts, settings and wall time; distinguish simulated wages from billing. Failed pre-checkpoint provider usage may be unavailable. |
| O07 | RL extension | Configured actor keys and decision/context records support a later manager-only RL integration. Training/filtering/token alignment/reward attachment are deferred. |
| O08 | Split and comparisons | Evaluation seed/suite/model provenance; no invented official training split. |
| O09 | Extended simulator/product features | Scheduler replacement, new capacity/day rules, real tools/people/UI and unregistered scenario deferred. |


## Source and verification references

- [Architecture](../../architecture/09_manager_gym.md) and its linked native owners.
- [Scenario inventory](../../rfcs/active/2026-09-07-manager-gym-port/evidence/mag-inventory-and-probes.json).
- [Row-level rubric inventory](../../rfcs/active/2026-09-07-manager-gym-port/evidence/rubric-inventory.csv).
- [Historical proof receipts](../../rfcs/active/2026-09-07-manager-gym-port/evidence/native-proof/README.md).
- [Operating and export commands](../../../examples/manager_gym/README.md).

The original PRD/RFC/audit are retained as historical design evidence. They do
not authorize per-decision Tasks, optional/local sandboxes, actor queues or
additional runtime ownership. Current source and the acceptance ledger take
precedence over earlier prose that claimed a feature was still only proposed.

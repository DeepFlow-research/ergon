# Inngest Refactor Cleanup Index

This folder breaks the refactor plan into one file per architectural violation so it is easier to review.

## Goal

Keep Inngest as the orchestration layer, but remove Inngest concepts from the core execution and evaluation logic.

The target rule is:

- runners orchestrate
- services execute business logic
- domain models stay framework-agnostic

## Files

- `01_rubric_api_depends_on_inngest.md`
  - Rubric interfaces currently take `inngest.Context` and own orchestration concerns.

- `02_evaluation_runner_inngest_aware.md`
  - `EvaluationRunner` is acting as an Inngest-aware service instead of a framework-agnostic execution helper.

- `03_worker_execution_ambient_step_context.md`
  - Worker execution currently depends on ambient Inngest step injection via `set_step(...)` and `as_step(...)`.

- `04_rubrics_orchestrate_criterion_fanout.md`
  - Benchmark rubrics currently construct criterion events and choose the fanout strategy themselves.

- `05_step_durability_shapes_service_apis.md`
  - Several handlers are structured around `step.run(...)` rather than around application service boundaries.

- `06_events_and_services_tightly_interleaved.md`
  - Event DTOs, handler logic, and service responsibilities are too tightly coupled.

- `07_rubric_criterion_service_redesign.md`
  - Concrete redesign for criteria as the extension point, rubrics as metadata plus aggregation, and a separate service/executor owning Inngest orchestration.

- `08_remaining_task_orchestration_cleanup.md`
  - Implementation-ready plan for the first task/workflow cleanup wave: evaluator dispatch, task execution, and workflow finalization.

- `09_post_cleanup_status_and_next_wave.md`
  - Post-implementation status check plus the recommended next cleanup wave for the remaining thick runners.

- `10_workflow_start_initialization_service.md`
  - Implementation-ready spec for extracting `WorkflowInitializationService` from `workflow_start.py`.

- `11_task_propagation_service.md`
  - Implementation-ready spec for extracting `TaskPropagationService` from `task_propagate.py`.

- `12_otel_sidecar_tracing_implementation.md`
  - Implementation-ready spec for adding OTEL tracing via a collector sidecar across workflow, task, worker, sandbox, and evaluation execution.

## Recommended Reading Order

1. `01_rubric_api_depends_on_inngest.md`
2. `04_rubrics_orchestrate_criterion_fanout.md`
3. `02_evaluation_runner_inngest_aware.md`
4. `03_worker_execution_ambient_step_context.md`
5. `05_step_durability_shapes_service_apis.md`
6. `06_events_and_services_tightly_interleaved.md`
7. `07_rubric_criterion_service_redesign.md`
8. `08_remaining_task_orchestration_cleanup.md`
9. `09_post_cleanup_status_and_next_wave.md`
10. `10_workflow_start_initialization_service.md`
11. `11_task_propagation_service.md`
12. `12_otel_sidecar_tracing_implementation.md`

## Suggested Implementation Order

1. Separate service DTOs from event DTOs.
2. Extract services from thick Inngest handlers.
3. Remove `inngest.Context` from rubric interfaces.
4. Move criterion fanout out of rubric implementations.
5. Make `EvaluationRunner` framework-agnostic.
6. Remove ambient step injection from worker execution.

## Cross-Reference

The broader narrative version still exists in `a.md`. This folder is the reviewer-friendly breakdown.

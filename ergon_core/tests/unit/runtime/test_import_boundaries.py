def test_telemetry_models_import_before_run_resource_api() -> None:
    from ergon_core.core.persistence.telemetry.models import RunResource

    from ergon_core.core.application.resources import RunResourceView

    assert RunResource.__tablename__ == "run_resources"
    assert RunResourceView.__name__ == "RunResourceView"


def test_context_models_import_without_worker_cycle() -> None:
    from ergon_core.core.persistence.context.models import RunContextEvent

    assert RunContextEvent.__tablename__ == "run_context_events"


def test_context_event_payloads_use_shared_logprob_type_without_api_cycle() -> None:
    from ergon_core.core.domain.generation.context_parts import ContextPartChunkLog, TokenLogprob
    from ergon_core.core.persistence.context.event_payloads import ContextEventPayload

    assert ContextEventPayload is ContextPartChunkLog
    assert ContextPartChunkLog.model_fields["logprobs"].annotation == list[TokenLogprob] | None


def test_worker_execute_does_not_expose_result_adapter_helpers() -> None:
    import ergon_core.core.application.jobs.worker_execute as worker_execute

    assert not hasattr(worker_execute, "_worker_execute_result_from_output")
    assert not hasattr(worker_execute, "_worker_execute_result_from_exception")


def test_runs_api_does_not_own_run_snapshot_read_model_helpers() -> None:
    import ergon_core.core.rest_api.runs as runs_api

    assert not hasattr(runs_api, "_build_task_map")
    assert not hasattr(runs_api, "_task_keyed_executions")
    assert not hasattr(runs_api, "_task_keyed_resources")
    assert not hasattr(runs_api, "_task_keyed_evaluations")
    assert not hasattr(runs_api, "_task_keyed_sandboxes")
    assert not hasattr(runs_api, "_build_communication_threads")
    assert not hasattr(runs_api, "_task_timestamps")
    assert not hasattr(runs_api, "_context_events_by_task")


def test_runtime_jobs_do_not_import_v1_evaluation_dispatch_dtos() -> None:
    import inspect

    import ergon_core.core.application.evaluation.models as evaluation_models
    import ergon_core.core.application.jobs.evaluate_task_run as evaluate_task_run
    import ergon_core.core.application.jobs.execute_task as execute_task
    from ergon_core.core.application.evaluation.service import EvaluationService

    removed_dispatch_symbols = {
        "CriterionContext",
        "DispatchEvaluatorsCommand",
        "PreparedEvaluatorDispatch",
        "PreparedSingleEvaluator",
        "TaskEvaluationContext",
    }

    assert not hasattr(EvaluationService, "prepare_dispatch")
    assert all(not hasattr(evaluation_models, name) for name in removed_dispatch_symbols)
    runtime_source = inspect.getsource(execute_task) + inspect.getsource(evaluate_task_run)
    runtime_dispatch_symbols = removed_dispatch_symbols - {"CriterionContext"}
    assert all(name not in runtime_source for name in runtime_dispatch_symbols)
    assert "prepare_dispatch" not in runtime_source

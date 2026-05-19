from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def _python_files(*roots: str) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        path = ROOT / root
        if path.is_file():
            files.append(path)
        else:
            files.extend(path.rglob("*.py"))
    return sorted(files)


def test_runtime_and_tooling_do_not_import_process_local_registry() -> None:
    """PR14 deletes ``ergon_core.api.registry`` as a public/runtime surface."""

    forbidden = "ergon_core.api.registry"
    offenders = [
        path.relative_to(ROOT).as_posix()
        for path in _python_files(
            "ergon_core/ergon_core",
            "ergon_cli/ergon_cli",
            "tests/fixtures/smoke_components",
            "scripts/smoke_reassert.py",
        )
        if path.relative_to(ROOT).as_posix() != "ergon_core/ergon_core/api/registry.py"
        and forbidden in path.read_text()
    ]

    assert offenders == []


def test_process_local_registry_module_is_deleted() -> None:
    assert not (ROOT / "ergon_core/ergon_core/api/registry.py").exists()


def test_persistent_component_catalog_model_is_deleted() -> None:
    assert not (ROOT / "ergon_core/ergon_core/core/persistence/components/models.py").exists()


def test_telemetry_models_import_before_run_resource_api() -> None:
    from ergon_core.core.persistence.telemetry.models import RunResource

    from ergon_core.core.application.resources import RunResourceView

    assert RunResource.__tablename__ == "run_resources"
    assert RunResourceView.__name__ == "RunResourceView"


def test_context_models_import_without_worker_cycle() -> None:
    from ergon_core.core.persistence.context.models import RunContextEvent

    assert RunContextEvent.__tablename__ == "run_context_events"


def test_context_part_logs_use_shared_logprob_type_without_api_cycle() -> None:
    from ergon_core.core.shared.context_parts import ContextPartChunkLog, TokenLogprob

    assert ContextPartChunkLog.model_fields["logprobs"].annotation == list[TokenLogprob] | None


def test_worker_execute_does_not_expose_result_adapter_helpers() -> None:
    import ergon_core.core.application.jobs.worker_execute as worker_execute

    assert not hasattr(worker_execute, "_worker_execute_result_from_output")
    assert not hasattr(worker_execute, "_worker_execute_result_from_exception")


def test_runs_api_does_not_own_run_snapshot_read_model_helpers() -> None:
    import ergon_core.core.infrastructure.http.routes.runs as runs_api

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

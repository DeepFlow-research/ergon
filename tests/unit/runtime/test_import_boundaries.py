def test_telemetry_models_import_before_run_resource_api() -> None:
    from ergon_core.core.persistence.telemetry.models import RunResource

    from ergon_core.core.runtime.resources import RunResourceView

    assert RunResource.__tablename__ == "run_resources"
    assert RunResourceView.__name__ == "RunResourceView"


def test_context_models_import_without_worker_cycle() -> None:
    from ergon_core.core.persistence.context.models import RunContextEvent

    assert RunContextEvent.__tablename__ == "run_context_events"


def test_context_event_payloads_use_shared_logprob_type_without_api_cycle() -> None:
    from ergon_core.core.generation import ContextPartChunkLog, TokenLogprob
    from ergon_core.core.persistence.context.event_payloads import ContextEventPayload

    assert ContextEventPayload is ContextPartChunkLog
    assert ContextPartChunkLog.model_fields["logprobs"].annotation == list[TokenLogprob] | None


def test_worker_execute_does_not_expose_result_adapter_helpers() -> None:
    import ergon_core.core.runtime.inngest.worker_execute as worker_execute

    assert not hasattr(worker_execute, "_worker_execute_result_from_output")
    assert not hasattr(worker_execute, "_worker_execute_result_from_exception")

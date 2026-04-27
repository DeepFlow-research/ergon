def test_telemetry_models_import_before_run_resource_api() -> None:
    from ergon_core.core.persistence.telemetry.models import RunResource

    from ergon_core.api.run_resource import RunResourceView

    assert RunResource.__tablename__ == "run_resources"
    assert RunResourceView.__name__ == "RunResourceView"


def test_context_models_import_without_worker_cycle() -> None:
    from ergon_core.core.persistence.context.models import RunContextEvent

    assert RunContextEvent.__tablename__ == "run_context_events"


def test_context_event_payloads_use_shared_logprob_type_without_api_cycle() -> None:
    from typing import get_args

    from ergon_core.core.persistence.context.event_payloads import ToolCallPayload
    from ergon_core.core.providers.generation.types import TokenLogprob

    annotation_args = get_args(ToolCallPayload.model_fields["turn_logprobs"].annotation)
    list_annotation = next(arg for arg in annotation_args if get_args(arg))

    assert get_args(list_annotation) == (TokenLogprob,)

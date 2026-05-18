from uuid import uuid4

from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
)


def test_run_request_identifies_definition() -> None:
    definition_id = uuid4()

    request = ExperimentRunRequest(definition_id=definition_id)

    assert request.definition_id == definition_id
    assert request.wait is True

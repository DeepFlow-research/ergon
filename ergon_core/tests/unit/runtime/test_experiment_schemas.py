from uuid import uuid4

from ergon_core.core.application.experiments.models import (
    ExperimentRunRequest,
)


def test_run_request_identifies_defined_experiment() -> None:
    experiment_id = uuid4()

    request = ExperimentRunRequest(experiment_id=experiment_id)

    assert request.experiment_id == experiment_id
    assert request.wait is True

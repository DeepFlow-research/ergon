from uuid import uuid4

import pytest
from ergon_core.core.runtime.services.experiment_schemas import (
    ExperimentDefineRequest,
    ExperimentRunRequest,
)
from pydantic import ValidationError


def test_define_request_accepts_optional_name_cohort_and_evaluator() -> None:
    request = ExperimentDefineRequest(
        benchmark_slug="researchrubrics",
        limit=5,
        default_model_target="anthropic:claude-sonnet-4.6",
        default_worker_team={"primary": "researchrubrics-workflow-cli-react"},
    )

    assert request.name is None
    assert request.cohort_id is None
    assert request.default_evaluator_slug is None


@pytest.mark.parametrize(
    "payload",
    [
        {
            "benchmark_slug": "researchrubrics",
            "default_model_target": "anthropic:claude-sonnet-4.6",
            "default_worker_team": {"primary": "worker"},
        },
        {
            "benchmark_slug": "researchrubrics",
            "limit": 5,
            "sample_ids": ["a"],
            "default_model_target": "anthropic:claude-sonnet-4.6",
            "default_worker_team": {"primary": "worker"},
        },
    ],
)
def test_define_request_requires_exactly_one_sample_selector(payload) -> None:
    with pytest.raises(ValidationError, match="exactly one"):
        ExperimentDefineRequest.model_validate(payload)


def test_define_request_requires_assignment_defaults_without_arms() -> None:
    with pytest.raises(ValidationError, match="default_worker_team"):
        ExperimentDefineRequest(
            benchmark_slug="researchrubrics",
            limit=5,
        )


def test_define_request_accepts_design_arms_without_defaults() -> None:
    request = ExperimentDefineRequest(
        benchmark_slug="researchrubrics",
        sample_ids=["a"],
        design={
            "arms": {
                "baseline": {
                    "worker_team": {"primary": "worker"},
                    "model_target": "anthropic:claude-sonnet-4.6",
                },
            },
        },
    )

    assert request.default_worker_team == {}
    assert request.design["arms"]["baseline"]["worker_team"] == {"primary": "worker"}


def test_run_request_identifies_defined_experiment() -> None:
    experiment_id = uuid4()

    request = ExperimentRunRequest(experiment_id=experiment_id)

    assert request.experiment_id == experiment_id
    assert request.wait is True


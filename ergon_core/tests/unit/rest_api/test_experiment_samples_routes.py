from datetime import UTC, datetime
from uuid import uuid4

from ergon_core.core.infrastructure.http.routes import experiments as module
from ergon_core.core.infrastructure.http.routes.experiments import router
from ergon_core.core.views.experiments.models import (
    EnvironmentContributionView,
    ExperimentDetailView,
    ExperimentSamplesView,
    ExperimentSampleSummaryView,
    SamplerInvocationsView,
    SamplerInvocationView,
)
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeExperimentReadService:
    def __init__(self) -> None:
        self.experiment_id = uuid4()
        self.environment_id = uuid4()
        self.sample_id = uuid4()

    def get_experiment_state(self, experiment_id):
        return ExperimentDetailView(
            experiment_id=experiment_id,
            name="mixed-training",
            environments=[
                EnvironmentContributionView(
                    environment_id=self.environment_id,
                    environment_name="mini-validation",
                    source_mode="materialized",
                    sample_count=1,
                    selected_count=1,
                )
            ],
            sample_count=1,
            samples=[
                ExperimentSampleSummaryView(
                    sample_id=self.sample_id,
                    experiment_id=experiment_id,
                    environment_id=self.environment_id,
                    environment_name="mini-validation",
                    sample_key="problem-1",
                    status="completed",
                    created_at=datetime(2026, 5, 26, tzinfo=UTC),
                )
            ],
            sampler_invocations=[],
            created_at=datetime(2026, 5, 26, tzinfo=UTC),
        )

    def list_experiment_samples(self, experiment_id):
        return ExperimentSamplesView(
            items=[
                ExperimentSampleSummaryView(
                    sample_id=self.sample_id,
                    experiment_id=experiment_id,
                    environment_id=self.environment_id,
                    environment_name="mini-validation",
                    sample_key="problem-1",
                    status="completed",
                    created_at=datetime(2026, 5, 26, tzinfo=UTC),
                )
            ]
        )

    def list_sampler_invocations(self, experiment_id):
        return SamplerInvocationsView(
            items=[
                SamplerInvocationView(
                    sampler_invocation_id=uuid4(),
                    sampler_name="random",
                    requested_k=1,
                    candidate_pool_size=4,
                    selected_count=1,
                    created_at=datetime(2026, 5, 26, tzinfo=UTC),
                )
            ]
        )


def test_experiment_detail_lists_environment_contributions(monkeypatch) -> None:
    service = _FakeExperimentReadService()
    monkeypatch.setattr(module, "ExperimentReadService", lambda: service)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    response = client.get(f"/experiments/{service.experiment_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["environments"][0]["environmentName"] == "mini-validation"
    assert body["environments"][0]["sampleCount"] == 1
    assert "definitionId" not in response.text
    assert "runId" not in response.text


def test_experiment_child_routes(monkeypatch) -> None:
    service = _FakeExperimentReadService()
    monkeypatch.setattr(module, "ExperimentReadService", lambda: service)
    app = FastAPI()
    app.include_router(router)
    client = TestClient(app)

    samples = client.get(f"/experiments/{service.experiment_id}/samples")
    invocations = client.get(f"/experiments/{service.experiment_id}/sampler-invocations")

    assert samples.status_code == 200
    assert samples.json()["items"][0]["sampleId"] == str(service.sample_id)
    assert "runId" not in samples.text
    assert invocations.status_code == 200
    assert invocations.json()["items"][0]["samplerName"] == "random"

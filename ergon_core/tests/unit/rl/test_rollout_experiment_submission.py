from uuid import uuid4

from ergon_core.core.infrastructure.http.routes.rollouts import router
from ergon_core.core.rl.rollout_types import BatchStatus, RolloutBatchSummary
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeRolloutService:
    def __init__(self) -> None:
        self.request = None

    async def submit_experiment_batch(self, request):
        self.request = request
        return RolloutBatchSummary(
            batch_id=uuid4(),
            sample_ids=[uuid4()],
            status=BatchStatus.PENDING,
            sampler_invocation_id=uuid4(),
        )


def test_experiment_rollout_route_accepts_camel_case_training_request() -> None:
    experiment_id = uuid4()
    service = _FakeRolloutService()
    app = FastAPI()
    app.state.rollout_service = service
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        f"/rollouts/experiments/{experiment_id}/rollout-batches",
        json={
            "experimentId": str(experiment_id),
            "k": 32,
            "sampler": "random",
            "samplerConfig": {"seed": 7},
            "candidatePoolSize": 256,
        },
    )

    assert response.status_code == 202
    assert service.request.experiment_id == experiment_id
    assert service.request.k == 32
    assert service.request.sampler == "random"
    assert service.request.sampler_config == {"seed": 7}
    assert service.request.candidate_pool_size == 256


def test_experiment_rollout_route_rejects_mismatched_experiment_id() -> None:
    app = FastAPI()
    app.state.rollout_service = _FakeRolloutService()
    app.include_router(router)
    client = TestClient(app)

    response = client.post(
        f"/rollouts/experiments/{uuid4()}/rollout-batches",
        json={
            "experimentId": str(uuid4()),
            "k": 1,
        },
    )

    assert response.status_code == 400

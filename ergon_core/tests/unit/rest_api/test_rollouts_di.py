from uuid import uuid4

from ergon_core.core.infrastructure.http.routes.rollouts import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeRolloutService:
    def __init__(self) -> None:
        self.batch_id = uuid4()
        self.sample_id = uuid4()
        self.submitted_request = None

    async def submit_experiment_batch(self, request: object) -> dict[str, object]:
        self.submitted_request = request
        return {
            "batch_id": self.batch_id,
            "sample_ids": [self.sample_id],
            "status": "pending",
            "sampler_invocation_id": str(uuid4()),
        }

    def get_rollout_batch_by_id(self, _batch_id: object) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "sample_ids": [self.sample_id],
            "status": "pending",
        }


class _FakeVLLMManager:
    def __init__(self) -> None:
        self.restarted_with: str | None = None

    def restart(self, checkpoint_path: str) -> None:
        self.restarted_with = checkpoint_path


def test_rollout_router_gets_experiment_service_from_app_state() -> None:
    experiment_id = uuid4()
    app = FastAPI()
    app.state.rollout_service = _FakeRolloutService()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post(
        f"/rollouts/experiments/{experiment_id}/rollout-batches",
        json={
            "experimentId": str(experiment_id),
            "k": 1,
        },
    )

    assert resp.status_code == 202
    assert app.state.rollout_service.submitted_request.experiment_id == experiment_id


def test_rollout_batch_route_exposes_sample_ids() -> None:
    app = FastAPI()
    app.state.rollout_service = _FakeRolloutService()
    app.include_router(router)
    client = TestClient(app)

    resp = client.get(f"/rollouts/batches/{app.state.rollout_service.batch_id}")

    assert resp.status_code == 200
    body = resp.json()
    assert body["sample_ids"] == [str(app.state.rollout_service.sample_id)]
    assert "run_ids" not in body


def test_sync_weights_gets_vllm_manager_from_app_state() -> None:
    manager = _FakeVLLMManager()
    app = FastAPI()
    app.state.vllm_manager = manager
    app.include_router(router)
    client = TestClient(app)

    resp = client.post(
        "/rollouts/sync-weights",
        json={
            "checkpoint_path": "/tmp/checkpoint",
            "model_name": "ignored-by-manager",
        },
    )

    assert resp.status_code == 200
    assert manager.restarted_with == "/tmp/checkpoint"

from uuid import uuid4

from ergon_core.core.rest_api.rollouts import router
from fastapi import FastAPI
from fastapi.testclient import TestClient


class _FakeRolloutService:
    def __init__(self) -> None:
        self.batch_id = uuid4()
        self.run_id = uuid4()

    def submit(self, _request: object) -> dict[str, object]:
        return {
            "batch_id": self.batch_id,
            "run_ids": [self.run_id],
            "status": "pending",
        }


class _FakeVLLMManager:
    def __init__(self) -> None:
        self.restarted_with: str | None = None

    def restart(self, checkpoint_path: str) -> None:
        self.restarted_with = checkpoint_path


def test_rollout_router_gets_service_from_app_state() -> None:
    app = FastAPI()
    app.state.rollout_service = _FakeRolloutService()
    app.include_router(router)
    client = TestClient(app)

    resp = client.post(
        "/rollouts/submit",
        json={
            "definition_id": str(uuid4()),
            "num_episodes": 1,
        },
    )

    assert resp.status_code == 202


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

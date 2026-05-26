from uuid import uuid4

import ergon_infra.adapters.trl_http as trl_http


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *args, **kwargs) -> None:
        self.requests = []
        self._polls = 0

    def post(self, path, *, json):
        self.requests.append(("POST", path, json))
        return _FakeResponse({"batch_id": "batch-1"})

    def get(self, path):
        self.requests.append(("GET", path, None))
        return _FakeResponse({"status": "complete", "trajectories": []})

    def delete(self, path):
        self.requests.append(("DELETE", path, None))
        return _FakeResponse({})


def test_trl_rollout_func_submits_experiment_batch(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(trl_http.httpx, "Client", lambda *args, **kwargs: fake)
    experiment_id = uuid4()

    rollout_func = trl_http.make_ergon_http_rollout_func(
        ergon_url="http://ergon.test",
        experiment_id=str(experiment_id),
        sampler="random",
        candidate_pool_size=256,
    )

    rollout_func([{"prompt": "a"}, {"prompt": "b"}], object())

    assert fake.requests[0] == (
        "POST",
        f"/rollouts/experiments/{experiment_id}/rollout-batches",
        {
            "experimentId": str(experiment_id),
            "k": 2,
            "sampler": "random",
            "samplerConfig": {},
            "candidatePoolSize": 256,
        },
    )

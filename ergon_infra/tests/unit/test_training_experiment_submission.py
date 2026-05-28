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
        return _FakeResponse({"batchId": "batch-1"})

    def get(self, path):
        self.requests.append(("GET", path, None))
        return _FakeResponse(
            {
                "status": "complete",
                "trainingRecords": [
                    {
                        "sampleId": "sample-1",
                        "actor": {"actorSlug": "planner", "baseWorkerSlug": "planner"},
                        "promptIds": [11, 12, 13],
                        "completionIds": [21, 22],
                        "logprobs": [-0.31, -0.42],
                        "reward": 0.75,
                    }
                ],
            }
        )

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


def test_trl_http_adapter_maps_projected_records_to_rollout_batch(monkeypatch) -> None:
    fake = _FakeClient()
    monkeypatch.setattr(trl_http.httpx, "Client", lambda *args, **kwargs: fake)

    rollout_func = trl_http.make_ergon_http_rollout_func(
        ergon_url="http://ergon.test",
        experiment_id=str(uuid4()),
    )

    batch = rollout_func([{"prompt": "a"}], object())

    assert batch["prompt_ids"] == [[11, 12, 13]]
    assert batch["completion_ids"] == [[21, 22]]
    assert batch["logprobs"] == [[-0.31, -0.42]]
    assert batch["completion_reward"] == [0.75]
    assert batch["trace_metadata"][0]["actor"]["actorSlug"] == "planner"


def test_trl_http_adapter_rejects_or_ignores_legacy_trajectories_payload(monkeypatch) -> None:
    class LegacyClient(_FakeClient):
        def get(self, path):
            self.requests.append(("GET", path, None))
            return _FakeResponse({"status": "complete", "trajectories": []})

    fake = LegacyClient()
    monkeypatch.setattr(trl_http.httpx, "Client", lambda *args, **kwargs: fake)
    rollout_func = trl_http.make_ergon_http_rollout_func(
        ergon_url="http://ergon.test",
        experiment_id=str(uuid4()),
        timeout_s=0.01,
    )

    try:
        rollout_func([{"prompt": "a"}], object())
    except RuntimeError as exc:
        assert "trainingRecords" in str(exc)
    else:
        raise AssertionError("legacy trajectories payload was accepted")

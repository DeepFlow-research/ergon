from uuid import uuid4

from pydantic import ValidationError

from ergon_core.core.persistence.telemetry.models import RolloutBatch
from ergon_core.core.rl.rollout_types import BatchStatus
from ergon_core.core.shared.rollout_status import RolloutStatus


def test_rollout_api_and_persistence_share_status_contract() -> None:
    assert BatchStatus is RolloutStatus

    batch = RolloutBatch.model_validate(
        {
            "definition_id": str(uuid4()),
            "status": RolloutStatus.RUNNING,
        }
    )

    assert batch.status == RolloutStatus.RUNNING


def test_rollout_batch_rejects_unknown_status() -> None:
    try:
        RolloutBatch.model_validate(
            {
                "definition_id": str(uuid4()),
                "status": "not-a-status",
            }
        )
    except ValidationError as exc:
        assert "not-a-status" in str(exc)
    else:
        raise AssertionError("RolloutBatch accepted an unknown status")

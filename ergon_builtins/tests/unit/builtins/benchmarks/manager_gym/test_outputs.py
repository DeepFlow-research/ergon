"""Creation identifiers belong to native code, not the model's deliverable schema."""

from unittest.mock import AsyncMock
from uuid import uuid5

import pytest

from ergon_builtins.benchmarks.manager_gym import workers
from ergon_builtins.benchmarks.manager_gym.inference import INTERNAL_MODEL, InferenceResult
from ergon_builtins.benchmarks.manager_gym.outputs import AITaskOutput
from ergon_builtins.benchmarks.manager_gym.state import EpisodeConfig, new_episode, all_tasks


@pytest.mark.asyncio
async def test_native_resource_ids_are_assigned_without_model_uuid_validation(monkeypatch):
    assert "id" not in AITaskOutput.model_json_schema()["$defs"]["ResourceDraft"]["properties"]
    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery"))
    planned = next(t for t in all_tasks(state.workflow).values() if not t.subtasks)
    actor = next(a for a in state.actors.values() if a["agent_type"] == "ai")
    output = {
        "reasoning": "Created the deliverable",
        "resources": [
            {
                "id": "not-a-uuid",
                "name": "Report",
                "description": "Work output",
                "content": "Evidence",
            }
        ],
        "confidence": 0.9,
        "execution_notes": [],
    }
    monkeypatch.setattr(
        workers,
        "infer",
        AsyncMock(
            return_value=InferenceResult(
                output=output, elapsed_seconds=0.1, input_tokens=1, output_tokens=1
            )
        ),
    )
    payload = workers.WorkPayload(episode=state.config, planned_task=planned, actor=actor)
    result = await workers.MAGWorkWorker(name=actor["agent_id"], model=INTERNAL_MODEL)._work(
        payload, workers.WorkInputs(resources=[]), None
    )
    assert result.resources[0].id == uuid5(planned.id, "output/0")
    assert result.resources[0].content == "Evidence"

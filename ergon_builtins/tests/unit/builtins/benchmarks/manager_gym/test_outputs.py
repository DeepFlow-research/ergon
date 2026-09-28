"""Creation identifiers belong to native code, not the model's deliverable schema."""

from unittest.mock import AsyncMock
from types import SimpleNamespace
from uuid import uuid5

import pytest

from ergon_builtins.benchmarks.manager_gym import workers
from ergon_builtins.benchmarks.manager_gym import inference
from ergon_builtins.benchmarks.manager_gym.manager import work_task
from ergon_builtins.llm.resolution import ResolvedModel
from ergon_core.api.worker import WorkerOutput
from pydantic_ai.models import override_allow_model_requests
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.messages import ModelResponse, ToolCallPart
from ergon_builtins.benchmarks.manager_gym.inference import InferenceResult
from ergon_builtins.benchmarks.manager_gym.outputs import AITaskOutput
from ergon_builtins.benchmarks.manager_gym.state import EpisodeConfig, new_episode, all_tasks

MODEL = "openai-compatible:http://localhost:8000/v1#test-model"


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
    result = await workers.MAGWorkWorker(name=actor["agent_id"], model=MODEL)._work(
        payload, workers.WorkInputs(resources=[]), None
    )
    assert result.resources[0].id == uuid5(planned.id, "output/0")
    assert result.resources[0].content == "Evidence"


@pytest.mark.asyncio
@pytest.mark.parametrize("output_kind", ["invalid", "empty_human"])
async def test_invalid_model_output_is_a_durable_native_failed_work_result(
    monkeypatch, output_kind
):
    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery"))
    planned = next(t for t in all_tasks(state.workflow).values() if not t.subtasks)
    actor_type = "human_mock" if output_kind == "empty_human" else "ai"
    actor = next(k for k, a in state.actors.items() if a["agent_type"] == actor_type)
    planned.estimated_duration_hours = 1
    final = (
        {}
        if output_kind == "invalid"
        else {
            "reasoning": "No deliverable",
            "resources": [],
            "work_process": "Attempted work",
            "challenges_encountered": [],
            "quality_notes": "No output",
            "confidence_level": "low",
        }
    )
    task = work_task(state, planned, actor, MODEL, [])
    monkeypatch.setattr(
        inference,
        "resolve_model_target",
        lambda _: ResolvedModel(
            model=FunctionModel(
                lambda messages, info: ModelResponse(parts=[ToolCallPart("final_result", final)])
            )
        ),
    )
    monkeypatch.setattr(
        workers, "read_inputs", AsyncMock(return_value=workers.WorkInputs(resources=[]))
    )

    async def checkpoint(name, operation, *, output_type):
        result = await operation()
        return output_type.model_validate_json(result.model_dump_json())

    with override_allow_model_requests(True):
        items = [
            item
            async for item in task.worker.execute(
                task, context=SimpleNamespace(run_step=checkpoint)
            )
        ]
    output = items[-1]
    assert isinstance(output, WorkerOutput) and not output.success
    assert output.metadata["model_failure"]["kind"] == "output_validation"
    assert output.metadata["resources"] == []
    assert output.metadata["accounted_hours"] == 0
    assert len(items) > 1  # The unsuccessful attempt keeps its native transcript.

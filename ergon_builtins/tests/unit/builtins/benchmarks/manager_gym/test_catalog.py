"""Offline source-characterization and native snapshot contracts."""

from ergon_core.api.criterion import CriterionOutcome
from ergon_builtins.benchmarks.manager_gym.rubric import MAGRubric

import hashlib
import json
import math
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from ergon_core.api.criterion import CriterionContext
from ergon_core.api.worker import WorkerOutput
from ergon_core.test_support.task_factory import task_with_id
from ergon_builtins.benchmarks.manager_gym.actions import ManagerDecision
from ergon_builtins.benchmarks.manager_gym.inference import INTERNAL_MODEL, require_internal_model
from ergon_builtins.benchmarks.manager_gym.rubric import definitions, MAGCriterion, normalize_score
from ergon_builtins.benchmarks.manager_gym.sample import (
    make_manager_gym_sample,
    make_snapshot_reevaluation_sample,
    MAGSnapshotWorker,
)
from ergon_builtins.benchmarks.manager_gym.scenario_catalog import SCENARIOS
from ergon_builtins.benchmarks.manager_gym.source_types import Resource
from ergon_builtins.benchmarks.manager_gym.state import (
    EpisodeConfig,
    EpisodeState,
    new_episode,
    apply_timeline,
    all_tasks,
    public_observation,
    snapshot_hash,
)

ROOT = Path(__file__).resolve().parents[6]
INVENTORY = ROOT / "docs/rfcs/active/2026-09-07-manager-gym-port/evidence/rubric-inventory.json"


def test_large_native_artifacts_do_not_expand_manager_or_source_judge_previews():
    state = new_episode(EpisodeConfig(scenario="icaap"))
    resource = Resource(name="Large output", description="Native artifact", content="x" * 1_000_000)
    state.workflow.resources[resource.id] = resource
    before = snapshot_hash(state)
    observation = public_observation(state)
    preview = next(r for r in observation["resources"] if r["id"] == str(resource.id))
    assert preview["content"] == "x" * 300 and preview["content_characters"] == 1_000_000
    rendered = state.workflow.pretty_print()
    assert "x" * 300 in rendered and "x" * 301 not in rendered
    assert "chars=1000000" in rendered
    assert snapshot_hash(state) == before and len(resource.content) == 1_000_000


@pytest.mark.asyncio
async def test_snapshot_reevaluation_preserves_hash_and_links_original_sample():
    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery"))
    source_id = uuid4()
    sample = make_snapshot_reevaluation_sample(
        state, source_sample_id=source_id, environment_name="re-eval"
    )
    assert sample.source_metadata["evaluation_of_sample"] == str(source_id)
    assert sample.source_metadata["snapshot_hash"] == snapshot_hash(state)
    assert sample.source_metadata["inference_profile"]["request_settings"]["extra_body"] == {
        "thinking_token_budget": 2048
    }
    task = sample.tasks[0]
    write_file = AsyncMock()
    # Bind an existing sandbox-runtime test double, keeping normal Task authoring.
    task.sandbox._runtime = AsyncMock(write_file=write_file)
    worker = task.worker
    assert isinstance(worker, MAGSnapshotWorker)
    results = [result async for result in worker.execute(task, context=AsyncMock())]
    assert len(results) == 1 and results[0].metadata["snapshot_hash"] == snapshot_hash(state)
    assert json.loads(results[0].output) == state.model_dump(mode="json")
    write_file.assert_awaited_once()


@pytest.mark.parametrize("scenario", SCENARIOS)
def test_scenario_roundtrip_preserves_ids_hierarchy_and_private_preferences(scenario):
    config = EpisodeConfig(scenario=scenario)
    first, second = new_episode(config), new_episode(config)
    assert set(all_tasks(first.workflow)) == set(all_tasks(second.workflow))
    tasks = all_tasks(first.workflow)
    for task in tasks.values():
        assert all(dep in tasks for dep in task.dependency_task_ids)
        assert all(child.parent_task_id == task.id for child in task.subtasks)
    initial = json.dumps(first.preference_history, sort_keys=True)
    for tick in range(101):
        first.timestep = tick
        apply_timeline(first)
    assert json.dumps(first.preference_history[:1], sort_keys=True) == initial
    restored = EpisodeState.model_validate_json(first.model_dump_json())
    assert snapshot_hash(restored) == snapshot_hash(first)
    obs = public_observation(restored)
    assert "weights" not in obs and "actors" not in obs
    assert all("initial_preferences" not in actor for actor in obs["agents"])
    sample = make_manager_gym_sample(config)
    assert "evaluator_function" not in sample.model_dump_json()


def test_rubric_manifest_matches_pinned_source_inventory():
    reference = {row["id"]: row for row in json.loads(INVENTORY.read_text())["rubrics"]}
    native = [d for scenario in SCENARIOS for d in definitions(scenario, terminal_only=False)]
    assert len(native) == len(reference) == 1281
    for definition in native:
        expected = reference[definition.slug]
        assert definition.rubric.name == expected["rubric_name"]
        assert definition.rubric.max_score == expected["max_score"]
        if definition.rubric.llm_prompt:
            assert (
                hashlib.sha256(definition.rubric.llm_prompt.encode()).hexdigest()
                == expected["definition_sha256"]
            )
    selected = [d for scenario in SCENARIOS for d in definitions(scenario)]
    assert len(selected) == 1230
    assert sum(d.rubric.llm_prompt is not None for d in selected) == 876


@pytest.mark.asyncio
async def test_every_terminal_callable_runs_against_frozen_native_projection():
    count = 0
    for scenario in SCENARIOS:
        state = new_episode(EpisodeConfig(scenario=scenario))
        apply_timeline(state)
        state.workflow.completed_at = datetime.now(UTC)
        task = task_with_id(uuid4(), task_slug="test", instance_key="test", description="test")
        context = CriterionContext(
            sample_id=uuid4(),
            task_id=uuid4(),
            execution_id=uuid4(),
            task=task,
            worker_result=WorkerOutput(
                output=state.model_dump_json(), metadata={"snapshot_hash": snapshot_hash(state)}
            ),
        )
        for definition in definitions(scenario):
            if definition.rubric.evaluator_function:
                result = await MAGCriterion(
                    slug=definition.slug, scenario=scenario, model=INTERNAL_MODEL
                ).evaluate(context)
                assert math.isfinite(result.score)
                assert 0 <= result.score <= definition.rubric.max_score
                count += 1
    assert count == 354


def test_gateway_json_string_action_is_decoded_then_validated():
    action = {
        "action_type": "assign_task",
        "task_id": str(uuid4()),
        "agent_id": "alice",
        "reasoning": "Appropriate expertise.",
    }
    decision = ManagerDecision.model_validate(
        {"reasoning": "Proceed.", "action": json.dumps(action)}
    )
    assert decision.action.action_type == "assign_task"
    with pytest.raises(ValueError):
        ManagerDecision.model_validate(
            {"reasoning": "Proceed.", "action": '{"action_type":"invented"}'}
        )


@pytest.mark.parametrize(
    "target", ["openai:gpt-4o", "openrouter:qwen", "openai-compatible:https://example.com#qwen"]
)
def test_external_inference_cannot_be_enabled_by_a_fallback(target):
    with pytest.raises(ValueError):
        require_internal_model(target)


def test_source_score_encodings_have_distinct_scales():
    assert normalize_score(True, 10, llm=False)[0] == 1
    assert normalize_score(True, 10, llm=True)[0] == 10
    assert normalize_score("medium", 10, llm=True)[0] == pytest.approx(6.6)
    assert normalize_score((99, "evidence"), 10, llm=False) == (10, "evidence")


def test_utility_uses_raw_preference_scores_and_rejects_partial_results():

    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery"))
    rubric = MAGRubric(name="MAG", scenario=state.config.scenario, model=INTERNAL_MODEL)
    task = task_with_id(uuid4(), task_slug="test", instance_key="test", description="test")
    rows = [
        CriterionOutcome(
            slug=d.slug,
            name=d.rubric.name,
            score=d.rubric.max_score * 0.4,
            max_score=d.rubric.max_score,
            passed=False,
            metadata={
                "snapshot_hash": "same",
                "kind": d.kind,
                "owner": d.owner,
                "preference_weight": state.weights.get(d.owner, 0),
            },
        )
        for d in definitions(state.config.scenario)
    ]
    result = rubric.aggregate_task(task, rows)
    assert result.score == pytest.approx(0.4) and result.metadata["score_scale"] == "normalized_0_1"
    changed = [
        r.model_copy(update={"score": r.max_score}) if r.metadata["kind"] == "diagnostic" else r
        for r in rows
    ]
    assert rubric.aggregate_task(task, changed).score == result.score
    with pytest.raises(ValueError, match="Incomplete"):
        rubric.aggregate_task(task, rows[:-1])
    with pytest.raises(ValueError, match="different snapshots"):
        rubric.aggregate_task(
            task,
            [
                rows[0].model_copy(
                    update={"metadata": {**rows[0].metadata, "snapshot_hash": "changed"}}
                ),
                *rows[1:],
            ],
        )

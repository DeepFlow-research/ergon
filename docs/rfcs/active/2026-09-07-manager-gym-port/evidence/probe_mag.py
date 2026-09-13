"""Offline inventory and characterization probes; run with the upstream MAG venv.

Usage: python probe_mag.py MAG_CHECKOUT OUTPUT_JSON
No model requests are made. This is research evidence, not an Ergon implementation.
"""

import asyncio
import importlib.metadata
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from uuid import uuid4

mag_root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(mag_root))

from examples.common_stakeholders import create_stakeholder_agent
from examples.scenarios import SCENARIOS
from manager_agent_gym.core.communication.service import CommunicationService
from manager_agent_gym.core.evaluation.common_evaluators import build_default_evaluators
from manager_agent_gym.core.evaluation.scenario_constraints import build_constraints_for_scenario
from manager_agent_gym.core.evaluation.validation_engine import ValidationEngine
from manager_agent_gym.core.evaluation.validation_rules import WorkflowValidationRule
from manager_agent_gym.core.execution.engine import WorkflowExecutionEngine
from manager_agent_gym.core.workflow_agents.registry import AgentRegistry
from manager_agent_gym.core.workflow_agents.tool_factory import ToolFactory
from manager_agent_gym.schemas.config import OutputConfig
from manager_agent_gym.schemas.core.tasks import Task
from manager_agent_gym.schemas.core.workflow import Workflow
from manager_agent_gym.schemas.preferences.preference import Preference, PreferenceWeights
from manager_agent_gym.schemas.preferences.rubric import RunCondition, WorkflowRubric
from manager_agent_gym.schemas.preferences.weight_update import PreferenceWeightUpdateRequest
from tests.helpers.stubs import ManagerNoOp, StubAgent


def inventory():
    rows = []
    for key, spec in SCENARIOS.items():
        workflow = spec.create_workflow()
        preferences = spec.create_preferences()
        timeline = spec.create_team_timeline()
        updates = spec.create_preference_update_requests() if spec.create_preference_update_requests else []
        additions = [config for changes in timeline.values() for action, config, _ in changes if action == "add"]
        removals = [config for changes in timeline.values() for action, config, _ in changes if action == "remove"]
        tasks = {}
        for task in workflow.tasks.values():
            for node in [task, *task.get_all_subtasks_flat()]:
                tasks[node.id] = node
        pref_rubrics = [rubric for preference in preferences.preferences if preference.evaluator for rubric in preference.evaluator.rubrics]
        evaluators = build_default_evaluators(CommunicationService())
        if spec.create_evaluator_to_measure_goal_achievement:
            evaluators.append(spec.create_evaluator_to_measure_goal_achievement())
        constraints = build_constraints_for_scenario(key)
        if constraints:
            evaluators.append(constraints)
        workflow_rubrics = [rubric for evaluator in evaluators for rubric in evaluator.rubrics]
        # Match ValidationEngine's actual selection predicates, including its
        # unconditional workflow-rubric selection when cadence is not None.
        final_pref_rubrics = [r for r in pref_rubrics if r.run_condition == RunCondition.ON_COMPLETION]
        rows.append({
            "scenario": key,
            "initial_registry_tasks": len(workflow.tasks),
            "unique_tasks_including_nested": len(tasks),
            "atomic_tasks": sum(not task.subtasks for task in tasks.values()),
            "initial_resources": len(workflow.resources),
            "initial_registry_dependency_edges": sum(len(t.dependency_task_ids) for t in workflow.tasks.values()),
            "team_additions": len(additions),
            "team_removals": len(removals),
            "human_additions": sum(c.agent_type == "human_mock" for c in additions),
            "ai_additions": sum(c.agent_type == "ai" for c in additions),
            "team_change_ticks": sorted(timeline),
            "preference_change_ticks": [u.timestep for u in updates],
            "preferences": len(preferences.preferences),
            "preference_rubrics": len(pref_rubrics),
            "preference_llm_rubrics": sum(r.llm_prompt is not None for r in pref_rubrics),
            "workflow_rubrics": len(workflow_rubrics),
            "workflow_llm_rubrics": sum(r.llm_prompt is not None for r in workflow_rubrics),
            "final_selected_llm_rubrics": sum(r.llm_prompt is not None for r in final_pref_rubrics + workflow_rubrics),
            "worker_models": sorted({c.model_name for c in additions}),
            "configured_judge_models": sorted({r.llm_model for r in pref_rubrics + workflow_rubrics if r.llm_prompt}),
            "required_rubric_context": sorted({c.value for r in pref_rubrics + workflow_rubrics for c in r.required_context}),
        })
    return rows


async def characterize():
    results = {}
    models = []

    async def fake_validate(rule, context):
        models.append(rule.model)
        return SimpleNamespace(meta=None, message="stub", score=1.0)

    with patch.object(WorkflowValidationRule, "validate", fake_validate):
        await ValidationEngine(seed=42)._evaluate_single_rubric(
            Workflow(name="probe", workflow_goal="probe", owner_id=uuid4()),
            WorkflowRubric(name="model_probe", llm_prompt="probe", llm_model="sentinel-model"),
            None,
        )
    results["rubric_model_forwarding"] = {"requested": "sentinel-model", "called": models}

    prefs = PreferenceWeights(preferences=[Preference(name="quality", weight=0.5), Preference(name="speed", weight=0.5)])
    stakeholder = create_stakeholder_agent("balanced", prefs)
    before = stakeholder.get_preferences_for_timestep(0).get_preference_dict().copy()
    stakeholder.apply_weight_update(PreferenceWeightUpdateRequest(timestep=10, changes={"quality": 0.9, "speed": 0.1}, mode="absolute"))
    results["preference_history"] = {
        "t0_before": before,
        "t0_after_scheduling_t10": stakeholder.get_preferences_for_timestep(0).get_preference_dict(),
        "t10": stakeholder.get_preferences_for_timestep(10).get_preference_dict(),
    }

    workflow = Workflow(name="capacity", workflow_goal="probe", owner_id=uuid4())
    agent = StubAgent(agent_id="worker", agent_type="human_mock", seconds=0)
    workflow.add_agent(agent)
    for name in ["one", "two"]:
        workflow.add_task(Task(name=name, description="probe", assigned_agent_id=agent.agent_id))
    with tempfile.TemporaryDirectory(prefix="mag-port-probe-") as directory:
        engine = WorkflowExecutionEngine(
            workflow=workflow, agent_registry=AgentRegistry(), manager_agent=ManagerNoOp(),
            stakeholder_agent=create_stakeholder_agent("hands_off", PreferenceWeights()),
            output_config=OutputConfig(base_output_dir=Path(directory), create_run_subdirectory=False),
            enable_timestep_logging=False, enable_final_metrics_logging=False,
            max_timesteps=3, seed=42, log_preference_evaluation_progress=False,
        )
        await engine.execute_timestep()
        results["capacity"] = {"configured_capacity": agent.max_concurrent_tasks, "running_after_one_tick": len(engine.running_tasks)}
        await asyncio.gather(*engine.running_tasks.values())

    registry = AgentRegistry()
    for action, config, reason in SCENARIOS["icaap"].create_team_timeline()[0]:
        if action == "add":
            registry.schedule_agent_add(0, config, reason)
    registry.apply_scheduled_changes_for_timestep(0, communication_service=CommunicationService(), tool_factory=ToolFactory())
    results["scheduled_agent_tools"] = {}
    for agent in registry.list_agents():
        sdk_agent = agent.openai_agent if agent.agent_type == "ai" else agent.roleplay_agent
        results["scheduled_agent_tools"][agent.agent_id] = [tool.name for tool in sdk_agent.tools]
    return results


result = {
    "mag_commit": subprocess.check_output(["git", "-C", str(mag_root), "rev-parse", "HEAD"], text=True).strip(),
    "python": sys.version.split()[0],
    "versions": {name: importlib.metadata.version(name) for name in ("pydantic", "openai-agents", "instructor", "litellm")},
    "scenarios": inventory(),
    "characterization": asyncio.run(characterize()),
}
Path(sys.argv[2]).write_text(json.dumps(result, indent=2) + "\n")
print(json.dumps(result["characterization"], indent=2))

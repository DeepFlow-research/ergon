"""Enumerate rubric definitions offline from a pinned MAG checkout.

Usage: python inventory_rubrics.py MAG_CHECKOUT OUTPUT_DIRECTORY
No model requests. IDs are definition ordinals, independent of generated UUIDs.
"""

import csv
import hashlib
import inspect
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

root = Path(sys.argv[1]).resolve()
destination = Path(sys.argv[2]).resolve()
sys.path.insert(0, str(root))

from examples.scenarios import SCENARIOS
from manager_agent_gym.core.communication.service import CommunicationService
from manager_agent_gym.core.evaluation.common_evaluators import build_default_evaluators
from manager_agent_gym.core.evaluation.scenario_constraints import build_constraints_for_scenario
from manager_agent_gym.schemas.preferences.rubric import RunCondition


rows = []
for scenario, spec in SCENARIOS.items():
    owners = [
        ("preference", preference.name, preference.weight, preference.evaluator)
        for preference in spec.create_preferences().preferences
        if preference.evaluator is not None
    ]
    evaluators = build_default_evaluators(CommunicationService())
    if spec.create_evaluator_to_measure_goal_achievement:
        evaluators.append(spec.create_evaluator_to_measure_goal_achievement())
    constraints = build_constraints_for_scenario(scenario)
    if constraints:
        evaluators.append(constraints)
    owners.extend(("diagnostic", evaluator.name, None, evaluator) for evaluator in evaluators)
    for owner_index, (kind, owner_name, initial_weight, evaluator) in enumerate(owners):
        for index, rubric in enumerate(evaluator.rubrics):
            function = rubric.evaluator_function
            source_path = inspect.getsourcefile(function) if function else None
            source_line = inspect.getsourcelines(function)[1] if source_path else None
            definition = rubric.llm_prompt if function is None else inspect.getsource(function)
            rows.append({
                "id": f"{scenario}/{kind}/{owner_index:02d}/{index:02d}",
                "scenario": scenario,
                "owner_kind": kind,
                "owner_name": owner_name,
                "initial_preference_weight": initial_weight,
                "declared_aggregation": (
                    f"{evaluator.aggregation.__module__}.{evaluator.aggregation.__qualname__}"
                    if callable(evaluator.aggregation)
                    else evaluator.aggregation.value
                ),
                "rubric_name": rubric.name,
                "description": rubric.description,
                "mode": "callable" if function else "llm",
                "max_score": rubric.max_score,
                "run_condition": rubric.run_condition.value,
                "reference_final_selected": kind == "diagnostic" or rubric.run_condition == RunCondition.ON_COMPLETION,
                "required_context": sorted(item.value for item in rubric.required_context),
                "configured_model": rubric.llm_model if function is None else None,
                "callable_name": function.__qualname__ if function else None,
                "source_path": str(Path(source_path).resolve().relative_to(root)) if source_path else None,
                "source_line": source_line,
                "definition_sha256": hashlib.sha256(definition.encode()).hexdigest(),
                "port_disposition": "faithful_definition_native_criterion",
            })

assert len({row["id"] for row in rows}) == len(rows)
assert len({row["scenario"] for row in rows}) == 20
summary = {
    "total_definitions": len(rows),
    "by_owner": dict(Counter(row["owner_kind"] for row in rows)),
    "by_mode": dict(Counter(row["mode"] for row in rows)),
    "by_cadence": dict(Counter(row["run_condition"] for row in rows)),
    "final_selected": sum(row["reference_final_selected"] for row in rows),
    "final_selected_llm": sum(row["reference_final_selected"] and row["mode"] == "llm" for row in rows),
}
assert summary["by_owner"]["preference"] == 540
assert summary["final_selected_llm"] == 876
result = {
    "mag_commit": subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip(),
    "scope": "Registered scenarios, default diagnostics, goal achievement and scenario constraints; reference final selection without forced checkpoints.",
    "summary": summary,
    "rubrics": rows,
}
destination.mkdir(parents=True, exist_ok=True)
(destination / "rubric-inventory.json").write_text(json.dumps(result, indent=2) + "\n")
with (destination / "rubric-inventory.csv").open("w", newline="") as stream:
    writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
    writer.writeheader()
    for row in rows:
        writer.writerow({**row, "required_context": ";".join(row["required_context"])})
print(json.dumps(summary, indent=2))

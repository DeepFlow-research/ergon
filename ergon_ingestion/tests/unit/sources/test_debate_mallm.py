import importlib
import json
from pathlib import Path

import pytest

from ergon_ingestion.models import ImportSource


VALID_RESOURCE_KINDS = {"import", "artifact", "report", "output", "search_cache", "note"}


def test_debate_mallm_importer_preserves_nested_debate_trace_and_reducers(
    tmp_path: Path,
) -> None:
    source_module = _load_source_module()
    source_path = write_debate_mallm_fixture(tmp_path)
    importer = source_module.DebateMallmImporter()

    runs = list(
        importer.iter_runs(
            ImportSource(
                dataset="debate_mallm",
                input_path=source_path,
                batch_id="debate-mallm-unit",
            )
        )
    )

    assert len(runs) == 1
    run = runs[0]
    assert run.source_run_id == "debate-001"
    assert run.instance_key == "task-001"
    assert run.schema_fit_class == "full-trace"
    assert run.observed_fields["debate_id"] == "debate-001"
    assert run.observed_fields["task_id"] == "task-001"
    assert run.observed_fields["question"] == "Which city is the capital of France?"
    assert run.observed_fields["final_answer"] == "Paris"
    assert run.observed_fields["votes"] == {"agent_a": "Paris", "agent_b": "Paris"}
    assert run.observed_fields["judge_score"] == 1.0
    assert run.observed_fields["correct"] is True
    assert "private_prompts" in run.missing_fields
    assert "model_configs" in run.missing_fields
    assert "judge_rubric" in run.missing_fields

    assert [event.event_type for event in run.events] == [
        "round.start",
        "agent_turn",
        "agent_message",
        "agent_turn",
        "agent_message",
        "round.start",
        "agent_turn",
        "agent_message",
        "final_answer",
        "judge_vote",
    ]
    assert run.events[1].payload == {
        "round": 1,
        "agent": "agent_a",
        "content": "I think the answer is Paris.",
        "turn_index": 0,
    }
    assert run.events[2].payload == {
        "round": 1,
        "agent": "agent_a",
        "role": "assistant",
        "content": "I think the answer is Paris.",
        "turn_index": 0,
        "message_index": 0,
    }
    assert run.events[9].payload == {
        "votes": {"agent_a": "Paris", "agent_b": "Paris"},
        "judge": {"name": "majority_vote"},
        "judge_score": 1.0,
        "correct": True,
    }

    resources = {resource.name: resource for resource in run.resources}
    assert {resource.kind for resource in run.resources} <= VALID_RESOURCE_KINDS
    assert resources["source-record.json"].kind == "import"
    assert resources["rounds.json"].payload["rounds"][0]["agent_turns"][0]["agent"] == "agent_a"
    assert resources["messages.json"].payload["messages"][1]["agent"] == "agent_b"
    assert resources["final-answer.txt"].kind == "output"
    assert resources["final-answer.txt"].payload == "Paris"
    assert resources["judgement.json"].kind == "report"
    assert resources["judgement.json"].payload == {
        "votes": {"agent_a": "Paris", "agent_b": "Paris"},
        "judge": {"name": "majority_vote"},
        "judge_score": 1.0,
        "correct": True,
    }

    reducers = {reducer.name: reducer for reducer in run.reducers}
    assert set(reducers) == {
        "debate_mallm.final_answer",
        "debate_mallm.deliberation_trace",
    }
    assert reducers["debate_mallm.final_answer"].fields_read == [
        "final_answer",
        "votes",
        "judge",
        "judge_score",
        "correct",
    ]
    assert reducers["debate_mallm.final_answer"].output == {
        "final_answer": "Paris",
        "votes": {"agent_a": "Paris", "agent_b": "Paris"},
        "judge": {"name": "majority_vote"},
        "judge_score": 1.0,
        "correct": True,
    }
    assert reducers["debate_mallm.deliberation_trace"].fields_read == [
        "rounds",
        "agent_turns",
        "messages",
        "final_answer",
        "votes",
        "judge_score",
        "correct",
    ]
    assert reducers["debate_mallm.deliberation_trace"].output == {
        "round_count": 2,
        "agent_turn_count": 3,
        "message_count": 3,
        "agents": ["agent_a", "agent_b"],
        "rounds": [
            {"round": 1, "agent_count": 2, "message_count": 2},
            {"round": 2, "agent_count": 1, "message_count": 1},
        ],
        "final_answer": "Paris",
        "votes": {"agent_a": "Paris", "agent_b": "Paris"},
        "judge_score": 1.0,
        "correct": True,
    }

    caveats = {
        (drop.reason, drop.dropped_field_path) for reducer in run.reducers for drop in reducer.drops
    }
    assert ("missing_private_prompts", "private_prompts") in caveats
    assert ("missing_model_configs", "model_configs") in caveats
    assert ("missing_judge_rubric", "judge_rubric") in caveats


def test_debate_mallm_reducers_read_answer_votes_judge_and_trace_fields() -> None:
    reducers_module = _load_reducers_module()
    record = debate_mallm_records()[0]

    final_answer = reducers_module.final_answer_reducer(record)
    trace = reducers_module.deliberation_trace_reducer(record)

    assert final_answer.name == "debate_mallm.final_answer"
    assert final_answer.fields_read == [
        "final_answer",
        "votes",
        "judge",
        "judge_score",
        "correct",
    ]
    assert final_answer.output["final_answer"] == "Paris"
    assert final_answer.output["votes"] == {"agent_a": "Paris", "agent_b": "Paris"}
    assert final_answer.output["judge_score"] == 1.0
    assert final_answer.output["correct"] is True

    assert trace.name == "debate_mallm.deliberation_trace"
    assert trace.fields_read == [
        "rounds",
        "agent_turns",
        "messages",
        "final_answer",
        "votes",
        "judge_score",
        "correct",
    ]
    assert trace.output["round_count"] == 2
    assert trace.output["agent_turn_count"] == 3
    assert trace.output["message_count"] == 3
    assert trace.output["agents"] == ["agent_a", "agent_b"]

    caveats = {
        (drop.reason, drop.dropped_field_path)
        for reducer in [final_answer, trace]
        for drop in reducer.drops
    }
    assert ("missing_private_prompts", "private_prompts") in caveats
    assert ("missing_model_configs", "model_configs") in caveats
    assert ("missing_judge_rubric", "judge_rubric") in caveats


def write_debate_mallm_fixture(tmp_path: Path) -> Path:
    source_path = tmp_path / "debate_mallm.json"
    source_path.write_text(json.dumps(debate_mallm_records()))
    return source_path


def debate_mallm_records() -> list[dict]:
    return [
        {
            "debate_id": "debate-001",
            "task_id": "task-001",
            "question": "Which city is the capital of France?",
            "rounds": [
                {
                    "round": 1,
                    "agent_turns": [
                        {
                            "agent": "agent_a",
                            "content": "I think the answer is Paris.",
                            "messages": [
                                {
                                    "role": "assistant",
                                    "content": "I think the answer is Paris.",
                                }
                            ],
                        },
                        {
                            "agent": "agent_b",
                            "content": "Agreed; Paris is the capital.",
                            "messages": [
                                {
                                    "role": "assistant",
                                    "content": "Agreed; Paris is the capital.",
                                }
                            ],
                        },
                    ],
                },
                {
                    "round": 2,
                    "agent_turns": [
                        {
                            "agent": "agent_a",
                            "content": "No correction needed.",
                            "messages": [{"role": "assistant", "content": "No correction needed."}],
                        }
                    ],
                },
            ],
            "final_answer": "Paris",
            "votes": {"agent_a": "Paris", "agent_b": "Paris"},
            "judge": {"name": "majority_vote"},
            "judge_score": 1.0,
            "correct": True,
        }
    ]


def _load_source_module():
    try:
        return importlib.import_module("ergon_ingestion.sources.debate_mallm")
    except ModuleNotFoundError as exc:
        pytest.fail(f"DEBATE/MALLM source parser is not implemented: {exc}")


def _load_reducers_module():
    try:
        return importlib.import_module("ergon_ingestion.reducers.debate_mallm")
    except ModuleNotFoundError as exc:
        pytest.fail(f"DEBATE/MALLM reducers are not implemented: {exc}")

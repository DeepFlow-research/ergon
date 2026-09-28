"""Work-role prompts follow upstream MAG's AIAgent and HumanAgent wording."""

from ergon_builtins.benchmarks.manager_gym.outputs import HumanWorkOutput
from ergon_builtins.benchmarks.manager_gym.state import EpisodeConfig, all_tasks, new_episode
from ergon_builtins.benchmarks.manager_gym.upstream import (
    NO_RESOURCES_MESSAGE,
    HumanAgentConfig,
    Resource,
)
from ergon_builtins.benchmarks.manager_gym.workers import (
    HumanDraws,
    format_input_resources,
    human_execution_notes,
    human_task_prompt,
)


def _human_and_task():
    state = new_episode(EpisodeConfig(scenario="legal_litigation_ediscovery"))
    human = next(a for a in state.actors.values() if isinstance(a, HumanAgentConfig))
    planned = next(t for t in all_tasks(state.workflow).values() if not t.subtasks)
    return human, planned


def _draws(quality: float, *, misunderstood: bool = False) -> HumanDraws:
    return HumanDraws(fatigue=0.1, quality=quality, speed=1.0, misunderstood=misunderstood)


def test_input_resources_use_upstream_listing_and_preview():
    long = Resource(name="Brief", description="Case brief", content="x" * 250)
    short = Resource(name="Memo", description="Short memo", content="hello")
    assert format_input_resources([long, short], empty=NO_RESOURCES_MESSAGE) == (
        f"- Brief: Case brief\n  Content: {'x' * 200}...\n- Memo: Short memo\n  Content: hello"
    )
    assert format_input_resources([], empty=NO_RESOURCES_MESSAGE) == "No input resources provided"


def test_human_prompt_reflects_quality_draw():
    human, planned = _human_and_task()
    tired = human_task_prompt(planned, human, _draws(0.5), [])
    sharp = human_task_prompt(planned, human, _draws(0.95), [])
    neutral = human_task_prompt(planned, human, _draws(0.8), [])
    assert "feeling a bit tired/stressed today)" in tired
    assert "feeling sharp and focused today)" in sharp
    assert "(Note:" not in neutral
    assert f"Apply your {human.work_style} work style" in neutral
    assert "No specific resources provided" in neutral


def test_misunderstanding_uses_upstreams_separate_prompt():
    human, planned = _human_and_task()
    prompt = human_task_prompt(planned, human, _draws(0.95, misunderstood=True), [])
    assert "Important twist: You slightly misunderstand the task" in prompt
    assert "(Note:" not in prompt and "work style and" not in prompt


def test_human_execution_notes_match_upstream():
    human, _ = _human_and_task()
    output = HumanWorkOutput(
        reasoning="r",
        resources=[],
        work_process="p",
        challenges_encountered=["Waited on counsel"],
        quality_notes="q",
        confidence_level="high",
    )
    assert human_execution_notes(human, _draws(0.8), output) == [
        f"Human worker: {human.name}",
        f"Work style: {human.work_style}",
        f"Experience: {human.experience_years} years",
        "Current fatigue level: 0.10",
        "Quality modifier applied: 0.80",
        "Waited on counsel",
    ]
    misunderstood = human_execution_notes(human, _draws(0.8, misunderstood=True), output)
    assert misunderstood[0] == "Task execution under a subtle misunderstanding of requirements"

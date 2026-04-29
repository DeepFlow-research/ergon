from ergon_core.core.rl.rewards import IndependentTaskReward, SharedEpisodeReward


def test_independent_task_reward_uses_execution_ids_directly() -> None:
    reward = IndependentTaskReward().assign(
        "worker-a",
        {"execution-a": 0.25, "execution-b": 1.0},
        execution_ids={"execution-b"},
    )

    assert reward == 1.0


def test_shared_episode_reward_ignores_execution_membership() -> None:
    reward = SharedEpisodeReward().assign(
        "worker-a",
        {"execution-a": 0.25, "execution-b": 1.0},
        execution_ids={"execution-a"},
    )

    assert reward == 0.625

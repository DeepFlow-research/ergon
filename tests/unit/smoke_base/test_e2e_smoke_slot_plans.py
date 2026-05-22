from tests.e2e import (
    test_minif2f_smoke,
    test_researchrubrics_smoke,
    test_swebench_smoke,
)


def test_default_smoke_slot_plans_submit_three_runs_per_benchmark() -> None:
    assert [slot[0] for slot in test_researchrubrics_smoke._smoke_slots(1)] == [
        "happy",
        "happy",
        "sad",
    ]
    assert [slot[0] for slot in test_minif2f_smoke._smoke_slots(1)] == [
        "happy",
        "happy",
        "sad",
    ]
    assert [slot[0] for slot in test_swebench_smoke._smoke_slots(1)] == [
        "happy",
        "happy",
        "sad",
    ]


def test_smoke_group_size_repeats_three_run_experiments() -> None:
    assert [slot[0] for slot in test_minif2f_smoke._smoke_slots(2)] == [
        "happy",
        "happy",
        "sad",
        "happy",
        "happy",
        "sad",
    ]

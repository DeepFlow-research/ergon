from collections.abc import Sequence

import pytest

from ergon_cli.main import build_parser


@pytest.mark.parametrize(
    ("argv", "expected"),
    [
        (["benchmark", "list"], {"command": "benchmark", "bench_action": "list"}),
        (
            ["experiment", "show", "00000000-0000-0000-0000-000000000000"],
            {"command": "experiment", "experiment_action": "show"},
        ),
        (["run", "list", "--limit", "3"], {"command": "run", "run_action": "list"}),
        (["ingest", "list"], {"command": "ingest", "ingest_action": "list"}),
        (["worker", "list"], {"command": "worker", "worker_action": "list"}),
        (
            [
                "workflow",
                "--run-id",
                "00000000-0000-0000-0000-000000000000",
                "--task-id",
                "00000000-0000-0000-0000-000000000001",
                "--execution-id",
                "00000000-0000-0000-0000-000000000002",
                "--sandbox-task-key",
                "00000000-0000-0000-0000-000000000003",
                "inspect",
                "task-tree",
            ],
            {"command": "workflow", "workflow_args": ["inspect", "task-tree"]},
        ),
        (["evaluator", "list"], {"command": "evaluator", "evaluator_action": "list"}),
        (
            [
                "eval",
                "checkpoint",
                "--checkpoint",
                "ckpt",
                "--benchmark",
                "bench",
                "--evaluator",
                "eval",
                "--model-base",
                "model",
            ],
            {"command": "eval", "eval_action": "checkpoint"},
        ),
        (["onboard"], {"command": "onboard"}),
        (["doctor"], {"command": "doctor"}),
        (["start"], {"command": "start"}),
        (["stop"], {"command": "stop"}),
        (
            ["train", "local", "--benchmark", "bench"],
            {"command": "train", "train_action": "local"},
        ),
    ],
)
def test_domain_parsers_register_representative_commands(
    argv: Sequence[str],
    expected: dict[str, object],
) -> None:
    args = build_parser().parse_args(list(argv))

    assert callable(args.handler)
    for key, value in expected.items():
        assert getattr(args, key) == value

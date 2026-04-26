import pytest

from ergon_cli.main import build_parser


@pytest.mark.parametrize("action", ["watch", "checkpoint"])
def test_eval_commands_require_evaluator_and_model_base(action: str) -> None:
    parser = build_parser()
    args = ["eval", action]
    if action == "watch":
        args.extend(["--checkpoint-dir", "/tmp/checkpoints", "--benchmark", "minif2f"])
    else:
        args.extend(["--checkpoint", "/tmp/checkpoints/checkpoint-1", "--benchmark", "minif2f"])

    with pytest.raises(SystemExit) as exc_info:
        parser.parse_args(args)

    assert exc_info.value.code == 2

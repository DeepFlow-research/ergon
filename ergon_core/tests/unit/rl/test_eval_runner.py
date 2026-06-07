import asyncio

from ergon_core.core.rl.eval_runner import (
    LOCAL_EVAL_UNSUPPORTED_EXIT_CODE,
    evaluate_checkpoint,
)


def test_checkpoint_eval_does_not_submit_experiments_through_cli() -> None:
    exit_code = asyncio.run(
        evaluate_checkpoint(
            checkpoint_path="/tmp/checkpoint-1",
            benchmark_type="gdpeval",
            evaluator_type="stub-rubric",
            model_base="base-model",
            eval_limit=1,
        )
    )

    assert exit_code == LOCAL_EVAL_UNSUPPORTED_EXIT_CODE

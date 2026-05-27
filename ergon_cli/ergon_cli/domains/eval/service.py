from ergon_cli.domains.eval.models import EvalCommand
from ergon_cli.shared.errors import CliUsageError
from ergon_core.core.rl.eval_runner import evaluate_checkpoint, watch_and_evaluate


async def run_eval(command: EvalCommand) -> int:
    if command.action == "watch":
        if command.checkpoint_dir is None:
            raise CliUsageError("Usage: ergon eval watch --checkpoint-dir <path>")
        await watch_and_evaluate(
            checkpoint_dir=command.checkpoint_dir,
            benchmark_type=command.benchmark,
            evaluator_type=command.evaluator,
            model_base=command.model_base,
            poll_interval_s=command.poll_interval,
            eval_limit=command.eval_limit,
            on_checkpoint_cmd=command.on_checkpoint,
        )
        return 0

    if command.checkpoint is None:
        raise CliUsageError("Usage: ergon eval checkpoint --checkpoint <path>")
    return await evaluate_checkpoint(
        checkpoint_path=command.checkpoint,
        benchmark_type=command.benchmark,
        evaluator_type=command.evaluator,
        model_base=command.model_base,
        eval_limit=command.eval_limit,
    )

"""Eval subcommand: watch checkpoints and score them on benchmarks."""

from argparse import Namespace

from ergon_core.core.rl.eval_runner import evaluate_checkpoint, watch_and_evaluate


async def handle_eval(args: Namespace) -> int:
    if args.eval_action == "watch":
        return await _watch(args)
    elif args.eval_action == "checkpoint":
        return await _checkpoint(args)
    else:
        print("Usage: ergon eval {watch|checkpoint}")
        return 1


async def _watch(args: Namespace) -> int:
    try:
        await watch_and_evaluate(
            checkpoint_dir=args.checkpoint_dir,
            benchmark_type=args.benchmark,
            evaluator_type=args.evaluator or "stub-rubric",
            model_base=args.model_base,
            poll_interval_s=args.poll_interval,
            eval_limit=args.eval_limit,
            on_checkpoint_cmd=args.on_checkpoint,
        )
    except KeyboardInterrupt:
        print("\nEval watcher stopped.")
    return 0


async def _checkpoint(args: Namespace) -> int:
    await evaluate_checkpoint(
        checkpoint_path=args.checkpoint,
        benchmark_type=args.benchmark,
        evaluator_type=args.evaluator or "stub-rubric",
        model_base=args.model_base,
        eval_limit=args.eval_limit,
    )
    return 0

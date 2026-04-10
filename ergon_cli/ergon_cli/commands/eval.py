"""Eval subcommand: watch checkpoints and score them on benchmarks."""

import asyncio
from argparse import Namespace

from h_arcane.core.rl.eval_runner import evaluate_checkpoint, watch_and_evaluate


def handle_eval(args: Namespace) -> int:
    if args.eval_action == "watch":
        return _watch(args)
    elif args.eval_action == "checkpoint":
        return _checkpoint(args)
    else:
        print("Usage: arcane eval {watch|checkpoint}")
        return 1


def _watch(args: Namespace) -> int:
    try:
        asyncio.run(
            watch_and_evaluate(
                checkpoint_dir=args.checkpoint_dir,
                benchmark_type=args.benchmark,
                evaluator_type=args.evaluator or "stub-rubric",
                model_base=args.model_base,
                poll_interval_s=args.poll_interval,
                eval_limit=args.eval_limit,
                on_checkpoint_cmd=args.on_checkpoint,
            )
        )
    except KeyboardInterrupt:
        print("\nEval watcher stopped.")
    return 0


def _checkpoint(args: Namespace) -> int:
    evaluate_checkpoint(
        checkpoint_path=args.checkpoint,
        benchmark_type=args.benchmark,
        evaluator_type=args.evaluator or "stub-rubric",
        model_base=args.model_base,
        eval_limit=args.eval_limit,
    )
    return 0

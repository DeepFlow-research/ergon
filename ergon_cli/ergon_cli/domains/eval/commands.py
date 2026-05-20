"""Eval subcommand: watch checkpoints and score them on benchmarks."""

from argparse import Namespace

from ergon_cli.domains.eval.models import EvalCommand
from ergon_cli.domains.eval.service import run_eval
from ergon_cli.shared import exit_codes
from ergon_cli.shared.errors import CliUsageError


async def handle_eval(args: Namespace) -> int:
    if args.eval_action not in {"watch", "checkpoint"}:
        print("Usage: ergon eval {watch|checkpoint}")
        return exit_codes.RUNTIME_ERROR
    values = vars(args)
    command = EvalCommand(
        action=args.eval_action,
        checkpoint_dir=values.get("checkpoint_dir"),
        checkpoint=values.get("checkpoint"),
        benchmark=args.benchmark,
        evaluator=args.evaluator,
        model_base=args.model_base,
        poll_interval=values.get("poll_interval", 60),
        eval_limit=args.eval_limit,
        on_checkpoint=values.get("on_checkpoint"),
    )
    try:
        return await run_eval(command)
    except CliUsageError as exc:
        print(exc.message)
        return exc.exit_code
    except KeyboardInterrupt:
        print("\nEval watcher stopped.")
        return exit_codes.OK

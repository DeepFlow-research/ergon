import argparse

from ergon_cli.commands.eval import handle_eval


def register_eval_parser(subparsers: argparse._SubParsersAction) -> None:
    eval_cmd = subparsers.add_parser("eval", help="Checkpoint evaluation and training curves")
    eval_cmd.set_defaults(handler=handle_eval)
    eval_sub = eval_cmd.add_subparsers(dest="eval_action")

    eval_watch = eval_sub.add_parser("watch", help="Watch for new checkpoints and evaluate")
    eval_watch.add_argument("--checkpoint-dir", required=True, help="Directory to watch")
    eval_watch.add_argument("--benchmark", required=True, help="Benchmark slug")
    eval_watch.add_argument("--evaluator", required=True, help="Evaluator slug")
    eval_watch.add_argument("--model-base", required=True, help="Base model for local eval")
    eval_watch.add_argument("--poll-interval", type=int, default=60, help="Seconds between scans")
    eval_watch.add_argument("--eval-limit", type=int, default=None, help="Max tasks per eval")
    eval_watch.add_argument(
        "--on-checkpoint",
        default=None,
        help="Shell command per checkpoint ({path} and {step} are replaced)",
    )

    eval_ckpt = eval_sub.add_parser("checkpoint", help="Evaluate a single checkpoint")
    eval_ckpt.add_argument("--checkpoint", required=True, help="Checkpoint path")
    eval_ckpt.add_argument("--benchmark", required=True, help="Benchmark slug")
    eval_ckpt.add_argument("--evaluator", required=True, help="Evaluator slug")
    eval_ckpt.add_argument("--model-base", required=True, help="Base model for local eval")
    eval_ckpt.add_argument("--eval-limit", type=int, default=None, help="Max tasks")

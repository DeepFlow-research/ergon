"""Ergon CLI entry point."""

import argparse
import asyncio
import sys

from ergon_cli.commands.benchmark import handle_benchmark
from ergon_cli.commands.doctor import handle_doctor
from ergon_cli.commands.eval import handle_eval
from ergon_cli.commands.evaluator import handle_evaluator
from ergon_cli.commands.experiment import handle_experiment
from ergon_cli.commands.onboard import handle_onboard
from ergon_cli.commands.run import handle_run
from ergon_cli.commands.train import handle_train
from ergon_cli.commands.worker import handle_worker
from ergon_cli.commands.workflow import handle_workflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="ergon", description="Ergon experiment orchestration")
    sub = parser.add_subparsers(dest="command")

    bench = sub.add_parser("benchmark", help="Benchmark operations")
    bench_sub = bench.add_subparsers(dest="bench_action")
    bench_sub.add_parser("list", help="List available benchmarks")
    setup_parser = bench_sub.add_parser(
        "setup", help="Build and register the E2B sandbox template for a benchmark"
    )
    setup_parser.add_argument("slug", help="Benchmark slug (e.g., 'minif2f')")
    setup_parser.add_argument(
        "--force", action="store_true", help="Rebuild even if the template already exists"
    )

    experiment = sub.add_parser("experiment", help="Experiment lifecycle")
    experiment_sub = experiment.add_subparsers(dest="experiment_action")
    experiment_define = experiment_sub.add_parser("define", help="Define an experiment")
    experiment_define.add_argument("benchmark_slug", help="Benchmark slug")
    sample_group = experiment_define.add_mutually_exclusive_group(required=True)
    sample_group.add_argument("--limit", type=int, default=None, help="Number of samples")
    sample_group.add_argument(
        "--sample-id",
        action="append",
        default=None,
        help="Specific benchmark sample id; can be repeated",
    )
    experiment_define.add_argument("--name", default=None, help="Experiment name")
    experiment_define.add_argument("--cohort", default=None, help="Optional cohort/project folder")
    experiment_define.add_argument("--worker", required=True, help="Primary worker slug")
    experiment_define.add_argument("--model", required=True, help="Primary model target")
    experiment_define.add_argument("--evaluator", default=None, help="Optional evaluator slug")
    experiment_define.add_argument("--workflow", default="single", help="Workflow variant")
    experiment_define.add_argument(
        "--max-questions",
        type=int,
        default=10,
        help="Max questions workers can ask",
    )
    experiment_run = experiment_sub.add_parser("run", help="Run a defined experiment")
    experiment_run.add_argument("experiment_id", help="Experiment UUID")
    experiment_run.add_argument("--timeout", type=int, default=600, help="Timeout seconds")
    experiment_run.add_argument(
        "--no-wait",
        action="store_true",
        help="Do not wait for terminal runs",
    )
    experiment_show = experiment_sub.add_parser("show", help="Show experiment detail")
    experiment_show.add_argument("experiment_id", help="Experiment UUID")
    experiment_list = experiment_sub.add_parser("list", help="List experiments")
    experiment_list.add_argument("--limit", type=int, default=50, help="Number of experiments")

    run = sub.add_parser("run", help="Run management")
    run_sub = run.add_subparsers(dest="run_action")
    run_list_parser = run_sub.add_parser("list", help="List recent runs")
    run_list_parser.add_argument("--limit", type=int, default=20, help="Number of runs to show")
    run_list_parser.add_argument(
        "--status",
        default=None,
        help="Filter by status (pending, executing, completed, failed, cancelled)",
    )
    run_cancel_parser = run_sub.add_parser("cancel", help="Cancel a running experiment")
    run_cancel_parser.add_argument("run_id", help="Run ID (UUID) to cancel")

    worker = sub.add_parser("worker", help="Worker operations")
    worker_sub = worker.add_subparsers(dest="worker_action")
    worker_sub.add_parser("list", help="List available workers")

    workflow = sub.add_parser("workflow", help="Workflow topology and resource operations")
    workflow.add_argument("--run-id", default=None, help="Current run UUID")
    workflow.add_argument("--node-id", default=None, help="Current graph node UUID")
    workflow.add_argument("--execution-id", default=None, help="Current task execution UUID")
    workflow.add_argument("--sandbox-task-key", default=None, help="Sandbox task key UUID")
    workflow.add_argument(
        "--benchmark-type", default="default", help="Benchmark/sandbox manager slug"
    )
    workflow.add_argument("workflow_args", nargs=argparse.REMAINDER)

    evaluator = sub.add_parser("evaluator", help="Evaluator operations")
    evaluator_sub = evaluator.add_subparsers(dest="evaluator_action")
    evaluator_sub.add_parser("list", help="List available evaluators")

    # -- eval (checkpoint watcher) ------------------------------------------
    eval_cmd = sub.add_parser("eval", help="Checkpoint evaluation and training curves")
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

    # -- onboard / doctor ------------------------------------------------------
    sub.add_parser("onboard", help="Interactive environment setup wizard")
    doctor = sub.add_parser("doctor", help="Check environment health")
    doctor.add_argument("--verbose", action="store_true", help="Show detailed output")

    # -- train (RL training) --------------------------------------------------
    train_cmd = sub.add_parser("train", help="RL training with Ergon environments")
    train_sub = train_cmd.add_subparsers(dest="train_action")

    train_local = train_sub.add_parser("local", help="Run training on current hardware")
    train_local.add_argument(
        "--ergon-url",
        default="http://localhost:9000/api",
        help="Ergon API URL (default: http://localhost:9000/api)",
    )
    train_local.add_argument("--benchmark", required=True, help="Benchmark slug")
    train_local.add_argument("--evaluator", default="stub-rubric", help="Evaluator slug")
    train_local.add_argument("--limit", type=int, default=None, help="Max tasks per episode")
    train_local.add_argument("--definition-id", default=None, help="ExperimentDefinition UUID")
    train_local.add_argument("--model", default="Qwen/Qwen2.5-1.5B", help="HuggingFace model ID")
    train_local.add_argument(
        "--device", default="cuda", choices=["cpu", "cuda"], help="Device type"
    )
    train_local.add_argument(
        "--vllm-mode",
        default="server",
        choices=["colocate", "server"],
        help="vLLM mode: 'server' (default, required for remote env plane) or 'colocate' (in-process)",
    )
    train_local.add_argument(
        "--vllm-server-url", default=None, help="vLLM server URL (server mode)"
    )
    train_local.add_argument(
        "--vllm-max-model-length", type=int, default=4096, help="Max sequence length for vLLM"
    )
    train_local.add_argument(
        "--vllm-gpu-memory-utilization",
        type=float,
        default=0.3,
        help="Fraction of GPU memory for vLLM KV cache (0.0-1.0)",
    )
    train_local.add_argument(
        "--no-gradient-checkpointing",
        action="store_true",
        help="Disable gradient checkpointing (uses more memory but faster)",
    )
    train_local.add_argument("--num-generations", type=int, default=4, help="GRPO group size")
    train_local.add_argument("--max-completion-length", type=int, default=2048)
    train_local.add_argument("--learning-rate", type=float, default=1e-5)
    train_local.add_argument("--per-device-batch-size", type=int, default=1)
    train_local.add_argument("--gradient-accumulation-steps", type=int, default=4)
    train_local.add_argument("--num-train-epochs", type=int, default=1)
    train_local.add_argument("--save-steps", type=int, default=50)
    train_local.add_argument("--max-steps", type=int, default=None)
    train_local.add_argument(
        "--output-dir", default=".ergon/training/checkpoints", help="Checkpoint output dir"
    )
    train_local.add_argument(
        "--timeout", type=float, default=300.0, help="Seconds per episode batch"
    )
    train_local.add_argument("--dataset-size", type=int, default=100, help="Synthetic dataset size")

    return parser


async def _main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    async_handlers = {
        "benchmark": handle_benchmark,
        "experiment": handle_experiment,
        "workflow": handle_workflow,
        "eval": handle_eval,
    }
    sync_handlers = {
        "run": handle_run,
        "worker": handle_worker,
        "evaluator": handle_evaluator,
        "train": handle_train,
        "onboard": handle_onboard,
        "doctor": handle_doctor,
    }

    if args.command in async_handlers:
        return await async_handlers[args.command](args)
    if args.command in sync_handlers:
        return sync_handlers[args.command](args)
    else:
        parser.print_help()
        return 0


def main(argv: list[str] | None = None) -> int:
    coroutine = _main(argv)
    return asyncio.run(coroutine)  # slopcop: ignore[no-async-from-sync] -- CLI entrypoint


if __name__ == "__main__":
    sys.exit(main())

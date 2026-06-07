import argparse

from ergon_cli.domains.training.commands import handle_train


def register_train_parser(subparsers: argparse._SubParsersAction) -> None:
    train_cmd = subparsers.add_parser("train", help="RL training with Ergon environments")
    train_cmd.set_defaults(handler=handle_train)
    train_sub = train_cmd.add_subparsers(dest="train_action")

    train_local = train_sub.add_parser("local", help="Run training on current hardware")
    train_local.add_argument(
        "--ergon-url",
        default="http://localhost:9000/api",
        help="Ergon API URL (default: http://localhost:9000/api)",
    )
    train_local.add_argument("--environment", required=True, help="Environment slug")
    train_local.add_argument("--evaluator", default="stub-rubric", help="Evaluator slug")
    train_local.add_argument("--limit", type=int, default=None, help="Max tasks per episode")
    train_local.add_argument("--experiment-id", default=None, help="Experiment UUID")
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

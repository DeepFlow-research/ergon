"""TrainingConfig: Pydantic model carrying all training parameters.

Used by both ``ergon train local`` and ``ergon train launch``.
Also usable directly from notebooks or CI scripts.
"""

import argparse

from pydantic import BaseModel, ConfigDict, Field


class TrainingConfig(BaseModel):
    """Framework-agnostic training configuration."""

    model_config = ConfigDict(frozen=True)

    # -- Ergon ----------------------------------------------------------------
    benchmark: str
    evaluator: str = "stub-rubric"
    limit: int | None = None
    definition_id: str | None = None

    # -- Model ----------------------------------------------------------------
    model: str = "Qwen/Qwen2.5-1.5B"

    # -- Device ---------------------------------------------------------------
    device: str = "cuda"
    # "server" is correct for Ergon: MacBook workers need an HTTP endpoint
    # to call vLLM for generation. "colocate" runs vLLM in-process (no HTTP
    # server), which is unreachable from the environment plane.
    vllm_mode: str | None = "server"
    vllm_server_url: str | None = None
    vllm_max_model_length: int = 4096
    vllm_gpu_memory_utilization: float = 0.3
    gradient_checkpointing: bool = True

    # -- GRPO -----------------------------------------------------------------
    num_generations: int = 4
    max_completion_length: int = 2048
    learning_rate: float = 1e-5
    per_device_batch_size: int = 1
    gradient_accumulation_steps: int = 4
    num_train_epochs: int = 1
    save_steps: int = 50
    max_steps: int | None = None

    # -- Output ---------------------------------------------------------------
    output_dir: str = ".ergon/training/checkpoints"

    # -- Rollout ---------------------------------------------------------------
    timeout_s: float = Field(default=300.0, gt=0)

    # -- Dataset --------------------------------------------------------------
    dataset_size: int = Field(default=100, ge=1)


def _build_training_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Ergon training configuration")

    p.add_argument("--benchmark", type=str, required=True, help="Benchmark slug")
    p.add_argument("--evaluator", type=str, default="stub-rubric", help="Evaluator slug")
    p.add_argument("--limit", type=int, default=None, help="Max tasks per episode")
    p.add_argument(
        "--definition-id", type=str, default=None, help="Existing ExperimentDefinition UUID"
    )

    p.add_argument("--model", type=str, default="Qwen/Qwen2.5-1.5B", help="HuggingFace model ID")

    p.add_argument(
        "--device", type=str, default="cuda", choices=["cpu", "cuda"], help="Device type"
    )
    p.add_argument(
        "--vllm-mode",
        type=str,
        default="server",
        choices=["colocate", "server"],
        help="vLLM mode: 'server' (default, required for remote env plane) or 'colocate' (in-process)",
    )
    p.add_argument(
        "--vllm-server-url", type=str, default=None, help="vLLM server URL (server mode)"
    )
    p.add_argument(
        "--vllm-max-model-length", type=int, default=4096, help="Max sequence length for vLLM"
    )
    p.add_argument(
        "--vllm-gpu-memory-utilization",
        type=float,
        default=0.3,
        help="Fraction of GPU memory for vLLM KV cache (0.0-1.0)",
    )
    p.add_argument(
        "--no-gradient-checkpointing",
        action="store_true",
        help="Disable gradient checkpointing (uses more memory but faster)",
    )

    p.add_argument("--num-generations", type=int, default=4, help="GRPO group size")
    p.add_argument("--max-completion-length", type=int, default=2048)
    p.add_argument("--learning-rate", type=float, default=1e-5)
    p.add_argument("--per-device-batch-size", type=int, default=1)
    p.add_argument("--gradient-accumulation-steps", type=int, default=4)
    p.add_argument("--num-train-epochs", type=int, default=1)
    p.add_argument("--save-steps", type=int, default=50)
    p.add_argument("--max-steps", type=int, default=None)

    p.add_argument(
        "--output-dir",
        type=str,
        default=".ergon/training/checkpoints",
        help="Where to write checkpoints (default: .ergon/training/checkpoints)",
    )

    p.add_argument("--timeout", type=float, default=300.0, help="Seconds to wait per episode batch")
    p.add_argument("--dataset-size", type=int, default=100, help="Synthetic dataset size")

    return p


def training_config_from_args(argv: list[str] | None = None) -> TrainingConfig:
    """Parse CLI arguments into a ``TrainingConfig``."""
    args = _build_training_parser().parse_args(argv)

    vllm_mode = None if args.device == "cpu" else args.vllm_mode

    return TrainingConfig(
        benchmark=args.benchmark,
        evaluator=args.evaluator,
        limit=args.limit,
        definition_id=args.definition_id,
        model=args.model,
        device=args.device,
        vllm_mode=vllm_mode,
        vllm_server_url=args.vllm_server_url,
        vllm_max_model_length=args.vllm_max_model_length,
        vllm_gpu_memory_utilization=args.vllm_gpu_memory_utilization,
        gradient_checkpointing=not args.no_gradient_checkpointing,
        num_generations=args.num_generations,
        max_completion_length=args.max_completion_length,
        learning_rate=args.learning_rate,
        per_device_batch_size=args.per_device_batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        num_train_epochs=args.num_train_epochs,
        save_steps=args.save_steps,
        max_steps=args.max_steps,
        output_dir=args.output_dir,
        timeout_s=args.timeout,
        dataset_size=args.dataset_size,
    )

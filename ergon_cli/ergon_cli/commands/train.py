"""Train subcommand: run RL training with Ergon environments."""

import importlib.util
import logging
from argparse import Namespace

logger = logging.getLogger(__name__)


def handle_train(args: Namespace) -> int:
    if importlib.util.find_spec("ergon_infra") is None:
        logger.warning(
            "Training requires additional dependencies.\n"
            "Install with: pip install ergon-cli[training]"
        )
        return 1

    if args.train_action == "local":
        return _train_local(args)
    logger.warning("Usage: ergon train {local}")
    return 1


def _train_local(args: Namespace) -> int:
    # ergon_infra is an optional dependency — these imports must stay after the
    # find_spec guard in handle_train so the module loads even when not installed.
    # reason: optional ergon_infra; imported only when user runs `ergon train local`.
    from ergon_infra.training.config import TrainingConfig

    # reason: (same optional dep as above)
    from ergon_infra.training.trl_runner import run_trl_training

    vllm_mode = None if args.device == "cpu" else args.vllm_mode

    config = TrainingConfig(
        ergon_url=args.ergon_url,
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

    return run_trl_training(config)

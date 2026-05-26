"""Train subcommand: run RL training with Ergon environments."""

import logging
from argparse import Namespace

from ergon_cli.domains.training.models import TrainingCommand
from ergon_cli.domains.training.service import run_training
from ergon_cli.shared.errors import CliUsageError

logger = logging.getLogger(__name__)


def handle_train(args: Namespace) -> int:
    if args.train_action != "local":
        logger.warning("Usage: ergon train {local}")
        return 1
    command = TrainingCommand(
        action=args.train_action,
        ergon_url=args.ergon_url,
        benchmark=args.benchmark,
        evaluator=args.evaluator,
        limit=args.limit,
        experiment_id=args.experiment_id,
        model=args.model,
        device=args.device,
        vllm_mode=None if args.device == "cpu" else args.vllm_mode,
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
        timeout=args.timeout,
        dataset_size=args.dataset_size,
    )
    try:
        return run_training(command)
    except CliUsageError as exc:
        logger.warning(exc.message)
        return exc.exit_code

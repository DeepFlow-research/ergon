import importlib.util
import logging

from ergon_cli.domains.training.models import TrainingCommand
from ergon_cli.shared.errors import CliUsageError

logger = logging.getLogger(__name__)


def run_training(command: TrainingCommand) -> int:
    if importlib.util.find_spec("ergon_infra") is None:
        logger.warning(
            "Training requires additional dependencies.\n"
            "Install with: pip install ergon-cli[training]"
        )
        return 1

    if command.action != "local":
        raise CliUsageError("Usage: ergon train {local}")

    from ergon_infra.training.config import TrainingConfig
    from ergon_infra.training.trl_runner import run_trl_training

    config = TrainingConfig(
        ergon_url=command.ergon_url,
        benchmark=command.benchmark,
        evaluator=command.evaluator,
        limit=command.limit,
        experiment_id=command.experiment_id,
        model=command.model,
        device=command.device,
        vllm_mode=None if command.device == "cpu" else command.vllm_mode,
        vllm_server_url=command.vllm_server_url,
        vllm_max_model_length=command.vllm_max_model_length,
        vllm_gpu_memory_utilization=command.vllm_gpu_memory_utilization,
        gradient_checkpointing=command.gradient_checkpointing,
        num_generations=command.num_generations,
        max_completion_length=command.max_completion_length,
        learning_rate=command.learning_rate,
        per_device_batch_size=command.per_device_batch_size,
        gradient_accumulation_steps=command.gradient_accumulation_steps,
        num_train_epochs=command.num_train_epochs,
        save_steps=command.save_steps,
        max_steps=command.max_steps,
        output_dir=command.output_dir,
        timeout_s=command.timeout,
        dataset_size=command.dataset_size,
    )

    return run_trl_training(config)

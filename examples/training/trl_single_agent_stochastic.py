"""TRL single-agent stochastic SMDP/POMDP baseline.

Formalism:
child rollout = environment transition
parent-visible child result = feedback
reward = sample-level normalized reward
"""

import logging
from typing import cast

from ergon_infra.adapters.trl_http import make_ergon_http_rollout_func
from ergon_infra.training.config import TrainingConfig
from ergon_infra.training.device import resolve_device_mode

logger = logging.getLogger(__name__)


def run_trl_training(config: TrainingConfig) -> int:
    """Run TRL GRPO using projected parent-visible Ergon training records."""
    if not config.ergon_url:
        raise ValueError(
            "--ergon-url is required. Point it at the Ergon API "
            "(e.g. http://localhost:9000/api for local dev)."
        )
    if not config.experiment_id:
        raise ValueError("--experiment-id is required.")

    from datasets import Dataset
    from transformers import AutoTokenizer
    from trl import GRPOConfig, GRPOTrainer

    tokenizer = AutoTokenizer.from_pretrained(config.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    rollout_func = make_ergon_http_rollout_func(
        ergon_url=config.ergon_url,
        experiment_id=config.experiment_id,
        timeout_s=config.timeout_s,
    )

    dataset = Dataset.from_dict(
        {
            "prompt": [[{"role": "user", "content": "Complete the benchmark task."}]]
            * config.dataset_size,
        }
    )

    def reward_fn(completions: list[str], **kwargs: object) -> list[float]:
        rewards = kwargs.get("completion_reward")
        if rewards is None:
            raise RuntimeError("rollout_func did not return completion_reward")
        return cast(list[float], rewards)

    grpo_config = GRPOConfig(
        output_dir=config.output_dir,
        num_generations=config.num_generations,
        max_completion_length=config.max_completion_length,
        learning_rate=config.learning_rate,
        per_device_train_batch_size=config.per_device_batch_size,
        gradient_accumulation_steps=config.gradient_accumulation_steps,
        num_train_epochs=config.num_train_epochs,
        save_steps=config.save_steps,
        max_steps=config.max_steps or -1,
        logging_steps=1,
        report_to="none",
        **resolve_device_mode(config),
    )

    logger.info("Starting TRL stochastic single-agent baseline")
    trainer = GRPOTrainer(
        model=config.model,
        processing_class=tokenizer,
        reward_funcs=[reward_fn],
        train_dataset=dataset,
        args=grpo_config,
        rollout_func=rollout_func,
    )
    trainer.train()
    return 0

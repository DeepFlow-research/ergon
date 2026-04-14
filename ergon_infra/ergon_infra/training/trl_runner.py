"""TRL GRPO training runner.

Takes a ``TrainingConfig`` and runs ``GRPOTrainer.train()``. The rollout
logic is fully delegated to Ergon's HTTP API — this process only does
gradient computation.

Architecture::

    GPU Node (this process)              Ergon API (MacBook / cloud)
    ───────────────────────              ──────────────────────────
    TRL GRPOTrainer                      POST /rollouts/submit
      → rollout_func() ────HTTP────────►   → Inngest pipeline
      ← trajectories   ◄──HTTP────────    → workers call vLLM
      → forward/backward (GPU)            → eval + score
      → optimizer step                    → extract trajectories
      → repeat                           GET /rollouts/{batch_id}

    Dependencies: trl, httpx             Dependencies: ergon_core, inngest, sqlmodel

The GPU node has ONE network dependency: the Ergon API URL. No Inngest,
no Postgres, no Tailscale for internal services.
"""

import logging
from typing import cast

from datasets import Dataset
from transformers import AutoTokenizer
from trl import GRPOConfig, GRPOTrainer

from ergon_infra.adapters.trl_http import make_ergon_http_rollout_func
from ergon_infra.training.config import TrainingConfig
from ergon_infra.training.device import resolve_device_mode

logger = logging.getLogger(__name__)


def run_trl_training(config: TrainingConfig) -> int:
    """Run TRL GRPO training with Ergon environments via HTTP.

    Returns exit code (0 = success).
    """
    if not config.ergon_url:
        raise ValueError(
            "--ergon-url is required. Point it at the Ergon API "
            "(e.g. http://localhost:9000/api for local dev)."
        )

    definition_id = config.definition_id
    if not definition_id:
        raise ValueError(
            "--definition-id is required. Create one via: ergon benchmark run <slug> --limit 1"
        )

    tokenizer = AutoTokenizer.from_pretrained(config.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    rollout_func = make_ergon_http_rollout_func(
        ergon_url=config.ergon_url,
        definition_id=definition_id,
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
            raise RuntimeError(
                "rollout_func did not return 'completion_reward' — "
                "the Ergon evaluation pipeline may have failed"
            )
        return cast(list[float], rewards)

    device_kwargs = resolve_device_mode(config)

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
        **device_kwargs,
    )

    logger.info("Starting TRL GRPO training")
    logger.info("  Ergon API:     %s", config.ergon_url)
    logger.info("  Model:         %s", config.model)
    logger.info("  Definition:    %s", definition_id)
    logger.info("  Device:        %s", config.device)
    logger.info("  Output dir:    %s", config.output_dir)

    trainer = GRPOTrainer(
        model=config.model,
        processing_class=tokenizer,
        reward_funcs=[reward_fn],
        train_dataset=dataset,
        args=grpo_config,
        rollout_func=rollout_func,
    )

    trainer.train()
    logger.info("Training complete. Checkpoints in %s", config.output_dir)
    return 0

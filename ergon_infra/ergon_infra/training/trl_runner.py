"""TRL GRPO training runner.

Takes a ``TrainingConfig``, resolves all dependencies, and runs
``GRPOTrainer.train()``.  This is the library entry point that both
``arcane train local`` and ``scripts/train_trl_grpo.py`` call.
"""

import logging
from typing import cast
from uuid import UUID

from datasets import Dataset
from transformers import AutoTokenizer
from trl import GRPOConfig, GRPOTrainer

from arcane_infra.training.callback import ArcaneTrainingCallback
from arcane_infra.training.config import TrainingConfig
from arcane_infra.training.device import resolve_device_mode
from h_arcane.core.persistence.shared.db import get_session
from h_arcane.core.persistence.telemetry.models import TrainingSession
from h_arcane.core.rl.trl_adapter import make_arcane_rollout_func
from h_arcane.core.runtime.inngest_client import inngest_client
from h_arcane.core.utils import utcnow

logger = logging.getLogger(__name__)


def run_trl_training(config: TrainingConfig) -> int:
    """Run TRL GRPO training with Arcane environments.

    Returns exit code (0 = success).
    Callers are responsible for DB setup (ensure_db).
    """
    definition_id = (
        UUID(config.definition_id) if config.definition_id else _auto_create_definition(config)
    )

    tokenizer = AutoTokenizer.from_pretrained(config.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    rollout_func = make_arcane_rollout_func(
        definition_id=definition_id,
        inngest_send=inngest_client.send_sync,
        session_factory=get_session,
        tokenizer=tokenizer,
        timeout_s=config.timeout_s,
    )

    # TRL requires a train_dataset to iterate over, but with rollout_func
    # the prompts are ignored — Arcane's ExperimentDefinition drives task
    # selection, not the dataset.  This is a dummy iterator that controls
    # how many batches TRL runs (dataset_size / batch_size = num batches).
    dataset = Dataset.from_dict(
        {
            "prompt": [[{"role": "user", "content": "Complete the benchmark task."}]]
            * config.dataset_size,
        }
    )

    def reward_fn(completions: list[str], **kwargs: object) -> list[float]:
        """Passthrough: rewards are computed by Arcane's evaluation pipeline
        during the rollout and returned via the ``completion_reward`` key.
        """
        rewards = kwargs.get("completion_reward")
        if rewards is None:
            raise RuntimeError(
                "rollout_func did not return 'completion_reward' — "
                "the Arcane evaluation pipeline may have failed"
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

    training_session = TrainingSession(
        experiment_definition_id=definition_id,
        model_name=config.model,
        config_json=config.model_dump(mode="json"),
        status="running",
        started_at=utcnow(),
        output_dir=config.output_dir,
    )
    with get_session() as session:
        session.add(training_session)
        session.commit()
        session.refresh(training_session)

    session_id = training_session.id

    logger.info("Starting TRL GRPO training")
    logger.info("  Session:       %s", session_id)
    logger.info("  Model:         %s", config.model)
    logger.info("  Benchmark:     %s", config.benchmark)
    logger.info("  Definition:    %s", definition_id)
    logger.info("  Device:        %s", config.device)
    logger.info("  vLLM mode:     %s", config.vllm_mode)
    logger.info("  Output dir:    %s", config.output_dir)

    trainer = GRPOTrainer(
        model=config.model,
        processing_class=tokenizer,
        reward_funcs=[reward_fn],
        train_dataset=dataset,
        args=grpo_config,
        rollout_func=rollout_func,
        callbacks=[ArcaneTrainingCallback(session_id=session_id, session_factory=get_session)],
    )

    try:
        trainer.train()
        logger.info("Training complete. Checkpoints in %s", config.output_dir)
    except Exception:  # slopcop: ignore[no-broad-except]
        with get_session() as session:
            ts = session.get(TrainingSession, session_id)
            if ts is not None:
                ts.status = "failed"
                ts.completed_at = utcnow()
                session.add(ts)
                session.commit()
        raise

    return 0


def _auto_create_definition(config: TrainingConfig) -> UUID:
    raise ValueError(
        f"Auto-creation of ExperimentDefinition for benchmark '{config.benchmark}' "
        "is not yet implemented.  Pass --definition-id with an existing UUID "
        "(create one via: arcane benchmark run <slug> --limit 1)."
    )

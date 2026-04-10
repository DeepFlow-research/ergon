"""TRL GRPO training runner.

Takes a ``TrainingConfig``, resolves all dependencies, and runs
``GRPOTrainer.train()``.

Control flow (distributed case)::

    Your MacBook                                GPU Node (Shadeform)
    ────────────                                ────────────────────
    ergon train launch                         ergon train local  ← THIS FILE
      → provisions GPU via SkyPilot               → starts vLLM HTTP server (port 8000)
      → creates ExperimentDefinition              → TRL GRPOTrainer (vllm_mode=server)
                                                  → calls rollout_func each step:
    Docker compose (always running):                  fires Inngest event ──→ MacBook
      Postgres, Inngest, API, Dashboard         ←── Inngest pipeline runs:
                                                      worker calls vLLM HTTP on GPU node
                                                      eval runs (LLM judge / sandbox)
                                                      results written to Postgres
                                                    rollout_func polls Postgres ──→ reads results
                                                    TRL computes GRPO gradient (GPU)
                                                    TRL syncs weights to vLLM server

vLLM mode: we use "server" (not "colocate") because the MacBook workers
need an HTTP endpoint to reach vLLM for generation. Colocate runs vLLM
in-process with no HTTP server, making it unreachable from the remote
environment plane. Server mode also avoids GPU memory contention between
the training model and vLLM's KV cache.

NOTE: This control flow is inverted from what you'd expect. The GPU node
drives the training loop (because TRL's rollout_func is an in-process
callback), while the MacBook acts as an environment server. The GPU is
the "master" and the MacBook is the "worker" — the opposite of the
natural mental model where you launch from your laptop and the GPU
does what it's told.

This inversion exists because TRL couples the training loop to the
rollout function in a single process. Alternatives that would allow
a cleaner master-worker split:

  - veRL: Ray-based, separates rollout manager from trainer actor
  - TRL async GRPO (on their roadmap): decouples generation from training
  - Custom proxy: MacBook drives, sends trajectories to GPU via HTTP

For now we accept the inverted model. The GPU node needs network access
to the MacBook's Inngest (for firing events) and Postgres (for reading
results). Tailscale provides this when the MacBook lacks a public IP.

TRL's planned async GRPO replaces the synchronous rollout_func with a
continuous buffer, but this alone does NOT fix the inversion — the buffer
consumer still runs in-process on the GPU node. What would fix it: an
externalised buffer (Redis, Postgres, HTTP endpoint) that the environment
orchestrator writes to and the trainer reads from. Neither side needs to
reach the other's internal services. See the RolloutService protocol
sketch in trl_adapter.py for the concrete API this would require.
"""

import logging
from typing import cast
from uuid import UUID

from datasets import Dataset
from transformers import AutoTokenizer
from trl import GRPOConfig, GRPOTrainer

from ergon_infra.training.callback import ErgonTrainingCallback
from ergon_infra.training.config import TrainingConfig
from ergon_infra.training.device import resolve_device_mode
from ergon_core.core.persistence.shared.db import get_session
from ergon_core.core.persistence.telemetry.models import TrainingSession
from ergon_core.core.rl.trl_adapter import make_ergon_rollout_func
from ergon_core.core.runtime.inngest_client import inngest_client
from ergon_core.core.utils import utcnow

logger = logging.getLogger(__name__)


def run_trl_training(config: TrainingConfig) -> int:
    """Run TRL GRPO training with Ergon environments.

    Returns exit code (0 = success).
    Callers are responsible for DB setup (ensure_db).
    """
    definition_id = (
        UUID(config.definition_id) if config.definition_id else _auto_create_definition(config)
    )

    tokenizer = AutoTokenizer.from_pretrained(config.model)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    rollout_func = make_ergon_rollout_func(
        definition_id=definition_id,
        inngest_send=inngest_client.send_sync,
        session_factory=get_session,
        tokenizer=tokenizer,
        timeout_s=config.timeout_s,
    )

    # TRL requires a train_dataset to iterate over, but with rollout_func
    # the prompts are ignored — Ergon's ExperimentDefinition drives task
    # selection, not the dataset.  This is a dummy iterator that controls
    # how many batches TRL runs (dataset_size / batch_size = num batches).
    dataset = Dataset.from_dict(
        {
            "prompt": [[{"role": "user", "content": "Complete the benchmark task."}]]
            * config.dataset_size,
        }
    )

    def reward_fn(completions: list[str], **kwargs: object) -> list[float]:
        """Passthrough: rewards are computed by Ergon's evaluation pipeline
        during the rollout and returned via the ``completion_reward`` key.
        """
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
        vllm_max_model_length=config.vllm_max_model_length,
        vllm_gpu_memory_utilization=config.vllm_gpu_memory_utilization,
        gradient_checkpointing=config.gradient_checkpointing,
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
        callbacks=[ErgonTrainingCallback(session_id=session_id, session_factory=get_session)],
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
        "(create one via: ergon benchmark run <slug> --limit 1)."
    )

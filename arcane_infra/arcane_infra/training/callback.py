"""TRL training callback that persists metrics to Postgres.

Writes a ``TrainingMetric`` row on each ``on_log`` event and marks
the ``TrainingSession`` as completed/failed on ``on_train_end``.
"""

import logging
from typing import Callable
from uuid import UUID

from sqlmodel import Session
from transformers import TrainerCallback, TrainerControl, TrainerState, TrainingArguments

from h_arcane.core.persistence.telemetry.models import TrainingMetric, TrainingSession
from h_arcane.core.utils import utcnow

logger = logging.getLogger(__name__)

_KNOWN_METRIC_KEYS = frozenset({
    "epoch", "loss", "grad_norm", "learning_rate",
    "reward", "reward_std", "entropy",
    "completions/mean_length", "step_time",
})


class ArcaneTrainingCallback(TrainerCallback):
    """Persists per-step training metrics to the Arcane DB."""

    def __init__(self, session_id: UUID, session_factory: Callable[[], Session]) -> None:
        super().__init__()
        self.session_id = session_id
        self.session_factory = session_factory

    def on_log(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        logs: dict[str, float] | None = None,
        **kwargs: object,
    ) -> None:
        if logs is None:
            return

        try:
            metric = TrainingMetric(
                session_id=self.session_id,
                step=state.global_step,
                epoch=logs.get("epoch"),
                loss=logs.get("loss"),
                grad_norm=logs.get("grad_norm"),
                learning_rate=logs.get("learning_rate"),
                reward_mean=logs.get("reward"),
                reward_std=logs.get("reward_std"),
                entropy=logs.get("entropy"),
                completion_mean_length=logs.get("completions/mean_length"),
                step_time_s=logs.get("step_time"),
                extra_json={
                    k: v for k, v in logs.items() if k not in _KNOWN_METRIC_KEYS
                },
            )

            with self.session_factory() as session:
                session.add(metric)
                session.commit()

            logger.debug("Persisted training metric for step %d", state.global_step)
        except Exception:
            logger.warning(
                "Failed to persist training metric for step %d",
                state.global_step,
                exc_info=True,
            )

    def on_train_end(
        self,
        args: TrainingArguments,
        state: TrainerState,
        control: TrainerControl,
        **kwargs: object,
    ) -> None:
        try:
            with self.session_factory() as session:
                ts = session.get(TrainingSession, self.session_id)
                if ts is not None:
                    ts.status = "completed"
                    ts.completed_at = utcnow()
                    ts.total_steps = state.global_step
                    last_log: dict[str, float] = state.log_history[-1] if state.log_history else {}
                    ts.final_loss = last_log.get("loss")
                    session.add(ts)
                    session.commit()

            logger.info(
                "Training session %s marked completed (steps=%d)",
                self.session_id,
                state.global_step,
            )
        except Exception:
            logger.warning("Failed to mark training session completed", exc_info=True)

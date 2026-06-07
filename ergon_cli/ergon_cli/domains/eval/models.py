from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvalCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["watch", "checkpoint"]
    environment: str
    evaluator: str
    model_base: str
    eval_limit: int | None = None
    checkpoint_dir: str | None = None
    checkpoint: str | None = None
    poll_interval: int = 60
    on_checkpoint: str | None = None

from typing import Literal

from pydantic import BaseModel, ConfigDict


class EvaluatorCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["list"]


class EvaluatorRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str


class EvaluatorListResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    evaluators: tuple[EvaluatorRef, ...]

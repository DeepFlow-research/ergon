from typing import Literal

from pydantic import BaseModel, ConfigDict


class WorkerCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["list"]


class WorkerRef(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    name: str


class WorkerListResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    workers: tuple[WorkerRef, ...]

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict


class StackCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["start", "stop"]
    cwd: Path


class StackResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    exit_code: int
    stdout: tuple[str, ...] = ()
    stderr: tuple[str, ...] = ()

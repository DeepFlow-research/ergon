from typing import Literal

from pydantic import BaseModel, ConfigDict


class EnvironmentCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["list", "setup"]
    slug: str | None = None
    force: bool = False

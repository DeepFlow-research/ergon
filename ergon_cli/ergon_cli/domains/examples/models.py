from typing import Literal

from pydantic import BaseModel, ConfigDict


class ExampleOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    flag: str
    description: str
    default: str | None = None


class ExampleDefinition(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    display_name: str
    short_description: str
    purpose: str
    script_path: str
    prerequisites: tuple[str, ...]
    options: tuple[ExampleOption, ...]


class ExampleCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    action: Literal["list", "info", "check", "run"]
    example: str | None = None
    limit: int | None = None
    base_url: str | None = None
    model: str | None = None
    model_target: str | None = None
    max_iterations: int | None = None

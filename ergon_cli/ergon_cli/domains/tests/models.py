from typing import Literal

from pydantic import BaseModel, ConfigDict

TestSuite = Literal[
    "list",
    "unit",
    "integration",
    "smoke",
    "e2e",
    "full",
    "researchrubrics",
    "minif2f",
    "swebench-verified",
]
TestDomain = Literal[
    "list",
    "smoke",
    "full",
    "core",
    "builtins",
    "cli",
    "ingestion",
    "dashboard",
    "backend",
    "real-llm",
]


class TestCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    suite: TestSuite
    domain: TestDomain = "full"
    dry_run: bool = False
    extra_args: tuple[str, ...] = ()


class ResolvedTestCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    commands: tuple[tuple[str, ...], ...]

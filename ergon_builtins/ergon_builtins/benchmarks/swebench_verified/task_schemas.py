"""Pydantic schemas for SWE-Bench Verified tasks.

The raw dataset row carries both the gold ``patch`` and the ``test_patch``
that defines the test cases. We deliberately drop ``patch`` before it ever
reaches the worker, and we keep ``test_patch`` in the payload for the
evaluator only — ``build_worker_description`` never includes it.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, Field


class SWEBenchInstance(BaseModel):
    """Parsed representation of one SWE-Bench Verified row."""

    instance_id: str
    repo: str
    base_commit: str
    problem_statement: str
    hints_text: str = ""
    version: str
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    environment_setup_commit: str
    test_patch: str

    @classmethod
    def from_raw(cls, row: Mapping[str, Any]) -> "SWEBenchInstance":  # slopcop: ignore[no-typing-any]
        return cls(
            instance_id=row["instance_id"],
            repo=row["repo"],
            base_commit=row["base_commit"],
            problem_statement=row["problem_statement"],
            hints_text=row.get("hints_text") or "",
            version=str(row["version"]),
            fail_to_pass=_parse_test_list(row["FAIL_TO_PASS"]),
            pass_to_pass=_parse_test_list(row["PASS_TO_PASS"]),
            environment_setup_commit=row.get("environment_setup_commit") or row["base_commit"],
            test_patch=row["test_patch"],
        )


class SWEBenchTaskPayload(BaseModel):
    """Payload attached to each ``BenchmarkTask``.

    Includes ``test_patch`` because the evaluator needs it, but
    ``build_worker_description`` omits it so the worker cannot see the
    tests it is supposed to make pass.
    """

    instance_id: str
    repo: str
    base_commit: str
    version: str
    problem_statement: str
    hints_text: str = ""
    fail_to_pass: list[str]
    pass_to_pass: list[str]
    environment_setup_commit: str
    test_patch: str = Field(..., description="Gold test patch; evaluator-only.")

    @classmethod
    def from_instance(cls, instance: SWEBenchInstance) -> "SWEBenchTaskPayload":
        return cls(**instance.model_dump())

    def build_worker_description(self) -> str:
        parts = [
            f"Repository: {self.repo} (commit {self.base_commit[:12]})",
            "",
            "## Problem statement",
            self.problem_statement.strip(),
        ]
        if self.hints_text.strip():
            parts.extend(["", "## Hints", self.hints_text.strip()])
        parts.extend([
            "",
            "## Task",
            "Modify the repository so that the described issue is fixed.",
            "When done, your changes will be extracted as a `git diff HEAD` and",
            "scored against a hidden test suite.",
        ])
        return "\n".join(parts)


def _parse_test_list(value: Any) -> list[str]:  # slopcop: ignore[no-typing-any]
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        parsed = json.loads(value)
        if not isinstance(parsed, list):
            raise TypeError(
                f"FAIL/PASS list JSON must decode to list, got {type(parsed).__name__}"
            )
        return [str(v) for v in parsed]
    raise TypeError(f"Unsupported FAIL/PASS list type: {type(value)!r}")

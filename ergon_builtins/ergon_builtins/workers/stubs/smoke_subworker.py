"""Env-agnostic leaf worker Protocol for canonical smoke runs.

The parent CanonicalSmokeWorker spawns 9 subtasks via add_subtask; each subtask
resolves to a leaf worker via the composition binding `smoke-leaf`. That leaf
worker wraps a SmokeSubworker instance (one concrete class per env) whose sole
job is to prove the sandbox is correctly set up for that environment:

  1. Write a deterministic, well-known file into the sandbox.
  2. Run a bash probe against it (compile / parse / count lines / etc.).
  3. Return both so the criterion can assert on them.

MUST NOT call an LLM. MUST NOT make network calls. MUST complete in under 20s
under normal sandbox conditions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ergon_core.core.providers.sandbox.manager import AsyncSandbox


@dataclass(frozen=True)
class SubworkerResult:
    """Return payload from one SmokeSubworker.work() call."""

    file_path: str
    probe_stdout: str
    probe_exit_code: int


@runtime_checkable
class SmokeSubworker(Protocol):
    """The pluggable env-specific leaf."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult:
        ...

"""Env-agnostic leaf worker Protocol for canonical smoke runs.

The per-env smoke parent worker spawns 9 subtasks via ``plan_subtasks``.
Each subtask resolves to ``{env}-smoke-leaf`` — a ``BaseSmokeLeafWorker``
subclass that binds a concrete ``SmokeSubworker`` via ``subworker_cls``.

The subworker's sole job is to prove the sandbox is correctly set up
for that environment:

  1. Write a deterministic, well-known file into the sandbox under
     ``/workspace/final_output/`` so the runtime's persist step can
     hash it and produce a ``RunResource`` row.
  2. Run a bash probe against it (compile / parse / count lines / etc.)
     and persist the probe result as a second file
     (``probe_<node>.json``) that the criterion later reads.
  3. Return both so the leaf worker can report success/failure.

MUST NOT call an LLM.  MUST NOT make external network calls.  MUST
complete in under 20 seconds under normal sandbox conditions.
"""

from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from ergon_core.core.providers.sandbox.manager import AsyncSandbox


@dataclass(frozen=True)
class SubworkerResult:
    """Return payload from one ``SmokeSubworker.work()`` call.

    Plain value-object with positional construction; used in contract /
    unit tests as fixture returns.  A ``pydantic.BaseModel`` here would
    force kwargs on every test fixture for no semantic benefit.
    """

    file_path: str
    probe_stdout: str
    probe_exit_code: int


@runtime_checkable
class SmokeSubworker(Protocol):
    """The pluggable env-specific leaf.  One implementation per env."""

    async def work(self, node_id: str, sandbox: AsyncSandbox) -> SubworkerResult: ...

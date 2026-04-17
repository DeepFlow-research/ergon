# SWE-Bench Verified Benchmark Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SWE-Bench Verified (500 curated real-world GitHub issue-fix tasks) as an Ergon benchmark, end-to-end: dataset loader, custom E2B sandbox template, generic bash + file-edit worker, and an evaluator that scores by running the official SWE-Bench test harness.

**Architecture:**
- Dataset: `princeton-nlp/SWE-bench_Verified` loaded via `datasets.load_dataset`. Each row becomes one `BenchmarkTask` whose payload carries everything the evaluator needs (`instance_id`, `repo`, `base_commit`, `version`, `problem_statement`, `FAIL_TO_PASS`, `PASS_TO_PASS`, `test_patch`) but the worker's `description` contains ONLY the problem statement — gold `patch` is dropped entirely, `test_patch` is reserved for the evaluator.
- Sandbox: one E2B template (`ergon-swebench-v1`) with git, build toolchain, system libs for all 12 repos, `uv` as Python-version manager, `swebench` pip package, and a `UV_CACHE_DIR` on a writable path. Per-task setup is driven by `swebench.harness.test_spec.make_test_spec(instance).setup_env_script` and `install_repo_script` — we do not reimplement the install matrix.
- Worker: `SWEBenchReActWorker` extends `ReActWorker` and provides two generic tools: bash and str-replace file editor. On completion it runs `git diff HEAD` inside the sandbox and stores the unified diff as the output artifact.
- Evaluator: `SWEBenchRubric` holds a single `SWEBenchTestCriterion` that spawns a fresh sandbox of the same template, checks out `base_commit`, applies `test_patch`, applies the agent's patch, runs `eval_script`, and parses results with `swebench.harness.grading.get_eval_report`.

**Tech Stack:** Python 3.13, pydantic, pydantic_ai (tool use), E2B `AsyncSandbox`, `datasets`, `huggingface_hub`, `swebench>=3.0`, uv (inside container).

---

## File Structure

**New files (created by this plan):**

```
ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/
├── __init__.py
├── benchmark.py                # SweBenchVerifiedBenchmark
├── task_schemas.py             # SWEBenchInstance, SWEBenchTaskPayload
├── toolkit.py                  # SWEBenchToolkit (bash + file edit)
├── sandbox_manager.py          # SWEBenchSandboxManager
├── criterion.py                # SWEBenchTestCriterion
└── sandbox/
    ├── Dockerfile
    └── e2b.toml.template

ergon/ergon_builtins/ergon_builtins/workers/baselines/
└── swebench_worker.py          # SWEBenchReActWorker

ergon/ergon_builtins/ergon_builtins/evaluators/rubrics/
└── swebench_rubric.py          # SWEBenchRubric (+ factory)

ergon/tests/swebench_verified/
├── __init__.py
├── test_benchmark.py           # dataset loader (network-mocked)
├── test_task_schemas.py        # pydantic round-trips, patch stripping
├── test_sandbox_manager.py     # template threading
├── test_toolkit.py             # bash + edit tool semantics, mocked sandbox
├── test_worker.py              # toolkit wiring + patch extraction
├── test_criterion.py           # eval flow on canned outputs (no E2B)
└── test_rubric.py              # aggregation
```

**Modified files:**

- `ergon/ergon_builtins/ergon_builtins/registry_core.py` — add SWE-Bench to `SANDBOX_MANAGERS` and `SANDBOX_TEMPLATES`
- `ergon/ergon_builtins/ergon_builtins/registry_data.py` — add `"swebench-verified"` to `BENCHMARKS`, `"swebench-react"` to `WORKERS`, `"swebench-rubric"` to `EVALUATORS`
- `ergon/ergon_builtins/pyproject.toml` — add `datasets` and `swebench` to `[data]` extra
- `ergon/ergon_cli/ergon_cli/commands/benchmark.py` — register template build path (if not auto-discovered via `SANDBOX_TEMPLATES`)

---

## Task 1: Scaffolding and dependencies

**Files:**
- Modify: `ergon/ergon_builtins/pyproject.toml`
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/__init__.py`
- Create: `ergon/tests/swebench_verified/__init__.py`

- [ ] **Step 1: Add dependencies to `[data]` extra**

Open `ergon/ergon_builtins/pyproject.toml`. Find the `[project.optional-dependencies]` / `data` section and add:

```toml
[project.optional-dependencies]
data = [
    # ...existing entries kept...
    "datasets>=2.20,<4",
    "swebench>=3.0,<4",
]
```

- [ ] **Step 2: Install the extra and verify import**

Run: `uv sync --all-packages --group dev --extra data`
Expected: resolver succeeds, `swebench` and `datasets` are installed.
Verify: `uv run python -c "import swebench.harness.test_spec as t; import datasets; print('ok')"` → prints `ok`.

- [ ] **Step 3: Create empty package and test package**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/__init__.py` with contents:
```python
"""SWE-Bench Verified benchmark package."""
```

Create `ergon/tests/swebench_verified/__init__.py` as an empty file (touch).

- [ ] **Step 4: Commit**

```bash
cd ergon
git add ergon_builtins/pyproject.toml uv.lock \
    ergon_builtins/ergon_builtins/benchmarks/swebench_verified/__init__.py \
    tests/swebench_verified/__init__.py
git commit -m "chore(swebench): scaffold package and add datasets+swebench deps"
```

---

## Task 2: Task schemas

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/task_schemas.py`
- Test: `ergon/tests/swebench_verified/test_task_schemas.py`

Note: SWE-Bench Verified rows carry `FAIL_TO_PASS` and `PASS_TO_PASS` as JSON-encoded strings that need parsing. We normalize them to `list[str]` in the payload.

- [ ] **Step 1: Write failing tests**

Create `ergon/tests/swebench_verified/test_task_schemas.py`:

```python
"""Tests for SWE-Bench task schemas."""

from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)


RAW_ROW = {
    "instance_id": "django__django-11999",
    "repo": "django/django",
    "base_commit": "deadbeef",
    "patch": "--- gold patch, worker must not see ---",
    "test_patch": "--- test patch, evaluator only ---",
    "problem_statement": "Fix the thing.",
    "hints_text": "maybe look at foo.py",
    "version": "3.0",
    "FAIL_TO_PASS": '["tests.test_foo.TestFoo.test_fix"]',
    "PASS_TO_PASS": '["tests.test_foo.TestFoo.test_existing"]',
    "environment_setup_commit": "cafebabe",
}


def test_instance_parses_json_encoded_test_lists() -> None:
    instance = SWEBenchInstance.from_raw(RAW_ROW)
    assert instance.fail_to_pass == ["tests.test_foo.TestFoo.test_fix"]
    assert instance.pass_to_pass == ["tests.test_foo.TestFoo.test_existing"]


def test_payload_from_instance_strips_gold_patch() -> None:
    instance = SWEBenchInstance.from_raw(RAW_ROW)
    payload = SWEBenchTaskPayload.from_instance(instance)
    dumped = payload.model_dump()
    assert "patch" not in dumped
    assert dumped["test_patch"] == RAW_ROW["test_patch"]
    assert dumped["problem_statement"] == RAW_ROW["problem_statement"]


def test_worker_description_excludes_test_patch() -> None:
    instance = SWEBenchInstance.from_raw(RAW_ROW)
    payload = SWEBenchTaskPayload.from_instance(instance)
    description = payload.build_worker_description()
    assert RAW_ROW["problem_statement"] in description
    assert "test patch" not in description
    assert "gold patch" not in description
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/swebench_verified/test_task_schemas.py -v`
Expected: `ImportError` or `ModuleNotFoundError` for `task_schemas`.

- [ ] **Step 3: Implement `task_schemas.py`**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/task_schemas.py`:

```python
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
    def from_raw(cls, row: Mapping[str, Any]) -> "SWEBenchInstance":
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


def _parse_test_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        return [str(v) for v in json.loads(value)]
    raise TypeError(f"Unsupported FAIL/PASS list type: {type(value)!r}")
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/swebench_verified/test_task_schemas.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/task_schemas.py \
    tests/swebench_verified/test_task_schemas.py
git commit -m "feat(swebench): task payload schemas with gold-patch stripping"
```

---

## Task 3: Benchmark class (dataset loader)

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py`
- Test: `ergon/tests/swebench_verified/test_benchmark.py`

- [ ] **Step 1: Write failing tests**

Create `ergon/tests/swebench_verified/test_benchmark.py`:

```python
"""Tests for the SWE-Bench Verified benchmark loader."""

from __future__ import annotations

from unittest.mock import patch

from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SweBenchVerifiedBenchmark,
)


FAKE_ROWS = [
    {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "aaa",
        "patch": "GOLD",
        "test_patch": "TP1",
        "problem_statement": "p1",
        "hints_text": "",
        "version": "3.0",
        "FAIL_TO_PASS": '["t1"]',
        "PASS_TO_PASS": '["t0"]',
        "environment_setup_commit": "aaa",
    },
    {
        "instance_id": "sympy__sympy-2",
        "repo": "sympy/sympy",
        "base_commit": "bbb",
        "patch": "GOLD",
        "test_patch": "TP2",
        "problem_statement": "p2",
        "hints_text": "",
        "version": "1.10",
        "FAIL_TO_PASS": '["t2"]',
        "PASS_TO_PASS": '["t0"]',
        "environment_setup_commit": "bbb",
    },
]


def test_build_instances_yields_one_task_per_row() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        return_value=FAKE_ROWS,
    ):
        benchmark = SweBenchVerifiedBenchmark()
        instances = benchmark.build_instances()

    assert set(instances.keys()) == {"default"}
    tasks = instances["default"]
    assert len(tasks) == 2
    assert tasks[0].task_key == "django__django-1"
    assert tasks[1].task_key == "sympy__sympy-2"


def test_limit_truncates() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        return_value=FAKE_ROWS,
    ):
        benchmark = SweBenchVerifiedBenchmark(limit=1)
        tasks = benchmark.build_instances()["default"]

    assert len(tasks) == 1
    assert tasks[0].task_key == "django__django-1"


def test_task_description_excludes_test_patch_and_gold_patch() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        return_value=FAKE_ROWS,
    ):
        benchmark = SweBenchVerifiedBenchmark()
        task = benchmark.build_instances()["default"][0]

    assert "TP1" not in task.description
    assert "GOLD" not in task.description
    assert "p1" in task.description


def test_task_payload_retains_test_patch_for_evaluator() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        return_value=FAKE_ROWS,
    ):
        benchmark = SweBenchVerifiedBenchmark()
        task = benchmark.build_instances()["default"][0]

    assert task.task_payload["test_patch"] == "TP1"
    assert "patch" not in task.task_payload  # gold patch was dropped
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/swebench_verified/test_benchmark.py -v`
Expected: `ModuleNotFoundError` for `benchmark`.

- [ ] **Step 3: Implement the benchmark**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py`:

```python
"""SWE-Bench Verified benchmark loader.

Pulls the ``princeton-nlp/SWE-bench_Verified`` HuggingFace dataset and yields
one ``BenchmarkTask`` per instance. The worker only sees the problem
statement; the evaluator receives ``test_patch`` via the task payload.
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from typing import Any, ClassVar

from ergon_core.api.benchmark import Benchmark
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.swebench_verified.task_schemas import (
    SWEBenchInstance,
    SWEBenchTaskPayload,
)

logger = logging.getLogger(__name__)

HF_DATASET_ID = "princeton-nlp/SWE-bench_Verified"
HF_SPLIT = "test"


class SweBenchVerifiedBenchmark(Benchmark):
    """Benchmark backed by SWE-Bench Verified (500 curated instances)."""

    type_slug: ClassVar[str] = "swebench-verified"

    def __init__(
        self,
        *,
        limit: int | None = None,
        name: str | None = None,
        description: str | None = None,
        metadata: Mapping[str, Any] | None = None,  # slopcop: ignore[no-typing-any]
    ) -> None:
        super().__init__(
            name=name or "swebench-verified",
            description=description or "SWE-Bench Verified GitHub issue-fix benchmark",
            metadata=metadata,
        )
        self.limit = limit

    def build_instances(self) -> Mapping[str, Sequence[BenchmarkTask]]:
        rows = _load_rows(limit=self.limit)
        tasks: list[BenchmarkTask] = []
        for row in rows:
            instance = SWEBenchInstance.from_raw(row)
            payload = SWEBenchTaskPayload.from_instance(instance)
            tasks.append(
                BenchmarkTask(
                    task_key=instance.instance_id,
                    instance_key="default",
                    description=payload.build_worker_description(),
                    evaluator_binding_keys=("default",),
                    task_payload=payload.model_dump(),
                )
            )
        logger.info("Loaded %d SWE-Bench Verified instances", len(tasks))
        return {"default": tasks}

    def evaluator_requirements(self) -> Sequence[str]:
        return ("default",)


def _load_rows(*, limit: int | None = None) -> list[dict[str, Any]]:
    """Load rows from the HF dataset. Isolated for testability."""
    # reason: optional dependency from ergon-builtins[data]
    from datasets import load_dataset

    ds = load_dataset(HF_DATASET_ID, split=HF_SPLIT)
    if limit is not None:
        ds = ds.select(range(min(limit, len(ds))))
    return [dict(row) for row in ds]
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/swebench_verified/test_benchmark.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/benchmark.py \
    tests/swebench_verified/test_benchmark.py
git commit -m "feat(swebench): dataset loader yielding BenchmarkTasks"
```

---

## Task 4: Dockerfile and E2B template config

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox/Dockerfile`
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox/e2b.toml.template`

This task produces files that are consumed by `ergon benchmark setup swebench-verified` in a later task. There is no TDD cycle for a Dockerfile — verification is building the template and running a smoke command.

- [ ] **Step 1: Write the Dockerfile**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox/Dockerfile`:

```dockerfile
# SWE-Bench Verified sandbox: one image that covers the 12 repos in Verified.
# Per-instance Python selection and dependency install is driven at runtime
# by swebench.harness.test_spec — this image only provides the substrate.
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV PATH=/root/.local/bin:/usr/local/bin:$PATH
ENV UV_CACHE_DIR=/workspace/.uv-cache

# --- system deps -------------------------------------------------------------
# Kept in a single layer. Grouped by repo that needs them for readability.
RUN apt-get update && apt-get install -y --no-install-recommends \
    # core
    git ca-certificates curl wget unzip xz-utils \
    build-essential pkg-config \
    # python build deps
    libssl-dev libffi-dev libsqlite3-dev libbz2-dev \
    zlib1g-dev libreadline-dev liblzma-dev \
    # matplotlib / pillow
    libfreetype6-dev libpng-dev libjpeg-dev libtiff-dev \
    # scikit-learn / scipy
    libopenblas-dev liblapack-dev gfortran \
    # sphinx / lxml / xarray
    libxml2-dev libxslt1-dev \
    # django (psycopg2)
    libpq-dev \
  && rm -rf /var/lib/apt/lists/*

# --- uv as Python-version manager -------------------------------------------
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    ln -sf /root/.local/bin/uv /usr/local/bin/uv

# --- swebench harness (for test_spec + grading) -----------------------------
# Install into a dedicated venv so it does not collide with task-specific
# repo environments.
RUN uv venv /opt/swebench-harness --python 3.11 && \
    /opt/swebench-harness/bin/pip install --no-cache-dir "swebench>=3.0,<4"
ENV SWEBENCH_PY=/opt/swebench-harness/bin/python

# --- workspace layout -------------------------------------------------------
RUN mkdir -p /workspace/repo /workspace/.uv-cache /workspace/artifacts /inputs

WORKDIR /workspace
CMD ["/bin/bash"]
```

- [ ] **Step 2: Write the E2B template config**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox/e2b.toml.template`:

```toml
dockerfile = "Dockerfile"
template_name = "ergon-swebench-v1"
start_cmd = "/bin/bash"
cpu_count = 4
memory_mb = 8192
```

- [ ] **Step 3: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox/
git commit -m "feat(swebench): E2B sandbox template (Dockerfile + e2b.toml)"
```

(Template build itself happens in Task 7 after registry wiring.)

---

## Task 5: Sandbox manager

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py`
- Test: `ergon/tests/swebench_verified/test_sandbox_manager.py`

- [ ] **Step 1: Write failing tests**

Create `ergon/tests/swebench_verified/test_sandbox_manager.py`:

```python
"""Tests for SWEBenchSandboxManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)


@pytest.fixture(autouse=True)
def _reset_singleton():
    SWEBenchSandboxManager._instances.clear()
    yield
    SWEBenchSandboxManager._instances.clear()


def test_resolves_template_from_registry() -> None:
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.sandbox_manager.resolve_template",
        return_value="tmpl-abc123",
    ):
        manager = SWEBenchSandboxManager()
    assert manager.template == "tmpl-abc123"


@pytest.mark.asyncio
async def test_verify_setup_runs_git_version() -> None:
    manager = SWEBenchSandboxManager.__new__(SWEBenchSandboxManager)
    manager.template = "tmpl"
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=AsyncMock(exit_code=0, stdout="git version 2.40"))

    await manager._verify_setup(sandbox, task_id="t1")

    sandbox.commands.run.assert_awaited()
    args = sandbox.commands.run.call_args.args[0]
    assert "git --version" in args
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/swebench_verified/test_sandbox_manager.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the sandbox manager**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py`:

```python
"""Sandbox manager for the SWE-Bench Verified benchmark.

Per-task setup (cloning the repo at ``base_commit``, creating the venv at
the right Python version, installing deps) is driven by
``swebench.harness.test_spec`` and is performed by the worker at task
start, not here. This manager only provisions the E2B sandbox from the
pre-built template.
"""

from __future__ import annotations

import logging

from ergon_core.core.providers.sandbox.manager import BaseSandboxManager
from ergon_core.core.providers.sandbox.template_registry import resolve_template

logger = logging.getLogger(__name__)

TEMPLATE_SLUG = "swebench-verified"


class SWEBenchSandboxManager(BaseSandboxManager):
    """Singleton manager that hands out E2B sandboxes built from ergon-swebench-v1."""

    def __init__(self) -> None:
        super().__init__()
        self.template = resolve_template(TEMPLATE_SLUG)

    async def _install_dependencies(self, sandbox, task_id) -> None:  # noqa: ARG002
        # Template is pre-built; per-task setup is driven by the worker
        # using swebench.harness.test_spec scripts.
        return None

    async def _verify_setup(self, sandbox, task_id) -> None:  # noqa: ARG002
        result = await sandbox.commands.run("git --version && uv --version")
        if result.exit_code != 0:
            raise RuntimeError(f"SWE-Bench sandbox smoke check failed: {result.stdout}")
```

Note on `resolve_template`: this helper lives in `ergon_core.core.providers.sandbox.template_registry` and reads `~/.ergon/sandbox_templates.json`. If the import path differs in the current codebase, match the signature used by `MiniF2FSandboxManager.resolve_template` — grep for it before implementing if unsure.

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/swebench_verified/test_sandbox_manager.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/sandbox_manager.py \
    tests/swebench_verified/test_sandbox_manager.py
git commit -m "feat(swebench): sandbox manager with template resolution"
```

---

## Task 6: Registry registration

**Files:**
- Modify: `ergon/ergon_builtins/ergon_builtins/registry_core.py`
- Modify: `ergon/ergon_builtins/ergon_builtins/registry_data.py`

- [ ] **Step 1: Register the sandbox manager and template in `registry_core.py`**

In `ergon/ergon_builtins/ergon_builtins/registry_core.py`, add the import near the other benchmark-sandbox imports:

```python
from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
```

And extend the existing dicts:

```python
SANDBOX_MANAGERS: dict[str, type[BaseSandboxManager]] = {
    "gdpeval": GDPEvalSandboxManager,
    "minif2f": MiniF2FSandboxManager,
    "swebench-verified": SWEBenchSandboxManager,
}

SANDBOX_TEMPLATES: dict[str, Path] = {
    "minif2f": Path(__file__).parent / "benchmarks/minif2f/sandbox",
    "swebench-verified": Path(__file__).parent / "benchmarks/swebench_verified/sandbox",
}
```

- [ ] **Step 2: Register benchmark (+ placeholder worker/rubric entries) in `registry_data.py`**

In `ergon/ergon_builtins/ergon_builtins/registry_data.py`, add:

```python
from ergon_builtins.benchmarks.swebench_verified.benchmark import (
    SweBenchVerifiedBenchmark,
)
```

And extend the benchmarks dict:

```python
BENCHMARKS["swebench-verified"] = SweBenchVerifiedBenchmark
```

Worker and evaluator entries are added in Tasks 9 and 11 respectively.

- [ ] **Step 3: Sanity-check the registry loads**

Run: `uv run python -c "from ergon_builtins.registry import BENCHMARKS, SANDBOX_MANAGERS; assert 'swebench-verified' in BENCHMARKS; assert 'swebench-verified' in SANDBOX_MANAGERS; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add ergon_builtins/ergon_builtins/registry_core.py \
    ergon_builtins/ergon_builtins/registry_data.py
git commit -m "feat(swebench): register benchmark and sandbox manager"
```

---

## Task 7: Build the E2B template

**Files:** none created here — CLI action and artifact persistence to `~/.ergon/sandbox_templates.json`.

- [ ] **Step 1: Build the template via CLI**

Run: `uv run ergon benchmark setup swebench-verified`

Expected behaviour (mirroring miniF2F):
- Reads `e2b.toml.template` + `Dockerfile` from the registered path.
- Calls E2B `Template.build(...)` with `template_name="ergon-swebench-v1"`.
- Writes the returned template_id to `~/.ergon/sandbox_templates.json`.

If this command does not automatically pick up the new sandbox template, check `ergon_cli/commands/benchmark.py` — the loop over `SANDBOX_TEMPLATES` should be keyed off the registry, not a hard-coded list. If it's hard-coded, add the new slug there.

- [ ] **Step 2: Smoke the built template**

Run: `uv run python -c "
import asyncio
from e2b import AsyncSandbox
from ergon_core.core.providers.sandbox.template_registry import resolve_template

async def go():
    tid = resolve_template('swebench-verified')
    sbx = await AsyncSandbox.create(template=tid)
    r = await sbx.commands.run('git --version && uv --version && \$SWEBENCH_PY -c \"import swebench; print(swebench.__version__)\"')
    print(r.stdout)
    await sbx.kill()

asyncio.run(go())
"`

Expected: `git version ...`, `uv ...`, and a swebench version string.

- [ ] **Step 3: Commit (template registry entry)**

```bash
git add -u   # picks up ~/.ergon changes IF they live in the repo; typically they don't
git commit --allow-empty -m "chore(swebench): build and register ergon-swebench-v1 template"
```

(If `~/.ergon/sandbox_templates.json` is outside the repo, just document the template id in the commit message.)

---

## Task 8: Toolkit (bash + str-replace editor)

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py`
- Test: `ergon/tests/swebench_verified/test_toolkit.py`

Keep the toolkit deliberately generic: `bash` and `str_replace_editor`. Both operate against the sandbox; no SWE-Bench-specific logic here.

- [ ] **Step 1: Write failing tests**

Create `ergon/tests/swebench_verified/test_toolkit.py`:

```python
"""Tests for the SWE-Bench toolkit (bash + str-replace editor)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit


@pytest.mark.asyncio
async def test_bash_tool_runs_command_in_workdir() -> None:
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(
        return_value=SimpleNamespace(exit_code=0, stdout="hello\n", stderr="")
    )
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "bash")
    response = await tool.function(command="echo hello")

    assert response.exit_code == 0
    assert "hello" in response.stdout
    # Command should be wrapped to execute inside the workdir
    invoked = sandbox.commands.run.call_args.args[0]
    assert "/workspace/repo" in invoked


@pytest.mark.asyncio
async def test_str_replace_editor_view_reads_file() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="def foo():\n    return 1\n")
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "str_replace_editor")
    response = await tool.function(command="view", path="src/foo.py")

    assert "def foo" in response.output
    sandbox.files.read.assert_awaited_with("/workspace/repo/src/foo.py")


@pytest.mark.asyncio
async def test_str_replace_editor_replace_updates_file() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="def foo():\n    return 1\n")
    sandbox.files.write = AsyncMock()
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "str_replace_editor")
    response = await tool.function(
        command="str_replace",
        path="src/foo.py",
        old_str="    return 1",
        new_str="    return 2",
    )

    assert response.ok is True
    sandbox.files.write.assert_awaited()
    written_path, written_bytes = sandbox.files.write.call_args.args
    assert written_path == "/workspace/repo/src/foo.py"
    assert b"return 2" in written_bytes


@pytest.mark.asyncio
async def test_str_replace_editor_replace_fails_when_old_str_not_unique() -> None:
    sandbox = AsyncMock()
    sandbox.files.read = AsyncMock(return_value="x = 1\nx = 1\n")
    tk = SWEBenchToolkit(sandbox=sandbox, workdir="/workspace/repo")

    tool = next(t for t in tk.get_tools() if t.name == "str_replace_editor")
    response = await tool.function(
        command="str_replace", path="x.py", old_str="x = 1", new_str="x = 2"
    )

    assert response.ok is False
    assert "not unique" in response.error.lower()
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/swebench_verified/test_toolkit.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the toolkit**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py`:

```python
"""Tools exposed to a SWE-Bench worker.

Deliberately generic: one bash tool and one str-replace editor. Enough to
solve the benchmark end-to-end and portable to other code-editing tasks.
"""

from __future__ import annotations

import shlex
from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel
from pydantic_ai.tools import Tool


class BashResponse(BaseModel):
    exit_code: int
    stdout: str
    stderr: str


class EditorResponse(BaseModel):
    ok: bool
    output: str = ""
    error: str = ""


class SWEBenchToolkit:
    def __init__(self, *, sandbox, workdir: str = "/workspace/repo") -> None:
        self._sandbox = sandbox
        self._workdir = workdir

    def get_tools(self) -> Sequence[Tool]:
        return [self._bash_tool(), self._editor_tool()]

    # --- bash ---------------------------------------------------------------

    def _bash_tool(self) -> Tool:
        async def bash(command: str, timeout_sec: int = 300) -> BashResponse:
            """Run a shell command inside the repo workdir."""
            wrapped = f"cd {shlex.quote(self._workdir)} && {command}"
            result = await self._sandbox.commands.run(wrapped, timeout=timeout_sec)
            return BashResponse(
                exit_code=result.exit_code,
                stdout=result.stdout or "",
                stderr=getattr(result, "stderr", "") or "",
            )

        return Tool(function=bash, takes_ctx=False, name="bash")

    # --- str-replace editor -------------------------------------------------

    def _editor_tool(self) -> Tool:
        async def str_replace_editor(
            command: Literal["view", "create", "str_replace"],
            path: str,
            file_text: str | None = None,
            old_str: str | None = None,
            new_str: str | None = None,
        ) -> EditorResponse:
            """View, create, or edit a file by exact string replacement."""
            abs_path = f"{self._workdir.rstrip('/')}/{path.lstrip('/')}"
            try:
                if command == "view":
                    content = await self._sandbox.files.read(abs_path)
                    return EditorResponse(ok=True, output=content)

                if command == "create":
                    if file_text is None:
                        return EditorResponse(ok=False, error="file_text required for create")
                    await self._sandbox.files.write(abs_path, file_text.encode())
                    return EditorResponse(ok=True, output=f"created {abs_path}")

                if command == "str_replace":
                    if old_str is None or new_str is None:
                        return EditorResponse(ok=False, error="old_str and new_str required")
                    content = await self._sandbox.files.read(abs_path)
                    occurrences = content.count(old_str)
                    if occurrences == 0:
                        return EditorResponse(ok=False, error="old_str not found")
                    if occurrences > 1:
                        return EditorResponse(
                            ok=False,
                            error=f"old_str not unique ({occurrences} matches); add more context",
                        )
                    new_content = content.replace(old_str, new_str, 1)
                    await self._sandbox.files.write(abs_path, new_content.encode())
                    return EditorResponse(ok=True, output=f"edited {abs_path}")

                return EditorResponse(ok=False, error=f"unknown command {command!r}")
            except Exception as exc:  # noqa: BLE001  - surface as tool error
                return EditorResponse(ok=False, error=str(exc))

        return Tool(function=str_replace_editor, takes_ctx=False, name="str_replace_editor")
```

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/swebench_verified/test_toolkit.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py \
    tests/swebench_verified/test_toolkit.py
git commit -m "feat(swebench): generic bash + str-replace editor toolkit"
```

---

## Task 9: Worker (with per-task setup + patch extraction)

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/workers/baselines/swebench_worker.py`
- Test: `ergon/tests/swebench_verified/test_worker.py`
- Modify: `ergon/ergon_builtins/ergon_builtins/registry_data.py`

The worker does three things around the ReAct loop:
1. **Before** the loop: run `swebench.harness.test_spec.make_test_spec(instance).setup_env_script` and `install_repo_script` inside the sandbox so the repo is at `base_commit` with deps installed in a venv.
2. **During** the loop: ReAct with the bash + editor toolkit.
3. **After** the loop: run `git diff HEAD` and store the patch as the worker output.

- [ ] **Step 1: Write failing tests**

Create `ergon/tests/swebench_verified/test_worker.py`:

```python
"""Tests for SWEBenchReActWorker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker import WorkerContext
from ergon_builtins.workers.baselines.swebench_worker import SWEBenchReActWorker


def _fake_task() -> BenchmarkTask:
    payload = {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "aaa",
        "version": "3.0",
        "problem_statement": "p",
        "hints_text": "",
        "fail_to_pass": ["t1"],
        "pass_to_pass": ["t0"],
        "environment_setup_commit": "aaa",
        "test_patch": "TP",
    }
    return BenchmarkTask(
        task_key="django__django-1",
        instance_key="default",
        description="Fix the thing",
        evaluator_binding_keys=("default",),
        task_payload=payload,
    )


@pytest.mark.asyncio
async def test_worker_runs_setup_scripts_before_react_loop() -> None:
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="", stderr=""))
    manager = MagicMock()
    manager.get_or_create = AsyncMock(return_value=sandbox)

    with patch(
        "ergon_builtins.workers.baselines.swebench_worker.SWEBenchSandboxManager",
        return_value=manager,
    ), patch(
        "ergon_builtins.workers.baselines.swebench_worker.make_test_spec",
    ) as mk_spec:
        mk_spec.return_value = MagicMock(
            setup_env_script="echo SETUP",
            install_repo_script="echo INSTALL",
            eval_script="echo EVAL",  # not used by worker
        )
        worker = SWEBenchReActWorker(model="stub")
        # Short-circuit the ReAct loop for this unit test
        with patch.object(SWEBenchReActWorker.__bases__[0], "execute") as parent_execute:
            async def _empty(*a, **kw):
                if False:
                    yield
            parent_execute.return_value = _empty()

            ctx = WorkerContext(run_id="r", task_id="t", execution_id="e", sandbox_id="s")
            async for _ in worker.execute(_fake_task(), context=ctx):
                pass

    # Setup and install scripts should both have been run
    invoked = [call.args[0] for call in sandbox.commands.run.call_args_list]
    assert any("SETUP" in c for c in invoked)
    assert any("INSTALL" in c for c in invoked)


@pytest.mark.asyncio
async def test_worker_extracts_patch_via_git_diff_on_output() -> None:
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(
        return_value=MagicMock(exit_code=0, stdout="--- diff ---\n+foo", stderr="")
    )
    worker = SWEBenchReActWorker(model="stub")
    worker._sandbox = sandbox
    worker._workdir = "/workspace/repo"

    ctx = WorkerContext(run_id="r", task_id="t", execution_id="e", sandbox_id="s")
    output = await worker._extract_patch(ctx)

    assert "--- diff ---" in output
    invoked = sandbox.commands.run.call_args.args[0]
    assert "git diff HEAD" in invoked
    assert "/workspace/repo" in invoked
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/swebench_verified/test_worker.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the worker**

Create `ergon/ergon_builtins/ergon_builtins/workers/baselines/swebench_worker.py`:

```python
"""SWE-Bench Verified worker.

Uses swebench.harness.test_spec to perform per-task setup inside the E2B
sandbox, runs a ReAct loop over a generic bash + editor toolkit, and
returns the resulting ``git diff HEAD`` as the output artifact.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator
from typing import ClassVar

from ergon_core.api.task_types import BenchmarkTask
from ergon_core.api.worker import GenerationTurn, WorkerContext, WorkerOutput
from ergon_core.api.react_worker import ReActWorker  # matches miniF2F base import

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.benchmarks.swebench_verified.toolkit import SWEBenchToolkit

logger = logging.getLogger(__name__)

WORKDIR = "/workspace/repo"
SETUP_TIMEOUT_SEC = 1800  # 30 min — slowest installs (sklearn, matplotlib)


def make_test_spec(instance_row):  # re-exported for test monkeypatching
    from swebench.harness.test_spec import make_test_spec as _mk
    return _mk(instance_row)


class SWEBenchReActWorker(ReActWorker):
    type_slug: ClassVar[str] = "swebench-react"

    def __init__(self, *, model: str, **kwargs) -> None:
        super().__init__(model=model, **kwargs)
        self._sandbox = None
        self._workdir = WORKDIR
        self._patch: str = ""

    async def execute(
        self,
        task: BenchmarkTask,
        *,
        context: WorkerContext,
    ) -> AsyncGenerator[GenerationTurn, None]:
        manager = SWEBenchSandboxManager()
        sandbox = await manager.get_or_create(context.task_id)
        self._sandbox = sandbox

        await self._run_setup(task)

        toolkit = SWEBenchToolkit(sandbox=sandbox, workdir=self._workdir)
        self.tools = list(toolkit.get_tools())

        async for turn in super().execute(task, context=context):
            yield turn

        self._patch = await self._extract_patch(context)

    async def _run_setup(self, task: BenchmarkTask) -> None:
        # The raw instance row we'll feed to make_test_spec is the payload
        # plus the derived fields needed by swebench's schema.
        row = _payload_to_swebench_row(task.task_payload)
        spec = make_test_spec(row)

        for label, script in (
            ("setup_env", spec.setup_env_script),
            ("install_repo", spec.install_repo_script),
        ):
            logger.info("Running swebench %s script for %s", label, task.task_key)
            result = await self._sandbox.commands.run(
                f"bash -c {_shell_quote(script)}",
                timeout=SETUP_TIMEOUT_SEC,
            )
            if result.exit_code != 0:
                raise RuntimeError(
                    f"swebench {label} failed for {task.task_key}: "
                    f"{(result.stdout or '')[-1000:]}"
                )

    async def _extract_patch(self, context: WorkerContext) -> str:  # noqa: ARG002
        result = await self._sandbox.commands.run(
            f"cd {self._workdir} && git add -A && git diff HEAD",
            timeout=60,
        )
        if result.exit_code != 0:
            logger.warning("git diff failed: %s", result.stdout)
            return ""
        return result.stdout or ""

    def get_output(self, context: WorkerContext) -> WorkerOutput:  # noqa: ARG002
        return WorkerOutput(
            output=self._patch,
            success=bool(self._patch.strip()),
            artifacts={"patch": self._patch},
        )


def _payload_to_swebench_row(payload: dict) -> dict:
    """Re-expand a SWEBenchTaskPayload dict into the row shape swebench expects."""
    return {
        "instance_id": payload["instance_id"],
        "repo": payload["repo"],
        "base_commit": payload["base_commit"],
        "version": payload["version"],
        "problem_statement": payload["problem_statement"],
        "hints_text": payload.get("hints_text", ""),
        "FAIL_TO_PASS": payload["fail_to_pass"],
        "PASS_TO_PASS": payload["pass_to_pass"],
        "environment_setup_commit": payload["environment_setup_commit"],
        "test_patch": payload["test_patch"],
        "patch": "",  # intentionally blank - gold patch never reaches worker
    }


def _shell_quote(script: str) -> str:
    import shlex
    return shlex.quote(script)
```

Note: the base-class import is written as `ergon_core.api.react_worker.ReActWorker` — match whichever module `MiniF2FReActWorker` imports from. Grep `minif2f_react_worker.py` for the exact line and mirror it.

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/swebench_verified/test_worker.py -v`
Expected: 2 passed.

- [ ] **Step 5: Register in `registry_data.py`**

Open `ergon/ergon_builtins/ergon_builtins/registry_data.py`, add:

```python
from ergon_builtins.workers.baselines.swebench_worker import SWEBenchReActWorker
# ...
WORKERS["swebench-react"] = SWEBenchReActWorker
```

- [ ] **Step 6: Commit**

```bash
git add ergon_builtins/ergon_builtins/workers/baselines/swebench_worker.py \
    ergon_builtins/ergon_builtins/registry_data.py \
    tests/swebench_verified/test_worker.py
git commit -m "feat(swebench): worker with setup, ReAct loop, patch extraction"
```

---

## Task 10: Criterion (evaluation via swebench harness)

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`
- Test: `ergon/tests/swebench_verified/test_criterion.py`

The criterion's job: given the agent's patch and the task payload, run the official SWE-Bench eval and return a 0/1 score. To avoid reusing the worker sandbox (which is messy post-agent), the criterion spawns a fresh sandbox of the same template, checks out `base_commit`, applies `test_patch`, applies the agent patch, runs `eval_script`, and parses the log with `swebench.harness.grading`.

- [ ] **Step 1: Write failing tests**

Create `ergon/tests/swebench_verified/test_criterion.py`:

```python
"""Tests for SWEBenchTestCriterion.

We mock the sandbox and swebench.harness.grading to isolate the flow:
patch application order, eval_script invocation, result parsing.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ergon_core.api.evaluator import CriterionResult, EvaluationContext
from ergon_core.api.task_types import BenchmarkTask
from ergon_builtins.benchmarks.swebench_verified.criterion import (
    SWEBenchTestCriterion,
)


def _task() -> BenchmarkTask:
    return BenchmarkTask(
        task_key="django__django-1",
        instance_key="default",
        description="",
        evaluator_binding_keys=("default",),
        task_payload={
            "instance_id": "django__django-1",
            "repo": "django/django",
            "base_commit": "aaa",
            "version": "3.0",
            "problem_statement": "p",
            "hints_text": "",
            "fail_to_pass": ["t1"],
            "pass_to_pass": ["t0"],
            "environment_setup_commit": "aaa",
            "test_patch": "TP",
        },
    )


@pytest.mark.asyncio
async def test_criterion_scores_1_when_all_fail_to_pass_resolved() -> None:
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="log", stderr=""))
    sandbox.kill = AsyncMock()

    with patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion._spawn_eval_sandbox",
        AsyncMock(return_value=sandbox),
    ), patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        return_value=MagicMock(eval_script="echo EVAL"),
    ), patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.grade_log",
        return_value={"resolved": True, "fail_to_pass": {"success": ["t1"], "failure": []},
                      "pass_to_pass": {"success": ["t0"], "failure": []}},
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        ctx = EvaluationContext(
            worker_output=MagicMock(output="PATCH", artifacts={"patch": "PATCH"}),
        )
        result: CriterionResult = await crit.evaluate(_task(), ctx)

    assert result.score == 1.0
    assert result.passed is True
    # patch application order: test_patch first, then agent patch
    seq = [call.args[0] for call in sandbox.commands.run.call_args_list]
    assert any("git apply" in s and "test_patch" in s.lower() for s in seq) or \
        any("TP" in s for s in seq)


@pytest.mark.asyncio
async def test_criterion_scores_0_when_empty_patch() -> None:
    crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
    ctx = EvaluationContext(worker_output=MagicMock(output="", artifacts={"patch": ""}))

    result = await crit.evaluate(_task(), ctx)

    assert result.score == 0.0
    assert result.passed is False
    assert "empty patch" in result.feedback.lower()


@pytest.mark.asyncio
async def test_criterion_scores_0_when_fail_to_pass_not_resolved() -> None:
    sandbox = AsyncMock()
    sandbox.commands.run = AsyncMock(return_value=MagicMock(exit_code=0, stdout="log", stderr=""))
    sandbox.kill = AsyncMock()

    with patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion._spawn_eval_sandbox",
        AsyncMock(return_value=sandbox),
    ), patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.make_test_spec",
        return_value=MagicMock(eval_script="echo EVAL"),
    ), patch(
        "ergon_builtins.benchmarks.swebench_verified.criterion.grade_log",
        return_value={"resolved": False, "fail_to_pass": {"success": [], "failure": ["t1"]},
                      "pass_to_pass": {"success": ["t0"], "failure": []}},
    ):
        crit = SWEBenchTestCriterion(name="test-resolution", weight=1.0)
        ctx = EvaluationContext(worker_output=MagicMock(output="PATCH", artifacts={"patch": "PATCH"}))
        result = await crit.evaluate(_task(), ctx)

    assert result.score == 0.0
    assert result.passed is False
```

- [ ] **Step 2: Run tests to confirm they fail**

Run: `uv run pytest tests/swebench_verified/test_criterion.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the criterion**

Create `ergon/ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py`:

```python
"""Evaluator criterion that runs the SWE-Bench test harness.

Spawns a fresh E2B sandbox from the ergon-swebench-v1 template, checks
out ``base_commit``, applies ``test_patch``, applies the agent's patch,
runs the swebench-generated ``eval_script``, and parses the log to
decide resolved/unresolved.
"""

from __future__ import annotations

import logging
import shlex

from ergon_core.api.criterion import Criterion, CriterionResult
from ergon_core.api.evaluator import EvaluationContext
from ergon_core.api.task_types import BenchmarkTask

from ergon_builtins.benchmarks.swebench_verified.sandbox_manager import (
    SWEBenchSandboxManager,
)
from ergon_builtins.workers.baselines.swebench_worker import _payload_to_swebench_row

logger = logging.getLogger(__name__)

WORKDIR = "/workspace/repo"
EVAL_TIMEOUT_SEC = 1800


def make_test_spec(row):  # re-exported for tests
    from swebench.harness.test_spec import make_test_spec as _mk
    return _mk(row)


def grade_log(instance_id: str, log: str, fail_to_pass: list[str], pass_to_pass: list[str]) -> dict:
    """Adapt swebench.harness.grading to our inputs."""
    from swebench.harness.grading import get_logs_eval, get_eval_report
    # swebench's API shape has drifted across versions. The cleanest stable
    # surface: parse the eval log to a per-test status map, then compute
    # resolved using get_eval_report with our FAIL/PASS lists.
    test_status = get_logs_eval(log)  # dict: test_name -> "PASSED"/"FAILED"/...
    report = get_eval_report(
        test_spec=None,
        prediction={"instance_id": instance_id},
        test_log_path=None,
        include_tests_status=True,
        _status_map_override=test_status,
        _fail_to_pass_override=fail_to_pass,
        _pass_to_pass_override=pass_to_pass,
    )
    return report[instance_id]


async def _spawn_eval_sandbox():
    manager = SWEBenchSandboxManager()
    # A fresh sandbox keyed by a random UUID; never shared with a worker.
    import uuid
    sbx = await manager.get_or_create(uuid.uuid4())
    return sbx


class SWEBenchTestCriterion(Criterion):
    """Scores 1 iff the agent patch resolves all FAIL_TO_PASS and does not break PASS_TO_PASS."""

    def __init__(self, *, name: str, weight: float = 1.0) -> None:
        super().__init__(name=name, weight=weight)

    async def evaluate(
        self, task: BenchmarkTask, context: EvaluationContext
    ) -> CriterionResult:
        patch_text = (context.worker_output.artifacts or {}).get("patch") or context.worker_output.output or ""
        if not patch_text.strip():
            return CriterionResult(
                name=self.name, score=0.0, passed=False,
                feedback="Empty patch — agent did not produce any edits.",
                metadata={},
            )

        payload = task.task_payload
        row = _payload_to_swebench_row(payload)
        spec = make_test_spec(row)

        sandbox = await _spawn_eval_sandbox()
        try:
            # 1. fresh checkout at base_commit (swebench install script does this;
            #    we rely on the sandbox being a fresh provision here).
            inst_script = spec.install_repo_script  # clones + checks out base_commit
            r = await sandbox.commands.run(
                f"bash -c {shlex.quote(inst_script)}", timeout=EVAL_TIMEOUT_SEC
            )
            if r.exit_code != 0:
                return _error_result(self.name, "install_repo failed", r.stdout)

            # 2. apply test_patch
            await _write_and_apply(sandbox, "test.patch", payload["test_patch"])

            # 3. apply agent patch
            await _write_and_apply(sandbox, "agent.patch", patch_text)

            # 4. run eval script, capture full log
            r = await sandbox.commands.run(
                f"bash -c {shlex.quote(spec.eval_script)} 2>&1",
                timeout=EVAL_TIMEOUT_SEC,
            )
            log = r.stdout or ""

            # 5. grade
            report = grade_log(
                instance_id=payload["instance_id"],
                log=log,
                fail_to_pass=payload["fail_to_pass"],
                pass_to_pass=payload["pass_to_pass"],
            )
            resolved = bool(report.get("resolved"))
            return CriterionResult(
                name=self.name,
                score=1.0 if resolved else 0.0,
                passed=resolved,
                feedback=_format_feedback(report),
                metadata=report,
            )
        finally:
            try:
                await sandbox.kill()
            except Exception:  # noqa: BLE001
                logger.warning("Failed to kill eval sandbox", exc_info=True)


async def _write_and_apply(sandbox, filename: str, content: str) -> None:
    path = f"/tmp/{filename}"
    await sandbox.files.write(path, content.encode())
    r = await sandbox.commands.run(
        f"cd {WORKDIR} && git apply --allow-empty --verbose {path}", timeout=120
    )
    if r.exit_code != 0:
        # Try 3-way; some patches need it
        r = await sandbox.commands.run(
            f"cd {WORKDIR} && git apply --3way --verbose {path}", timeout=120
        )
    if r.exit_code != 0:
        raise RuntimeError(f"git apply {filename} failed: {(r.stdout or '')[-800:]}")


def _error_result(name: str, kind: str, detail: str) -> CriterionResult:
    return CriterionResult(
        name=name, score=0.0, passed=False,
        feedback=f"{kind}: {(detail or '')[-400:]}", metadata={"error": kind},
    )


def _format_feedback(report: dict) -> str:
    f2p = report.get("fail_to_pass", {})
    p2p = report.get("pass_to_pass", {})
    return (
        f"FAIL_TO_PASS success={len(f2p.get('success', []))} "
        f"failure={len(f2p.get('failure', []))}; "
        f"PASS_TO_PASS success={len(p2p.get('success', []))} "
        f"failure={len(p2p.get('failure', []))}"
    )
```

Note on `grade_log`: the `swebench` package's grading API surface has shifted between 2.x and 3.x. If the `_status_map_override` / `_fail_to_pass_override` kwargs don't exist in the installed version, adapt by writing the log to a temp file and feeding it to the public `get_eval_report(test_spec=spec, prediction={...}, test_log_path=log_path)`. The behavioural contract is the same.

- [ ] **Step 4: Run tests to confirm they pass**

Run: `uv run pytest tests/swebench_verified/test_criterion.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add ergon_builtins/ergon_builtins/benchmarks/swebench_verified/criterion.py \
    tests/swebench_verified/test_criterion.py
git commit -m "feat(swebench): test-resolution criterion using swebench harness"
```

---

## Task 11: Rubric (evaluator wrapping the criterion)

**Files:**
- Create: `ergon/ergon_builtins/ergon_builtins/evaluators/rubrics/swebench_rubric.py`
- Test: `ergon/tests/swebench_verified/test_rubric.py`
- Modify: `ergon/ergon_builtins/ergon_builtins/registry_data.py`

- [ ] **Step 1: Write failing test**

Create `ergon/tests/swebench_verified/test_rubric.py`:

```python
"""Tests for SWEBenchRubric."""

from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric


def test_rubric_contains_single_test_resolution_criterion() -> None:
    rubric = SWEBenchRubric(name="swebench-rubric")
    names = [c.name for c in rubric.criteria]
    assert names == ["test-resolution"]
    assert rubric.criteria[0].weight == 1.0
```

- [ ] **Step 2: Run test to confirm it fails**

Run: `uv run pytest tests/swebench_verified/test_rubric.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement the rubric**

Create `ergon/ergon_builtins/ergon_builtins/evaluators/rubrics/swebench_rubric.py`:

```python
"""Evaluator rubric for SWE-Bench Verified."""

from __future__ import annotations

from typing import ClassVar

from ergon_core.api.evaluator import Rubric

from ergon_builtins.benchmarks.swebench_verified.criterion import (
    SWEBenchTestCriterion,
)


class SWEBenchRubric(Rubric):
    type_slug: ClassVar[str] = "swebench-rubric"

    def __init__(self, *, name: str = "swebench-rubric") -> None:
        super().__init__(
            name=name,
            criteria=[SWEBenchTestCriterion(name="test-resolution", weight=1.0)],
        )
```

- [ ] **Step 4: Run test to confirm it passes**

Run: `uv run pytest tests/swebench_verified/test_rubric.py -v`
Expected: 1 passed.

- [ ] **Step 5: Register in `registry_data.py`**

Add to `ergon/ergon_builtins/ergon_builtins/registry_data.py`:

```python
from ergon_builtins.evaluators.rubrics.swebench_rubric import SWEBenchRubric
# ...
EVALUATORS["swebench-rubric"] = SWEBenchRubric
```

- [ ] **Step 6: Commit**

```bash
git add ergon_builtins/ergon_builtins/evaluators/rubrics/swebench_rubric.py \
    ergon_builtins/ergon_builtins/registry_data.py \
    tests/swebench_verified/test_rubric.py
git commit -m "feat(swebench): rubric wrapping test-resolution criterion"
```

---

## Task 12: CLI composition wiring

**Files:** Verify only — composition should already work via registries.

- [ ] **Step 1: Confirm the slugs compose into an experiment**

Run:
```bash
uv run ergon benchmark list | grep swebench-verified
```

Expected: `swebench-verified` appears.

Run:
```bash
uv run python -c "
from ergon_cli.composition import build_experiment
exp = build_experiment(
    benchmark_slug='swebench-verified',
    model='claude-opus-4-6',
    worker_slug='swebench-react',
    evaluator_slug='swebench-rubric',
    limit=1,
)
print(type(exp).__name__, 'ok')
"
```

Expected: `Experiment ok`.

- [ ] **Step 2: Commit (no-op if nothing changed)**

If CLI wiring required changes, commit; otherwise skip.

---

## Task 13: End-to-end smoke test

**Files:**
- Create: `ergon/tests/swebench_verified/test_smoke_e2e.py`

The smoke test runs **one** instance end-to-end with a stubbed worker that produces an empty patch, confirming the full pipeline (dataset load → task build → worker invocation → criterion scoring) wires without errors. We don't run a real agent here — that belongs in a manual/opt-in E2E run.

- [ ] **Step 1: Write the smoke test**

Create `ergon/tests/swebench_verified/test_smoke_e2e.py`:

```python
"""End-to-end smoke for SWE-Bench Verified wiring (no LLM, no E2B)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ergon_cli.composition import build_experiment


@pytest.mark.asyncio
async def test_compose_and_build_instances_with_limit_1() -> None:
    fake_row = {
        "instance_id": "django__django-1",
        "repo": "django/django",
        "base_commit": "aaa",
        "patch": "GOLD",
        "test_patch": "TP",
        "problem_statement": "p",
        "hints_text": "",
        "version": "3.0",
        "FAIL_TO_PASS": '["t1"]',
        "PASS_TO_PASS": '["t0"]',
        "environment_setup_commit": "aaa",
    }
    with patch(
        "ergon_builtins.benchmarks.swebench_verified.benchmark._load_rows",
        return_value=[fake_row],
    ):
        exp = build_experiment(
            benchmark_slug="swebench-verified",
            model="stub",
            worker_slug="swebench-react",
            evaluator_slug="swebench-rubric",
            limit=1,
        )
        tasks = exp.benchmark.build_instances()["default"]

    assert len(tasks) == 1
    assert tasks[0].task_key == "django__django-1"
    assert "GOLD" not in tasks[0].description
```

- [ ] **Step 2: Run it**

Run: `uv run pytest tests/swebench_verified/test_smoke_e2e.py -v`
Expected: 1 passed.

- [ ] **Step 3: Run the full suite for the new package**

Run: `uv run pytest tests/swebench_verified/ -v`
Expected: all tests in the package pass (roughly 15 tests total across all test files).

- [ ] **Step 4: Run repo-wide checks**

Run:
```bash
pnpm run check:be
```

Expected: ruff, ty, slopcop all clean.

- [ ] **Step 5: Commit**

```bash
git add tests/swebench_verified/test_smoke_e2e.py
git commit -m "test(swebench): end-to-end composition smoke"
```

---

## Out of scope for this plan

Deliberately deferred — call them out explicitly so future work knows:

- **Large-scale parallel eval runs.** Concurrency tuning against 500 instances, Inngest throttling, E2B cost budgeting. First cut is `--limit 5` on a known-easy subset (e.g., flask / requests / pytest instances with small test suites).
- **Wheel cache pre-warming.** `UV_CACHE_DIR=/workspace/.uv-cache` is already wired but a persistent E2B volume mount is needed to amortize the cost across runs. That's a sandbox-infra change, not a benchmark change.
- **Retry logic for flaky tests.** SWE-Bench is known to have some non-determinism. The canonical harness retries; we currently don't. Add only if measured flakiness matters.
- **Leaderboard submission format.** The `predictions.jsonl` artifact format for the SWE-Bench leaderboard isn't produced here — easy to add a CLI `ergon benchmark export swebench-verified --format predictions`.
- **SWE-Bench full / Lite variants.** Same code path, different `HF_DATASET_ID`. Trivially pluggable via a subclass once this lands.

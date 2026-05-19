# Builtins PR 4 TODO Cleanup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Remove the TODO-backed cleanup debt in `ergon_builtins` as part of PR 4, preserving the current public benchmark/worker behavior while making the builtins code library-tier clean.

**Architecture:** Keep PR 4 focused on builtins domain cleanup: move domain models into semantic modules, delete empty/re-export-only modules where they add no boundary, replace constructor shims with Pydantic validators, and rely on existing core runtime containment instead of duplicating it in builtins. Do not change benchmark behavior, task JSON shape, or worker/evaluator slugs.

**Tech Stack:** Python 3.13, Pydantic v2, pydantic-ai tools, `ergon_core.api` public `Task`/`Sandbox`/`Criterion` contracts, ruff, ty, pytest.

---

## TODO Inventory

Source TODOs were read from:

`/Users/charliemasters/.config/superpowers/worktrees/ergon/codex-builtins-pr01-hygiene-guardrails/ergon_builtins`

Current PR 4 branch:

`/tmp/ergon-builtins-restack`, branch `codex/builtins-pr04-benchmark-domains-v2`

Implement these in PR 4:

- Strongly type GDPEval raw rubric loading instead of returning bare `dict`.
- Move GDPEval criteria factory helpers out of `criteria/__init__.py`.
- Remove empty `operations.py` placeholder modules.
- Move tool response models out of `tool_builder.py` and stop `response_models.py` re-exporting from builders.
- Move GDPEval sandbox operation response DTOs out of `task_schemas.py`.
- Replace `Any` annotations for `sandbox`/`task` in benchmark tool builders/toolkits.
- Remove `max_score` magic constructors from GDPEval criteria and normalize HF rubric data into canonical `score_spec` at the dataset-loading/conversion boundary.
- Replace the ResearchRubrics judge constructor override with Pydantic pre-validation.
- Move the ResearchRubrics settings import to module scope.
- Delete builtins Logfire observability hooks and remove the `ReActWorker` call site.
- Remove stale subtask-containment TODO text because `WorkerContext` already enforces descendant containment.
- Decide `StagedRubric.validate_runtime_deps`: keep dependency validation but remove the redundant stage-shape validation from that method, because Pydantic field constraints already own stage shape.

Non-goals for PR 4:

- Do not remove `validate_runtime_deps` from core public APIs. `WorkerExecuteService` and `EvaluationService` call it.
- Do not redesign GDPEval rubric semantics or load real HF data in unit tests.
- Do not change task/evaluator/criterion type slugs.

---

## Worker / Tool / Model Domain Layout

The current top-level `workers/`, `tools/`, and `models/` packages read like grab bags:

- `workers/react_worker.py` and `workers/react_output.py` are one coherent ReAct implementation, but sit beside the unrelated `training_stub_worker.py`.
- `workers/toolkit.py` is not really a worker; it is the serializable base class for benchmark toolkits used by ReAct-style agents.
- `workers/tool_budget.py`, `tools/workflow_cli_tool.py`, `tools/subtask_lifecycle_toolkit.py`, `tools/bash_sandbox_tool.py`, `tools/graph_toolkit.py`, and `tools/graph_toolkit_types.py` are separate toolkit surfaces, not one shared tools domain.
- `models/*` are not domain models; they are LLM provider/backend infrastructure.

Restructure toward ownership-first packages:

```text
ergon_builtins/
  agents/
    react/
      __init__.py
      worker.py              # ReActWorker
      output.py              # worker_output_from_chunks
    training/
      __init__.py
      synthetic_worker.py    # TrainingStubWorker + synthetic chunk helpers
  toolkits/
    common/
      __init__.py
      base.py                # Toolkit base for serializable benchmark toolkits
      budgets.py             # AgentToolBudgetState / deps / exhausted result
    subagents/
      __init__.py
      toolkit.py             # SubtaskLifecycleToolkit + builder
      models.py              # subtask lifecycle response DTOs
      sandbox_bash.py        # manager/subagent bash helper
    workflow_cli/
      __init__.py
      tool.py                # make_workflow_cli_tool
    resources/
      __init__.py
      toolkit.py             # ResearchGraphToolkit
      models.py              # ResourceRef / TaskExecutionRef
  llm/
    __init__.py
    resolution.py
    capture_settings.py
    providers/
      __init__.py
      openrouter.py
      openrouter_responses.py
      transformers.py
      vllm.py
```

Compatibility strategy:

- Move implementation modules to the new layout in PR 4.
- Keep thin compatibility modules at the old import paths for this stack only where external tests or likely user code import them:
  - `ergon_builtins.workers.react_worker`
  - `ergon_builtins.workers.react_output`
  - `ergon_builtins.workers.toolkit`
  - `ergon_builtins.workers.training_stub_worker`
  - `ergon_builtins.workers.tool_budget`
  - `ergon_builtins.tools.subtask_lifecycle_toolkit`
  - `ergon_builtins.tools.bash_sandbox_tool`
  - `ergon_builtins.tools.workflow_cli_tool`
  - `ergon_builtins.tools.graph_toolkit`
  - `ergon_builtins.tools.graph_toolkit_types`
  - `ergon_builtins.models.resolution`
- Compatibility modules must contain imports/`__all__` only, plus a short deprecation note in the docstring. No logic should remain there.
- Update builtins-internal imports to the new paths immediately.
- Add architecture tests that fail if old compatibility modules contain class/function definitions.

This keeps PR 4 reviewable: each toolkit folder contains the callable factory, response models, and helper logic for one agent-facing surface. Shared abstractions go in `toolkits/common`, not in a generic `tools` package.

---

### Task 1: Move GDPEval Criterion Factories Out Of `__init__.py`

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria/factories.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria/__init__.py`
- Test: `ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py`

- [x] **Step 1: Write the failing tests**

Create `ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py`:

```python
from ergon_builtins.benchmarks.gdpeval.criteria import (
    GDPEvalCriterion,
    content_quality_judge,
    make_code_check,
    make_llm_judge,
    output_file_exists,
)
from ergon_core.api.criterion import ScoreScale
from ergon_builtins.benchmarks.gdpeval.criteria.code_check import CodeCheckCriterion
from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import LLMJudgeCriterion


def test_gdpeval_criterion_union_accepts_domain_criteria() -> None:
    criterion: GDPEvalCriterion = make_code_check(
        name="has-output",
        code_template="True",
        description="checks output",
    )

    assert isinstance(criterion, CodeCheckCriterion)


def test_make_code_check_requires_explicit_description() -> None:
    criterion = make_code_check(
        name="has-output",
        code_template="True",
        description="checks output",
        score_spec=ScoreScale(max_score=2.5),
    )

    assert criterion.slug == "has-output"
    assert criterion.description == "checks output"
    assert criterion.score_spec.max_score == 2.5


def test_make_llm_judge_requires_explicit_description() -> None:
    criterion = make_llm_judge(
        name="quality",
        prompt_template="Judge this.",
        description="checks quality",
        model="openai:gpt-4o-mini",
        score_spec=ScoreScale(max_score=3.0),
    )

    assert isinstance(criterion, LLMJudgeCriterion)
    assert criterion.description == "checks quality"
    assert criterion.score_spec.max_score == 3.0


def test_gdpeval_presets_supply_descriptions() -> None:
    assert output_file_exists("*.docx").description == (
        "Verify output file matching *.docx was produced"
    )
    assert content_quality_judge("accuracy").description == "Judge content quality on: accuracy"
```

- [x] **Step 2: Run the failing tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py -q
```

Expected: fail because `criteria/factories.py` does not exist yet and descriptions still default to `""`.

- [x] **Step 3: Implement the factory module**

Move the factory/preset functions from `criteria/__init__.py` into `criteria/factories.py`:

```python
"""Factory helpers for GDP-specific criterion configurations."""

from ergon_builtins.benchmarks.gdpeval.criteria.code_check import CodeCheckCriterion
from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import LLMJudgeCriterion
from ergon_core.api.criterion import ScoreScale


def make_code_check(
    name: str,
    code_template: str,
    *,
    description: str,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
) -> CodeCheckCriterion:
    """Create a GDP code-check criterion."""
    return CodeCheckCriterion(
        slug=name,
        code_template=code_template,
        description=description,
        weight=weight,
        score_spec=score_spec or ScoreScale(),
    )


def make_llm_judge(
    name: str,
    prompt_template: str,
    *,
    description: str,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
    model: str = "openai:gpt-4o",
) -> LLMJudgeCriterion:
    """Create a GDP LLM-judge criterion."""
    return LLMJudgeCriterion(
        slug=name,
        prompt_template=prompt_template,
        description=description,
        weight=weight,
        score_spec=score_spec or ScoreScale(),
        model=model,
    )


def output_file_exists(
    file_pattern: str = "*.docx",
    *,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
) -> CodeCheckCriterion:
    """Check that at least one output file matching *file_pattern* exists."""
    return make_code_check(
        name=f"output-exists-{file_pattern}",
        code_template=(
            "import glob; "
            f"files = glob.glob('/workspace/final_output/{file_pattern}'); "
            "len(files) > 0"
        ),
        description=f"Verify output file matching {file_pattern} was produced",
        weight=weight,
        score_spec=score_spec,
    )


def content_quality_judge(
    aspect: str = "completeness",
    *,
    weight: float = 1.0,
    score_spec: ScoreScale | None = None,
    model: str = "openai:gpt-4o",
) -> LLMJudgeCriterion:
    """LLM judge that evaluates content quality on a specific *aspect*."""
    return make_llm_judge(
        name=f"content-quality-{aspect}",
        prompt_template=(
            f"Evaluate the {aspect} of the worker's output. "
            "Score 1.0 if the output fully satisfies expectations, "
            "0.5 for partial, 0.0 for absent or incorrect."
        ),
        description=f"Judge content quality on: {aspect}",
        weight=weight,
        score_spec=score_spec,
        model=model,
    )
```

Make `criteria/__init__.py` only expose symbols:

```python
"""GDP-specific criterion package."""

from ergon_builtins.benchmarks.gdpeval.criteria.code_check import CodeCheckCriterion
from ergon_builtins.benchmarks.gdpeval.criteria.factories import (
    content_quality_judge,
    make_code_check,
    make_llm_judge,
    output_file_exists,
)
from ergon_builtins.benchmarks.gdpeval.criteria.llm_judge import LLMJudgeCriterion

GDPEvalCriterion = CodeCheckCriterion | LLMJudgeCriterion

__all__ = [
    "CodeCheckCriterion",
    "GDPEvalCriterion",
    "LLMJudgeCriterion",
    "content_quality_judge",
    "make_code_check",
    "make_llm_judge",
    "output_file_exists",
]
```

- [x] **Step 4: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py -q
```

Expected: pass.

---

### Task 2: Remove GDPEval Criterion Constructor Shims

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria/code_check.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria/llm_judge.py`
- Test: `ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py`
- Test: `ergon_builtins/tests/unit/state/test_llm_judge_runtime_injection.py`

- [x] **Step 1: Add tests that require canonical `score_spec` input**

Append to `test_gdpeval_criteria_factories.py`:

```python
import pytest
from ergon_core.api.criterion import ScoreScale
from pydantic import ValidationError


def test_code_check_rejects_legacy_max_score_constructor_input() -> None:
    with pytest.raises(ValidationError):
        CodeCheckCriterion(slug="code", code_template="True", max_score=4.0)


def test_llm_judge_rejects_legacy_max_score_constructor_input() -> None:
    with pytest.raises(ValidationError):
        LLMJudgeCriterion(slug="judge", prompt_template="Judge.", max_score=5.0)


def test_gdpeval_criteria_accept_canonical_score_spec() -> None:
    code = CodeCheckCriterion(
        slug="code",
        code_template="True",
        score_spec=ScoreScale(max_score=4.0),
    )
    judge = LLMJudgeCriterion(
        slug="judge",
        prompt_template="Judge.",
        score_spec=ScoreScale(max_score=5.0),
    )

    assert code.score_spec.max_score == 4.0
    assert judge.score_spec.max_score == 5.0
```

- [x] **Step 2: Run tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py ergon_builtins/tests/unit/state/test_llm_judge_runtime_injection.py -q
```

Expected before implementation: fail because the criteria currently accept `max_score` through constructor shims.

- [x] **Step 3: Delete constructor overrides and disallow extra fields**

In both `CodeCheckCriterion` and `LLMJudgeCriterion`:

- Remove the custom `__init__`.
- Remove the `Any` import if it becomes unused.
- Remove the `ScoreScale` import if it becomes unused.
- Set a class model config that forbids unknown constructor fields while preserving the base model's arbitrary type allowance:

```python
from pydantic import ConfigDict


model_config = ConfigDict(arbitrary_types_allowed=True, frozen=False, extra="forbid")
```

This makes `score_spec=ScoreScale(max_score=...)` the only supported construction format for max-score configuration. Raw HF fields named `max_score` are handled by Task 3 before criterion construction.

- [x] **Step 4: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_criteria_factories.py ergon_builtins/tests/unit/state/test_llm_judge_runtime_injection.py -q
uv run ruff check ergon_builtins/ergon_builtins/benchmarks/gdpeval/criteria --output-format concise
```

Expected: pass.

---

### Task 3: Type GDPEval Rubric Loader Output

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/task_schemas.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/loader.py`
- Test: `ergon_builtins/tests/unit/benchmarks/test_gdpeval_loader_types.py`

- [x] **Step 1: Write tests using a local JSONL fixture**

Create `ergon_builtins/tests/unit/benchmarks/test_gdpeval_loader_types.py`:

```python
from pathlib import Path

from ergon_builtins.benchmarks.gdpeval.loader import load_rubric_data, load_single_rubric
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPRubricData


def test_load_rubric_data_returns_typed_rubric_records(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rubric_file = tmp_path / "rubrics.jsonl"
    rubric_file.write_text(
        '{"task_id": "task-1", "category_name": "docs", '
        '"max_total_score": 1.0, "stages": [], "rationale": "fixture"}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.loader.hf_hub_download",
        lambda **_: str(rubric_file),
    )

    rubrics = load_rubric_data()

    assert isinstance(rubrics["task-1"], GDPRubricData)
    assert rubrics["task-1"].task_id == "task-1"
    assert rubrics["task-1"].category_name == "docs"


def test_loader_normalizes_hf_max_score_to_score_spec(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rubric_file = tmp_path / "rubrics.jsonl"
    rubric_file.write_text(
        '{"task_id": "task-1", "category_name": "docs", '
        '"max_total_score": 1.0, "stages": [{"name": "stage", '
        '"max_points": 2.0, "criteria": [{"name": "criterion", '
        '"code_template": "True", "max_score": 2.0}]}]}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.loader.hf_hub_download",
        lambda **_: str(rubric_file),
    )

    rubric = load_single_rubric("task-1")

    criterion = rubric.stages[0].criteria[0]
    assert criterion.score_spec.max_score == 2.0
    assert "max_score" not in criterion.model_dump()


def test_load_single_rubric_returns_typed_record(
    tmp_path: Path,
    monkeypatch,
) -> None:
    rubric_file = tmp_path / "rubrics.jsonl"
    rubric_file.write_text(
        '{"task_id": "task-1", "category_name": "docs", '
        '"max_total_score": 1.0, "stages": []}\n',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "ergon_builtins.benchmarks.gdpeval.loader.hf_hub_download",
        lambda **_: str(rubric_file),
    )

    rubric = load_single_rubric("task-1")

    assert isinstance(rubric, GDPRubricData)
    assert rubric.task_id == "task-1"
```

- [x] **Step 2: Run tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_loader_types.py -q
```

Expected: fail because `GDPRubricData` does not exist and loader returns raw dicts.

- [x] **Step 3: Add typed models**

Append to `task_schemas.py`:

```python
class GDPRubricCriterionData(BaseModel):
    """Raw GDPEval criterion entry from the HuggingFace rubric JSONL."""

    name: str | None = None
    description: str | None = None
    type: str | None = None
    code_template: str | None = None
    prompt_template: str | None = None
    weight: float = 1.0
    score_spec: ScoreScale = Field(default_factory=ScoreScale)

    @model_validator(mode="before")
    @classmethod
    def _normalize_hf_max_score(cls, data: Any) -> Any:  # slopcop: ignore[no-typing-any]
        if isinstance(data, dict) and "max_score" in data and "score_spec" not in data:
            data = dict(data)
            data["score_spec"] = {"max_score": data.pop("max_score")}
        return data

    model_config = {"extra": "allow"}


class GDPRubricStageData(BaseModel):
    """Raw GDPEval staged-rubric entry from the HuggingFace rubric JSONL."""

    name: str
    description: str | None = None
    is_required: bool = True
    max_points: float = 1.0
    min_score_to_pass: float = 0.0
    on_failure_action: str = "skip_remaining"
    on_failure_score: float = 0.0
    criteria: list[GDPRubricCriterionData] = Field(default_factory=list)

    model_config = {"extra": "allow"}


class GDPRubricData(BaseModel):
    """Raw GDPEval rubric record keyed by task_id."""

    task_id: str
    category_name: str | None = None
    max_total_score: float | None = None
    stages: list[GDPRubricStageData] = Field(default_factory=list)
    rationale: str | None = None

    model_config = {"extra": "allow"}
```

Add imports to `task_schemas.py`:

```python
from typing import Any

from ergon_core.api.criterion import ScoreScale
from pydantic import BaseModel, Field, model_validator
```

- [x] **Step 4: Use the typed model in the loader**

In `loader.py`, import `GDPRubricData` and update signatures:

```python
from ergon_builtins.benchmarks.gdpeval.task_schemas import GDPRubricData


def load_rubric_data(
    split: str = "train",
    repo_id: str = HF_REPO_ID,
) -> dict[str, GDPRubricData]:
    ...
    rubrics: dict[str, GDPRubricData] = {}
    with open(path) as f:
        for line in f:
            rubric = GDPRubricData.model_validate_json(line)
            rubrics[rubric.task_id] = rubric
    return rubrics


def load_single_rubric(
    task_id: str,
    split: str = "train",
    repo_id: str = HF_REPO_ID,
) -> GDPRubricData:
    ...
```

- [x] **Step 5: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_loader_types.py ergon_builtins/tests/unit/state/test_gdpeval_benchmark.py ergon_builtins/tests/unit/test_gdpeval_v2_definition.py -q
```

Expected: pass.

---

### Task 4: Move Tool Response Models Out Of Tool Builders

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/tools/response_models.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/tools/tool_builder.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/tools/response_models.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/tools/tool_builder.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/tools/response_models.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/tools/tool_builder.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/tools/response_models.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/tools/tool_builder.py`
- Test: `ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py`

- [x] **Step 1: Write architecture tests**

Create `ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py`:

```python
from pathlib import Path


ROOT = Path("ergon_builtins/ergon_builtins/benchmarks")


def test_tool_response_models_do_not_import_tool_builders() -> None:
    for path in ROOT.glob("*/tools/response_models.py"):
        text = path.read_text()
        assert ".tools.tool_builder import" not in text, path


def test_tool_builders_import_response_models() -> None:
    for path in ROOT.glob("*/tools/tool_builder.py"):
        text = path.read_text()
        assert ".tools.response_models import" in text, path


def test_empty_operations_modules_are_deleted() -> None:
    assert not list(ROOT.glob("*/tools/operations.py"))
```

- [x] **Step 2: Run tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py -q
```

Expected: fail because `response_models.py` re-exports from builders and empty `operations.py` files exist.

- [x] **Step 3: Move response model classes**

For each benchmark:

- Copy response `BaseModel` classes from `tools/tool_builder.py` into `tools/response_models.py`.
- Import those classes back into `tools/tool_builder.py`.
- Remove direct `BaseModel` and `Field` imports from builders when no longer needed.
- Keep `__all__` in `response_models.py`.

For MiniF2F specifically, move:

```python
WriteLeanResponse
LeanCheckResponse
LeanVerificationResponse
SearchLemmasResponse
```

For GDPEval, move:

```python
BashResponse
EditorResponse
RunPythonResponse
```

For ResearchRubrics, move:

```python
ReportWriteResult
ReportReadResult
BashResult
```

For SWE-Bench, move:

```python
BashResponse
EditorResponse
```

- [x] **Step 4: Delete empty operations modules**

Delete:

```bash
ergon_builtins/ergon_builtins/benchmarks/gdpeval/tools/operations.py
ergon_builtins/ergon_builtins/benchmarks/minif2f/tools/operations.py
ergon_builtins/ergon_builtins/benchmarks/researchrubrics/tools/operations.py
ergon_builtins/ergon_builtins/benchmarks/swebench_verified/tools/operations.py
```

Use `apply_patch` delete hunks, not shell `rm`.

- [x] **Step 5: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py ergon_builtins/tests/unit/benchmarks/test_minif2f_task_shape.py ergon_builtins/tests/unit/test_gdpeval_v2_definition.py ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py -q
```

Expected: pass.

---

### Task 5: Move GDPEval Sandbox Operation DTOs Out Of Task Schemas

**Files:**
- Create: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/tools/sandbox_response_models.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/task_schemas.py`
- Test: `ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py`

- [x] **Step 1: Extend architecture test**

Append:

```python
def test_gdpeval_task_schemas_do_not_contain_tool_response_dtos() -> None:
    text = Path("ergon_builtins/ergon_builtins/benchmarks/gdpeval/task_schemas.py").read_text()
    assert "ReadPDFResponse" not in text
    assert "CreateDocxResponse" not in text
    assert "OcrImageResponse" not in text
```

- [x] **Step 2: Move DTOs**

Move these classes from `task_schemas.py` into `tools/sandbox_response_models.py`:

```python
ReadPDFResponse
CreateDocxResponse
ReadExcelResponse
CreateExcelResponse
ReadCsvResponse
CreateCsvResponse
OcrImageResponse
RunPythonResponse
```

Keep class names unchanged to preserve existing imports if consumers choose the new semantic module.

- [x] **Step 3: Verify no stale imports**

Run:

```bash
rg "ReadPDFResponse|CreateDocxResponse|ReadExcelResponse|CreateExcelResponse|ReadCsvResponse|CreateCsvResponse|OcrImageResponse" ergon_builtins ergon_core tests
```

Expected: only `tools/sandbox_response_models.py` and the architecture test mention them.

- [x] **Step 4: Verify tests**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py ergon_builtins/tests/unit/test_builtin_task_definition_roundtrip.py -q
```

Expected: pass.

---

### Task 6: Type Tool Builder And Toolkit Runtime Parameters

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/tools/tool_builder.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/minif2f/tools/tool_builder.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/tools/tool_builder.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/swebench_verified/tools/tool_builder.py`

- [x] **Step 1: Replace `Any` on sandbox/task runtime params**

Use public contracts:

```python
from typing import Any

from ergon_core.api import Task
from ergon_core.api.sandbox import Sandbox
from pydantic_ai.tools import Tool
```

Use signatures:

```python
def tools(self, sandbox: Sandbox, task: Task[Any]) -> list[Tool]:
    ...


def build_tools(
    toolkit: GDPEvalToolkit,
    *,
    sandbox: Sandbox,
    task: Task[Any],
) -> list[Tool]:
    ...
```

Apply the same shape to MiniF2F, ResearchRubrics, and SWE-Bench.

- [x] **Step 2: Remove unused `task` warnings cleanly**

If a builder does not use `task`, add:

```python
del task
```

near the top of the function body.

- [x] **Step 3: Verify**

Run:

```bash
uv run ty check ergon_builtins/ergon_builtins/benchmarks/gdpeval ergon_builtins/ergon_builtins/benchmarks/minif2f ergon_builtins/ergon_builtins/benchmarks/researchrubrics ergon_builtins/ergon_builtins/benchmarks/swebench_verified
uv run ruff check ergon_builtins/ergon_builtins/benchmarks --output-format concise
```

Expected: pass.

---

### Task 7: Clean ResearchRubrics Judge Construction

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/criteria/judge.py`
- Test: `ergon_builtins/tests/unit/state/test_research_rubrics_benchmark.py`

- [x] **Step 1: Add explicit tests for defaulting behavior**

Append to `test_research_rubrics_benchmark.py`:

```python
def test_researchrubrics_judge_defaults_from_rubric_without_constructor_override() -> None:
    rubric = RubricCriterion(criterion="Cite sources", axis="evidence", weight=2.0)

    criterion = ResearchRubricsJudgeCriterion(slug="evidence", rubric=rubric)

    assert criterion.description == "Cite sources"
    assert criterion.weight == 2.0
    assert criterion.score_spec.max_score == 2.0
    assert criterion.rubric_text == "Cite sources"
```

- [x] **Step 2: Run the targeted test**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/state/test_research_rubrics_benchmark.py::test_researchrubrics_judge_defaults_from_rubric_without_constructor_override -q
```

Expected before implementation: pass because the constructor currently does it. This locks behavior before removing the constructor.

- [x] **Step 3: Replace `__init__` with a before validator**

In `ResearchRubricsJudgeCriterion`, remove `__init__` and use:

```python
@model_validator(mode="before")
@classmethod
def _default_fields_from_rubric(cls, data: Any) -> Any:  # slopcop: ignore[no-typing-any]
    if not isinstance(data, dict):
        return data
    rubric = data.get("rubric")
    if not isinstance(rubric, RubricCriterion):
        return data
    data = dict(data)
    data.setdefault("description", rubric.criterion)
    data.setdefault("weight", rubric.weight)
    data.setdefault("score_spec", ScoreScale(max_score=abs(rubric.weight)))
    data.setdefault("rubric_text", rubric.criterion)
    return data
```

Keep `_reject_model_alias`; either leave it as a separate validator or fold the alias check into the new validator.

- [x] **Step 4: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/state/test_research_rubrics_benchmark.py ergon_builtins/tests/unit/test_research_rubrics_v2_definition.py -q
uv run ruff check ergon_builtins/ergon_builtins/benchmarks/researchrubrics/criteria/judge.py --output-format concise
```

Expected: pass.

---

### Task 8: Move ResearchRubrics Settings Import To Module Scope

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/benchmark.py`
- Test: `ergon_builtins/tests/unit/state/test_research_rubrics_benchmark.py`

- [x] **Step 1: Move import**

At module top:

```python
from ergon_core.core.shared.settings import settings
```

Remove the local import from `_load_rows`.

- [x] **Step 2: Verify monkeypatch behavior still works**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/state/test_research_rubrics_benchmark.py -q
```

Expected: pass. Existing tests monkeypatch `load_dataset`, not the local import, so this should be safe.

---

### Task 9: Delete Builtins Logfire Observability Hook

**Files:**
- Modify: `ergon_builtins/ergon_builtins/workers/react_worker.py`
- Delete: `ergon_builtins/ergon_builtins/observability/__init__.py`
- Delete: `ergon_builtins/ergon_builtins/observability/pydantic_ai_logfire.py`
- Delete: `ergon_builtins/tests/unit/builtins/test_logfire_pydantic_ai.py`
- Test: `ergon_builtins/tests/unit/workers/test_react_worker_contract.py`

- [x] **Step 1: Write/adjust architecture check**

Add to `ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py`:

```python
def test_builtins_do_not_configure_logfire_observability() -> None:
    assert not Path("ergon_builtins/ergon_builtins/observability").exists()
    react_worker = Path("ergon_builtins/ergon_builtins/workers/react_worker.py").read_text()
    assert "configure_pydantic_ai_logfire" not in react_worker
    assert "logfire" not in react_worker.lower()
```

- [x] **Step 2: Remove call site**

In `react_worker.py`:

- Delete `from ergon_builtins.observability.pydantic_ai_logfire import configure_pydantic_ai_logfire`.
- Delete `configure_pydantic_ai_logfire()` from the execution path.

- [x] **Step 3: Delete module and tests**

Delete:

```bash
ergon_builtins/ergon_builtins/observability/__init__.py
ergon_builtins/ergon_builtins/observability/pydantic_ai_logfire.py
ergon_builtins/tests/unit/builtins/test_logfire_pydantic_ai.py
```

Use `apply_patch` delete hunks.

- [x] **Step 4: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/workers/test_react_worker_contract.py ergon_builtins/tests/unit/architecture/test_builtin_tool_boundaries.py -q
rg "logfire|configure_pydantic_ai_logfire|ergon_builtins\\.observability" ergon_builtins ergon_core tests
```

Expected: tests pass, `rg` returns no builtins Logfire references.

---

### Task 10: Clean StagedRubric Validation Hook

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/gdpeval/rubric/staged_rubric.py`
- Test: `ergon_builtins/tests/unit/benchmarks/test_gdpeval_staged_rubric.py`

- [x] **Step 1: Add tests for Pydantic-owned shape validation**

Create `ergon_builtins/tests/unit/benchmarks/test_gdpeval_staged_rubric.py`:

```python
import pytest
from pydantic import ValidationError

from ergon_builtins.benchmarks.gdpeval.rubric import EvaluationStage, StagedRubric
from ergon_builtins.benchmarks.gdpeval.criteria.factories import make_code_check


def test_staged_rubric_runtime_validation_only_checks_dependencies() -> None:
    rubric = StagedRubric(
        name="gdpeval",
        category_name="docs",
        max_total_score=1.0,
        stages=[],
    )

    rubric.validate_runtime_deps()


def test_evaluation_stage_requires_at_least_one_criterion() -> None:
    with pytest.raises(ValidationError):
        EvaluationStage(
            name="empty",
            description="empty stage",
            max_points=1.0,
            criteria=[],
        )


def test_staged_rubric_still_rejects_stage_max_above_total() -> None:
    criterion = make_code_check(
        name="has-output",
        code_template="True",
        description="checks output",
    )

    with pytest.raises(ValidationError):
        StagedRubric(
            name="gdpeval",
            category_name="docs",
            max_total_score=0.5,
            stages=[
                EvaluationStage(
                    name="format",
                    description="format",
                    max_points=1.0,
                    criteria=[criterion],
                )
            ],
        )
```

- [x] **Step 2: Remove redundant override**

Delete `StagedRubric.validate_runtime_deps`. The inherited `Rubric.validate_runtime_deps` still checks evaluator/criterion package dependencies. Stage shape is already handled by Pydantic:

- `EvaluationStage.criteria` uses `min_length=1`.
- `_materialise_stage_state` rejects total stage max above total score.

- [x] **Step 3: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/benchmarks/test_gdpeval_staged_rubric.py ergon_builtins/tests/unit/test_gdpeval_v2_definition.py -q
```

Expected: pass.

---

### Task 11: Remove Stale Subtask Containment TODO

**Files:**
- Modify: `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`
- Modify: `ergon_builtins/tests/unit/tools/test_subtask_lifecycle_toolkit_containment.py`

- [x] **Step 1: Strengthen existing test wording/coverage**

Update `test_worker_toolkit_returns_failure_when_context_blocks_target` to cover all target-taking tools:

```python
@pytest.mark.asyncio
async def test_worker_toolkit_returns_failure_when_context_blocks_target() -> None:
    context = _FakeContext()
    toolkit = SubtaskLifecycleToolkit(context=context)

    for tool_name, args in [
        ("get_subtask", (str(uuid4()),)),
        ("cancel_task", (str(uuid4()),)),
        ("restart_task", (str(uuid4()),)),
        ("refine_task", (str(uuid4()), "new description")),
    ]:
        tool = next(tool for tool in toolkit.get_tools() if tool.__name__ == tool_name)
        result = await tool(*args)
        assert isinstance(result, ToolFailure)
```

Change `_FakeContext.cancel_task`, `_FakeContext.refine_task`, and `_FakeContext.restart_task` to raise `RuntimeError("not contained")` when `task_id != self.allowed_id`.

- [x] **Step 2: Update docstring**

Replace the stale note/TODO with:

```python
    Target-taking tools delegate containment to ``WorkerContext``. That
    facade verifies each supplied node id is this context's task id or a
    descendant before calling runtime task services, so the toolkit keeps
    only response-shaping and UUID parsing logic here.
```

- [x] **Step 3: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/tools/test_subtask_lifecycle_toolkit_containment.py -q
```

Expected: pass.

---

### Task 12: Restructure ReAct And Training Worker Domains

**Files:**
- Create: `ergon_builtins/ergon_builtins/agents/__init__.py`
- Create: `ergon_builtins/ergon_builtins/agents/react/__init__.py`
- Create: `ergon_builtins/ergon_builtins/agents/react/worker.py`
- Create: `ergon_builtins/ergon_builtins/agents/react/output.py`
- Create: `ergon_builtins/ergon_builtins/agents/training/__init__.py`
- Create: `ergon_builtins/ergon_builtins/agents/training/synthetic_worker.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/__init__.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/common/__init__.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/common/base.py`
- Modify: `ergon_builtins/ergon_builtins/workers/__init__.py`
- Modify: `ergon_builtins/ergon_builtins/workers/react_worker.py`
- Modify: `ergon_builtins/ergon_builtins/workers/react_output.py`
- Modify: `ergon_builtins/ergon_builtins/workers/toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/workers/training_stub_worker.py`
- Modify imports in benchmark worker factories/toolkits/tests.
- Test: `ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py`

- [x] **Step 1: Add layout tests**

Create `ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py`:

```python
from pathlib import Path


def test_react_implementation_lives_under_agents_react() -> None:
    assert Path("ergon_builtins/ergon_builtins/agents/react/worker.py").exists()
    assert Path("ergon_builtins/ergon_builtins/agents/react/output.py").exists()


def test_training_stub_lives_under_agents_training() -> None:
    assert Path("ergon_builtins/ergon_builtins/agents/training/synthetic_worker.py").exists()


def test_toolkit_base_lives_under_toolkits_common() -> None:
    assert Path("ergon_builtins/ergon_builtins/toolkits/common/base.py").exists()


def test_old_worker_modules_are_compatibility_shims_only() -> None:
    for path in [
        Path("ergon_builtins/ergon_builtins/workers/react_worker.py"),
        Path("ergon_builtins/ergon_builtins/workers/react_output.py"),
        Path("ergon_builtins/ergon_builtins/workers/toolkit.py"),
        Path("ergon_builtins/ergon_builtins/workers/training_stub_worker.py"),
    ]:
        text = path.read_text()
        assert "compatibility import" in text
        assert "\nclass " not in text
        assert "\ndef " not in text
```

- [x] **Step 2: Move implementation modules**

Move file contents:

```text
workers/react_worker.py          -> agents/react/worker.py
workers/react_output.py          -> agents/react/output.py
workers/toolkit.py               -> toolkits/common/base.py
workers/training_stub_worker.py  -> agents/training/synthetic_worker.py
```

Update imports inside moved files:

```python
from ergon_builtins.agents.react.output import worker_output_from_chunks
from ergon_builtins.llm.resolution import resolve_model_target
from ergon_builtins.toolkits.common.base import Toolkit
```

If Task 14 has not run yet, keep `resolve_model_target` imported from `ergon_builtins.models.resolution` temporarily and update it in Task 14.

- [x] **Step 3: Add compatibility shims**

Replace old worker modules with import-only shims, for example:

```python
"""Deprecated compatibility import for ``ergon_builtins.agents.react.worker``."""

from ergon_builtins.agents.react.worker import ReActWorker

__all__ = ["ReActWorker"]
```

Apply the same pattern for `react_output.py`, `toolkit.py`, and `training_stub_worker.py`.

- [x] **Step 4: Update internal imports**

Replace builtins-internal imports:

```text
ergon_builtins.workers.react_worker      -> ergon_builtins.agents.react.worker
ergon_builtins.workers.react_output      -> ergon_builtins.agents.react.output
ergon_builtins.workers.toolkit           -> ergon_builtins.toolkits.common.base
ergon_builtins.workers.training_stub_worker -> ergon_builtins.agents.training.synthetic_worker
```

Keep tests that explicitly assert old compatibility imports if they are testing public import stability.

- [x] **Step 5: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/workers ergon_builtins/tests/unit/benchmarks ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py -q
```

Expected: pass.

---

### Task 13: Restructure Toolkit Domains

**Files:**
- Create: `ergon_builtins/ergon_builtins/toolkits/subagents/__init__.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/subagents/toolkit.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/subagents/models.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/subagents/sandbox_bash.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/workflow_cli/__init__.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/workflow_cli/tool.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/resources/__init__.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/resources/toolkit.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/resources/models.py`
- Create: `ergon_builtins/ergon_builtins/toolkits/common/budgets.py`
- Modify: `ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py`
- Modify: `ergon_builtins/ergon_builtins/tools/graph_toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/tools/graph_toolkit_types.py`
- Modify: `ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py`
- Modify: `ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py`
- Modify: `ergon_builtins/ergon_builtins/workers/tool_budget.py`
- Modify imports in tests and CLI tests.
- Test: `ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py`

- [x] **Step 1: Extend layout tests**

Append:

```python
def test_toolkit_implementations_live_under_named_toolkit_packages() -> None:
    for rel in [
        "toolkits/common/budgets.py",
        "toolkits/subagents/toolkit.py",
        "toolkits/subagents/models.py",
        "toolkits/subagents/sandbox_bash.py",
        "toolkits/workflow_cli/tool.py",
        "toolkits/resources/toolkit.py",
        "toolkits/resources/models.py",
    ]:
        assert Path(f"ergon_builtins/ergon_builtins/{rel}").exists()


def test_old_tool_modules_are_compatibility_shims_only() -> None:
    for path in [
        Path("ergon_builtins/ergon_builtins/tools/bash_sandbox_tool.py"),
        Path("ergon_builtins/ergon_builtins/tools/graph_toolkit.py"),
        Path("ergon_builtins/ergon_builtins/tools/graph_toolkit_types.py"),
        Path("ergon_builtins/ergon_builtins/tools/subtask_lifecycle_toolkit.py"),
        Path("ergon_builtins/ergon_builtins/tools/workflow_cli_tool.py"),
        Path("ergon_builtins/ergon_builtins/workers/tool_budget.py"),
    ]:
        text = path.read_text()
        assert "compatibility import" in text
        assert "\nclass " not in text
        assert "\ndef " not in text
```

- [x] **Step 2: Move implementation modules**

Move file contents:

```text
workers/tool_budget.py             -> toolkits/common/budgets.py
tools/subtask_lifecycle_toolkit.py  -> toolkits/subagents/toolkit.py
tools/bash_sandbox_tool.py          -> toolkits/subagents/sandbox_bash.py
tools/workflow_cli_tool.py          -> toolkits/workflow_cli/tool.py
tools/graph_toolkit.py              -> toolkits/resources/toolkit.py
tools/graph_toolkit_types.py        -> toolkits/resources/models.py
```

Update imports within moved files:

```python
from ergon_builtins.toolkits.common.budgets import ...
from ergon_builtins.toolkits.resources.models import ResourceRef
from ergon_builtins.toolkits.subagents.sandbox_bash import make_sandbox_bash_tool
```

While moving `subtask_lifecycle_toolkit.py`, split response DTOs into
`toolkits/subagents/models.py` and import them from `toolkits/subagents/toolkit.py`.
This gives the subagent toolkit its own local schema file instead of keeping
models and tool construction in one large module.

- [x] **Step 3: Add compatibility shims**

Replace old modules with import-only shims, for example:

```python
"""Deprecated compatibility import for ``ergon_builtins.toolkits.subagents.toolkit``."""

from ergon_builtins.toolkits.subagents.models import (
    AddSubtaskToolResponse,
    AddSubtaskToolSuccess,
    CancelTaskToolResponse,
    CancelTaskToolSuccess,
    GetSubtaskToolResponse,
    GetSubtaskToolSuccess,
    ListSubtasksToolResponse,
    ListSubtasksToolSuccess,
    PlanSubtasksToolResponse,
    PlanSubtasksToolSuccess,
    RefineTaskToolResponse,
    RefineTaskToolSuccess,
    RestartTaskToolResponse,
    RestartTaskToolSuccess,
    ToolFailure,
)
from ergon_builtins.toolkits.subagents.toolkit import (
    SubtaskLifecycleToolkit,
    build_subtask_lifecycle_tools,
)

__all__ = [
    "AddSubtaskToolResponse",
    "AddSubtaskToolSuccess",
    "CancelTaskToolResponse",
    "CancelTaskToolSuccess",
    "GetSubtaskToolResponse",
    "GetSubtaskToolSuccess",
    "ListSubtasksToolResponse",
    "ListSubtasksToolSuccess",
    "PlanSubtasksToolResponse",
    "PlanSubtasksToolSuccess",
    "RefineTaskToolResponse",
    "RefineTaskToolSuccess",
    "RestartTaskToolResponse",
    "RestartTaskToolSuccess",
    "SubtaskLifecycleToolkit",
    "ToolFailure",
    "build_subtask_lifecycle_tools",
]
```

Use shorter equivalent shims for the other old modules.

- [x] **Step 4: Update internal imports**

Replace builtins-internal imports:

```text
ergon_builtins.workers.tool_budget          -> ergon_builtins.toolkits.common.budgets
ergon_builtins.tools.subtask_lifecycle_toolkit -> ergon_builtins.toolkits.subagents.toolkit
ergon_builtins.tools.bash_sandbox_tool      -> ergon_builtins.toolkits.subagents.sandbox_bash
ergon_builtins.tools.workflow_cli_tool      -> ergon_builtins.toolkits.workflow_cli.tool
ergon_builtins.tools.graph_toolkit          -> ergon_builtins.toolkits.resources.toolkit
ergon_builtins.tools.graph_toolkit_types    -> ergon_builtins.toolkits.resources.models
```

- [x] **Step 5: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/tools ergon_cli/tests/unit/state/test_workflow_cli_tool.py ergon_cli/tests/unit/state/test_subtask_lifecycle_toolkit.py ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py -q
```

Expected: pass.

---

### Task 14: Rename Model Infrastructure To LLM Providers

**Files:**
- Create: `ergon_builtins/ergon_builtins/llm/__init__.py`
- Create: `ergon_builtins/ergon_builtins/llm/resolution.py`
- Create: `ergon_builtins/ergon_builtins/llm/capture_settings.py`
- Create: `ergon_builtins/ergon_builtins/llm/providers/__init__.py`
- Create: `ergon_builtins/ergon_builtins/llm/providers/openrouter.py`
- Create: `ergon_builtins/ergon_builtins/llm/providers/openrouter_responses.py`
- Create: `ergon_builtins/ergon_builtins/llm/providers/transformers.py`
- Create: `ergon_builtins/ergon_builtins/llm/providers/vllm.py`
- Modify: `ergon_builtins/ergon_builtins/models/*.py`
- Modify imports in workers, common LLM judge, registry local models, and tests.
- Test: `ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py`

- [x] **Step 1: Extend layout tests**

Append:

```python
def test_llm_provider_implementation_lives_under_llm_package() -> None:
    for rel in [
        "llm/resolution.py",
        "llm/capture_settings.py",
        "llm/providers/openrouter.py",
        "llm/providers/openrouter_responses.py",
        "llm/providers/transformers.py",
        "llm/providers/vllm.py",
    ]:
        assert Path(f"ergon_builtins/ergon_builtins/{rel}").exists()


def test_old_models_modules_are_compatibility_shims_only() -> None:
    for path in [
        Path("ergon_builtins/ergon_builtins/models/resolution.py"),
        Path("ergon_builtins/ergon_builtins/models/openrouter_backend.py"),
        Path("ergon_builtins/ergon_builtins/models/openrouter_responses_backend.py"),
        Path("ergon_builtins/ergon_builtins/models/transformers_backend.py"),
        Path("ergon_builtins/ergon_builtins/models/vllm_backend.py"),
    ]:
        text = path.read_text()
        assert "compatibility import" in text
        assert "\nclass " not in text
        assert "\ndef " not in text
```

- [x] **Step 2: Move implementation modules**

Move file contents:

```text
models/resolution.py                    -> llm/resolution.py and llm/capture_settings.py
models/openrouter_backend.py            -> llm/providers/openrouter.py
models/openrouter_responses_backend.py  -> llm/providers/openrouter_responses.py
models/transformers_backend.py          -> llm/providers/transformers.py
models/vllm_backend.py                  -> llm/providers/vllm.py
```

Split provider-agnostic capture settings out of `resolution.py` into `llm/capture_settings.py`.
Update imports in moved files from `ergon_builtins.models.resolution` to `ergon_builtins.llm.resolution`.

- [x] **Step 3: Add compatibility shims**

Example:

```python
"""Deprecated compatibility import for ``ergon_builtins.llm.resolution``."""

from ergon_builtins.llm.capture_settings import capture_model_settings_for
from ergon_builtins.llm.resolution import (
    ResolvedModel,
    register_model_backend,
    registered_model_backend_prefixes,
    resolve_model_target,
)

__all__ = [
    "ResolvedModel",
    "capture_model_settings_for",
    "register_model_backend",
    "registered_model_backend_prefixes",
    "resolve_model_target",
]
```

- [x] **Step 4: Update internal imports**

Replace builtins-internal imports:

```text
ergon_builtins.models.resolution                    -> ergon_builtins.llm.resolution / ergon_builtins.llm.capture_settings
ergon_builtins.models.transformers_backend          -> ergon_builtins.llm.providers.transformers
ergon_builtins.models.openrouter_backend            -> ergon_builtins.llm.providers.openrouter
ergon_builtins.models.openrouter_responses_backend  -> ergon_builtins.llm.providers.openrouter_responses
ergon_builtins.models.vllm_backend                  -> ergon_builtins.llm.providers.vllm
```

- [x] **Step 5: Verify**

Run:

```bash
uv run pytest ergon_builtins/tests/unit/builtins/common/test_capture_settings.py ergon_builtins/tests/unit/workers/test_react_worker_contract.py ergon_builtins/tests/unit/architecture/test_builtin_domain_layout.py -q
```

Expected: pass.

---

### Task 15: Final TODO Sweep And PR 4 Verification

**Files:**
- All files touched above.

- [x] **Step 1: Confirm TODOs are gone or intentionally outside PR 4**

Run:

```bash
rg -n "TODO|todo|FIXME|XXX" ergon_builtins/ergon_builtins
```

Expected: no TODOs from the inventory remain. If a new TODO is intentionally retained, replace it with a tracked issue/RFC reference; do not leave casual cleanup comments in builtins.

- [x] **Step 2: Run focused builtins tests**

Run:

```bash
uv run pytest \
  ergon_builtins/tests/unit/architecture \
  ergon_builtins/tests/unit/benchmarks \
  ergon_builtins/tests/unit/state \
  ergon_builtins/tests/unit/tools \
  ergon_builtins/tests/unit/workers \
  -q
```

Expected: pass.

- [x] **Step 3: Run stack-level checks**

Run:

```bash
uv run ruff check ergon_builtins ergon_core ergon_cli ergon_infra ergon_ingestion tests scripts --output-format concise
uv run ty check ergon_core/ergon_core ergon_builtins/ergon_builtins ergon_cli/ergon_cli ergon_infra ergon_ingestion/ergon_ingestion
```

Expected: pass.

- [x] **Step 4: Commit on PR 4**

Commit only on `codex/builtins-pr04-benchmark-domains-v2`:

```bash
git add ergon_builtins/ergon_builtins ergon_builtins/tests/unit docs/superpowers/plans/2026-05-19-builtins-pr04-todo-cleanup.md
git commit --amend --no-edit
```

- [x] **Step 5: Push PR 4**

Run:

```bash
git push --force-with-lease origin codex/builtins-pr04-benchmark-domains-v2:codex/builtins-pr04-benchmark-domains
```

Expected: PR #87 updates only; PRs #84-#86 remain unchanged.

---

## Self-Review

**Spec coverage:** Every TODO found in the supplied worktree maps to a task above. The subtask containment TODO is resolved as stale because core `WorkerContext` already enforces containment; the plan strengthens the builtins test and updates docs instead of duplicating core checks.

**Placeholder scan:** The plan contains no implementation placeholders; each task gives concrete target files, expected tests, and the intended code shape.

**Type consistency:** Runtime tool builders use `Sandbox` and `Task[Any]` consistently. Criterion construction uses canonical `score_spec`; raw HF `max_score` fields are normalized only by GDPEval dataset-loading models.

# Evaluation Resource Context and Scoring Patch Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make evaluator criteria fetch their own task-scoped resources, judge final artifacts rather than assistant summaries, and preserve evaluator-normalized scores without double-normalizing.

**Architecture:** Core remains benchmark-agnostic: it exposes task-scoped resource access through `CriterionRuntime`. Benchmark criteria in `ergon_builtins` decide which resources to read, how to sort final outputs vs scratch files, and what to show verifiers or LLM judges. Evaluation persistence assumes all evaluators return normalized scalar task scores.

**Tech Stack:** Python, Pydantic models, SQLModel, Ergon `CriterionRuntime`, ResearchRubrics LLM judge, real-LLM rollout artifacts.

---

## Code Change Map

- Modify: `ergon_core/ergon_core/api/criterion_runtime.py`
  - Add optional `task_execution_id` to `list_resources`.
  - Add `read_resource_by_id` so criteria can read exact SQL rows after listing.

- Modify: `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`
  - Implement optional task-execution scoping for `list_resources`.
  - Implement `read_resource_by_id`.
  - Keep core generic: no final-vs-scratch classification here.

- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py`
  - Fetch resources from `context.runtime`.
  - Classify ResearchRubrics final outputs vs scratch files locally.
  - Build the judge prompt from resource content plus final assistant message.
  - Record `evaluated_resource_ids` and `evaluation_input`.

- Modify: `ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py`
  - Stop re-normalizing `TaskEvaluationResult.score`.
  - Store `summary.normalized_score = result.score`.

- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py`
  - Keep existing ResearchRubrics formula, but clarify metadata with normalized score semantics.

- Modify: `tests/real_llm/artifact_health.py`
  - Detect missing final output via task-scoped resource rows and final-output provenance, not durable blob `file_path`.

- Tests:
  - `tests/unit/state/test_criterion_runtime_di.py`
  - `tests/unit/state/test_research_rubrics_benchmark.py`
  - `tests/unit/runtime/test_evaluation_summary_contracts.py`
  - `tests/unit/runtime/test_real_llm_rollout_artifact_health.py`

---

## Task 1: Extend Core Runtime Resource Access

**Files:**
- Modify: `ergon_core/ergon_core/api/criterion_runtime.py`
- Modify: `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`
- Test: `tests/unit/state/test_criterion_runtime_di.py`

### Rationale

Criteria should own context selection. Core should only provide generic resource primitives:

- list resources for the evaluated task execution by default;
- optionally list resources for an explicit task execution id;
- read exact resources by id to avoid name collisions.

Core must not know about ResearchRubrics final reports, scratchpads, or judge prompt layout.

### Patch: Public Protocol

In `ergon_core/ergon_core/api/criterion_runtime.py`, add `UUID` under `TYPE_CHECKING` or as a normal import. Since Protocol signatures need the type at runtime under postponed annotations are not enabled in this file, use a normal import:

```python
from uuid import UUID
```

Change the resource methods:

```python
# ── resource I/O ──────────────────────────────────────────────────
async def read_resource(self, name: str) -> bytes: ...
async def read_resource_by_id(self, resource_id: UUID) -> bytes: ...
async def list_resources(
    self,
    task_execution_id: UUID | None = None,
) -> "list[RunResourceView]": ...
async def get_all_files_for_task(self) -> "dict[str, bytes]":
    """Return ``{name: bytes}`` for every resource produced by this task.

    Scoped to the runtime's evaluator-bound task execution. On duplicate
    ``name`` s, the newest ``created_at`` wins. Not size-capped.
    """
    ...
```

### Patch: Concrete Runtime

In `ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py`, keep the existing SQLModel imports:

```python
from sqlmodel import Session, desc, select
```

Add exact-id reading after `read_resource`:

```python
async def read_resource_by_id(self, resource_id: UUID) -> bytes:
    """Read one worker-published blob by its RunResource primary key."""
    with get_session() as session:
        row = session.get(RunResource, resource_id)

    if row is None or row.run_id != self._run_id:
        raise ResourceNotFoundError(
            f"No run_resource {resource_id!s} for run {self._run_id}"
        )

    result = Path(row.file_path).read_bytes()
    logger.info(
        "criterion read_resource_by_id run_id=%s resource_id=%s size_bytes=%d",
        self._run_id,
        resource_id,
        len(result),
    )
    return result
```

Replace `list_resources` with task-aware behavior:

```python
async def list_resources(
    self,
    task_execution_id: UUID | None = None,
) -> list[RunResourceView]:
    """Return resource DTOs for this run, newest first.

    Defaults to this runtime's evaluated task execution. Passing
    ``task_execution_id`` lets a benchmark criterion inspect a related task
    explicitly without core knowing benchmark semantics.
    """
    effective_execution_id = (
        task_execution_id if task_execution_id is not None else self._task_id
    )
    with get_session() as session:
        stmt = select(RunResource).where(RunResource.run_id == self._run_id)
        if effective_execution_id is not None:
            stmt = stmt.where(RunResource.task_execution_id == effective_execution_id)
        stmt = stmt.order_by(desc(RunResource.created_at))
        rows = list(session.exec(stmt).all())
    return [RunResourceView.from_row(r) for r in rows]
```

### Tests

In `tests/unit/state/test_criterion_runtime_di.py`, update the protocol test expected method set:

```python
expected = {
    "ensure_sandbox",
    "upload_files",
    "write_file",
    "run_command",
    "execute_code",
    "cleanup",
    "read_resource",
    "read_resource_by_id",
    "list_resources",
    "get_all_files_for_task",
    "db_read_session",
    "event_sink",
}
```

Add tests:

```python
@pytest.mark.asyncio
async def test_list_resources_defaults_to_runtime_task_execution() -> None:
    task_execution_id = uuid4()
    runtime = _make_runtime(task_id=task_execution_id)

    mock_row = MagicMock()
    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.exec.return_value.all.return_value = [mock_row]

    with (
        patch(
            "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
            return_value=mock_session,
        ),
        patch.object(RunResourceView, "from_row", return_value=MagicMock()) as mock_from_row,
    ):
        result = await runtime.list_resources()

    assert len(result) == 1
    mock_from_row.assert_called_once_with(mock_row)
    # Keep this assertion broad: SQLModel statements are hard to compare, but
    # this ensures a DB query was issued through the runtime path.
    mock_session.exec.assert_called_once()
```

```python
@pytest.mark.asyncio
async def test_read_resource_by_id_reads_exact_blob(tmp_path: Path) -> None:
    blob = tmp_path / "abc"
    blob.write_bytes(b"exact-resource")

    run_id = uuid4()
    resource_id = uuid4()
    row = MagicMock()
    row.id = resource_id
    row.run_id = run_id
    row.file_path = str(blob)

    runtime = _make_runtime(run_id=run_id)

    mock_session = MagicMock()
    mock_session.__enter__ = MagicMock(return_value=mock_session)
    mock_session.__exit__ = MagicMock(return_value=False)
    mock_session.get.return_value = row

    with patch(
        "ergon_core.core.runtime.evaluation.criterion_runtime.get_session",
        return_value=mock_session,
    ):
        result = await runtime.read_resource_by_id(resource_id)

    assert result == b"exact-resource"
```

Run:

```bash
uv run pytest tests/unit/state/test_criterion_runtime_di.py -q
```

Expected: all tests pass.

---

## Task 2: Make ResearchRubrics Criterion Fetch and Package Its Own Evidence

**Files:**
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py`
- Test: `tests/unit/state/test_research_rubrics_benchmark.py`

### Rationale

ResearchRubrics should judge the actual task artifacts, not the final assistant summary. The built-in criterion should use the generic runtime to fetch resources, then apply ResearchRubrics-specific evidence policy:

- final outputs first;
- scratch/intermediate resources second;
- final assistant message as status/context only.

### Patch

Add imports:

```python
from uuid import UUID

from ergon_core.api.run_resource import RunResourceView
```

Add constants and a small local evidence type:

```python
_MAX_RESOURCE_CHARS = 30_000
_FINAL_OUTPUT_PREFIX = "/workspace/final_output/"


class _ResourceEvidence(BaseModel):
    model_config = {"frozen": True, "arbitrary_types_allowed": True}

    resource: RunResourceView
    content: str

    @property
    def resource_id(self) -> str:
        return str(self.resource.id)
```

Change `evaluate`:

```python
async def evaluate(self, context: EvaluationContext) -> CriterionResult:
    final_outputs, scratch_outputs = await _load_researchrubrics_evidence(context)
    user_prompt = _build_user_prompt(
        context,
        final_outputs=final_outputs,
        scratch_outputs=scratch_outputs,
    )
    verdict = await call_structured_judge(
        messages=[
            JudgeMessage(role="system", content=self.system_prompt),
            JudgeMessage(role="user", content=user_prompt),
        ],
        response_type=ResearchRubricsVerdict,
        model=self.model,
    )
    evaluated_resource_ids = [
        evidence.resource_id for evidence in [*final_outputs, *scratch_outputs]
    ]
    return CriterionResult(
        name=self.name,
        score=self.max_score if verdict.passed else 0.0,
        passed=verdict.passed,
        weight=self.weight,
        feedback=verdict.reasoning,
        evaluation_input=_summarize_evaluation_input(
            final_outputs=final_outputs,
            scratch_outputs=scratch_outputs,
            final_assistant_message=context.worker_result.output,
        ),
        evaluated_resource_ids=evaluated_resource_ids,
        metadata={
            "primary_evidence_resource_ids": [e.resource_id for e in final_outputs],
            "scratch_evidence_resource_ids": [e.resource_id for e in scratch_outputs],
        },
    )
```

Add evidence loading helpers:

```python
async def _load_researchrubrics_evidence(
    context: EvaluationContext,
) -> tuple[list[_ResourceEvidence], list[_ResourceEvidence]]:
    if context.runtime is None:
        return [], []

    resources = await context.runtime.list_resources()
    final_resources = [resource for resource in resources if _is_final_output_resource(resource)]
    scratch_resources = [resource for resource in resources if resource not in final_resources]

    final_outputs = await _read_text_resources(context, final_resources)
    scratch_outputs = await _read_text_resources(context, scratch_resources)
    return final_outputs, scratch_outputs
```

```python
async def _read_text_resources(
    context: EvaluationContext,
    resources: list[RunResourceView],
) -> list[_ResourceEvidence]:
    if context.runtime is None:
        return []

    evidence: list[_ResourceEvidence] = []
    for resource in resources:
        if not _is_text_like(resource):
            continue
        content_bytes = await context.runtime.read_resource_by_id(resource.id)
        content = content_bytes.decode("utf-8", errors="replace")
        if len(content) > _MAX_RESOURCE_CHARS:
            content = content[:_MAX_RESOURCE_CHARS] + "\n\n[truncated]"
        evidence.append(_ResourceEvidence(resource=resource, content=content))
    return evidence
```

```python
def _is_text_like(resource: RunResourceView) -> bool:
    return (
        resource.mime_type.startswith("text/")
        or resource.mime_type in {"application/json", "application/x-ndjson"}
        or resource.name.endswith((".md", ".txt", ".json", ".jsonl", ".csv"))
    )
```

```python
def _is_final_output_resource(resource: RunResourceView) -> bool:
    origin = resource.metadata.get("sandbox_origin")
    return isinstance(origin, str) and origin.startswith(_FINAL_OUTPUT_PREFIX)
```

Replace `_build_user_prompt`:

```python
def _build_user_prompt(
    context: EvaluationContext,
    *,
    final_outputs: list[_ResourceEvidence],
    scratch_outputs: list[_ResourceEvidence],
) -> str:
    return "\n\n".join(
        [
            f"Original research request:\n{context.task.description}",
            _format_resource_section(
                "Final output resources (primary answer to judge)",
                final_outputs,
                empty="No final output resources were published.",
            ),
            _format_resource_section(
                "Scratch/intermediate resources (supporting context; do not treat as final answer)",
                scratch_outputs,
                empty="No scratch resources were published.",
            ),
            (
                "Final assistant message (execution summary/status, not the primary answer):\n"
                f"{context.worker_result.output}"
            ),
        ]
    )
```

Add format helpers:

```python
def _format_resource_section(
    title: str,
    resources: list[_ResourceEvidence],
    *,
    empty: str,
) -> str:
    if not resources:
        return f"{title}:\n{empty}"
    blocks = [f"{title}:"]
    for evidence in resources:
        resource = evidence.resource
        origin = resource.metadata.get("sandbox_origin")
        blocks.append(
            "\n".join(
                [
                    f"--- resource_id={resource.id} name={resource.name} kind={resource.kind}",
                    f"mime_type={resource.mime_type} sandbox_origin={origin}",
                    evidence.content,
                ]
            )
        )
    return "\n\n".join(blocks)
```

```python
def _summarize_evaluation_input(
    *,
    final_outputs: list[_ResourceEvidence],
    scratch_outputs: list[_ResourceEvidence],
    final_assistant_message: str,
) -> str:
    return "\n".join(
        [
            "Evidence used by ResearchRubrics judge:",
            "final_outputs="
            + ", ".join(f"{e.resource.name}:{e.resource.id}" for e in final_outputs),
            "scratch_outputs="
            + ", ".join(f"{e.resource.name}:{e.resource.id}" for e in scratch_outputs),
            "final_assistant_message="
            + final_assistant_message[:1000],
        ]
    )
```

### Tests

In `tests/unit/state/test_research_rubrics_benchmark.py`, add a fake runtime and direct unit test for the criterion.

```python
class _Runtime:
    def __init__(self, resources, blobs):
        self._resources = resources
        self._blobs = blobs

    async def list_resources(self, task_execution_id=None):
        return self._resources

    async def read_resource_by_id(self, resource_id):
        return self._blobs[resource_id]
```

Patch `call_structured_judge` and assert:

```python
@pytest.mark.asyncio
async def test_researchrubrics_judge_uses_final_resource_content(monkeypatch):
    from uuid import uuid4
    from ergon_core.api.evaluation_context import EvaluationContext
    from ergon_core.api.results import WorkerOutput
    from ergon_core.api.run_resource import RunResourceKind, RunResourceView
    from ergon_builtins.benchmarks.researchrubrics.judge_criterion import (
        ResearchRubricsJudgeCriterion,
        ResearchRubricsVerdict,
    )

    report_id = uuid4()
    scratch_id = uuid4()
    run_id = uuid4()
    execution_id = uuid4()
    report = RunResourceView(
        id=report_id,
        run_id=run_id,
        task_execution_id=execution_id,
        kind=RunResourceKind.REPORT,
        name="report.md",
        mime_type="text/markdown",
        file_path="/tmp/blob/report",
        size_bytes=12,
        content_hash="abc",
        error=None,
        metadata={"sandbox_origin": "/workspace/final_output/report.md"},
    )
    scratch = RunResourceView(
        id=scratch_id,
        run_id=run_id,
        task_execution_id=execution_id,
        kind=RunResourceKind.NOTE,
        name="notes.md",
        mime_type="text/markdown",
        file_path="/tmp/blob/notes",
        size_bytes=5,
        content_hash="def",
        error=None,
        metadata={"sandbox_origin": "/workspace/scratch/notes.md"},
    )
    captured = {}

    async def fake_judge(*, messages, response_type, model):
        captured["prompt"] = messages[1].content
        return ResearchRubricsVerdict(reasoning="report satisfies criterion", passed=True)

    monkeypatch.setattr(
        "ergon_builtins.benchmarks.researchrubrics.judge_criterion.call_structured_judge",
        fake_judge,
    )

    criterion = ResearchRubricsJudgeCriterion(
        name="criterion_0",
        rubric=RubricCriterion(criterion="Includes sources.", axis="Explicit", weight=2.0),
    )
    task = BenchmarkTask(
        task_slug="sample",
        instance_key="default",
        description="Write a report.",
    )
    context = EvaluationContext(
        run_id=run_id,
        task_id=uuid4(),
        execution_id=execution_id,
        task=task,
        worker_result=WorkerOutput(output="Wrote report.md"),
        runtime=_Runtime(
            [report, scratch],
            {
                report_id: b"# Findings\nFinal report text",
                scratch_id: b"draft notes",
            },
        ),
    )

    result = await criterion.evaluate(context)

    assert result.passed is True
    assert str(report_id) in result.evaluated_resource_ids
    assert str(scratch_id) in result.evaluated_resource_ids
    assert "Final output resources" in captured["prompt"]
    assert "Final report text" in captured["prompt"]
    assert "Scratch/intermediate resources" in captured["prompt"]
    assert "draft notes" in captured["prompt"]
```

Run:

```bash
uv run pytest tests/unit/state/test_research_rubrics_benchmark.py -q
```

Expected: all tests pass.

---

## Task 3: Align Rollout Artifact Health With Task-Scoped Final Outputs

**Files:**
- Modify: `tests/real_llm/artifact_health.py`
- Test: `tests/unit/runtime/test_real_llm_rollout_artifact_health.py`

### Rationale

Health analysis works on dumped JSONL, not live SQL. It should mirror the same policy:

- group resources by `task_execution_id`;
- a completed task has a final output if at least one resource has `metadata_json.sandbox_origin` under `/workspace/final_output/`;
- do not compare durable blob `file_path` to logical sandbox paths.

### Patch

In `tests/real_llm/artifact_health.py`, add helpers near `_tool_budget_signals`:

```python
_FINAL_OUTPUT_PREFIX = "/workspace/final_output/"


def _resource_metadata(resource: dict[str, Any]) -> dict[str, Any]:  # slopcop: ignore[no-typing-any]
    metadata = resource.get("metadata_json") or resource.get("metadata") or {}
    if isinstance(metadata, str):
        return json.loads(metadata)
    return metadata if isinstance(metadata, dict) else {}


def _is_final_output_resource(resource: dict[str, Any]) -> bool:  # slopcop: ignore[no-typing-any]
    origin = _resource_metadata(resource).get("sandbox_origin")
    return isinstance(origin, str) and origin.startswith(_FINAL_OUTPUT_PREFIX)
```

Replace current `missing_final_report` calculation:

```python
completed_execution_ids = {
    str(execution.get("id"))
    for execution in executions
    if execution.get("status") == "completed" and execution.get("id") is not None
}
final_output_execution_ids = {
    str(resource.get("task_execution_id"))
    for resource in resources
    if resource.get("task_execution_id") is not None and _is_final_output_resource(resource)
}
missing_final_report = bool(completed_execution_ids - final_output_execution_ids)
```

This field name can stay `missing_final_report` for now to avoid dashboard churn, but the semantics become “completed task is missing a final-output resource.”

### Tests

In `tests/unit/runtime/test_real_llm_rollout_artifact_health.py`, update `_write_minimal_rollout` to optionally write final-output metadata:

```python
def _write_minimal_rollout(
    root: Path,
    *,
    task_count: int = 1,
    evaluation_rows: list[dict] | None = None,
    resource_rows: list[dict] | None = None,
) -> None:
    ...
    execution_ids = [str(uuid4()) for _ in range(task_count)]
    ...
    _write_jsonl(
        db / "run_task_executions.jsonl",
        [
            {
                "id": execution_ids[idx],
                "task_slug": f"task-{idx}",
                "status": "completed",
            }
            for idx in range(task_count)
        ],
    )
    ...
    _write_jsonl(
        db / "run_resources.jsonl",
        resource_rows
        if resource_rows is not None
        else [
            {
                "id": str(uuid4()),
                "task_execution_id": execution_ids[0],
                "name": "report.md",
                "metadata_json": {"sandbox_origin": "/workspace/final_output/report.md"},
            }
        ],
    )
```

Add:

```python
def test_artifact_health_detects_final_output_by_task_resource_metadata(tmp_path: Path) -> None:
    execution_id = str(uuid4())
    _write_minimal_rollout(
        tmp_path,
        task_count=1,
        evaluation_rows=[
            {
                "id": str(uuid4()),
                "score": 0.75,
                "summary_json": {
                    "evaluator_name": "research-rubric",
                    "normalized_score": 0.75,
                    "criterion_results": [
                        {
                            "criterion_name": "criterion_0",
                            "criterion_type": "researchrubrics-llm-judge",
                            "score": 1.0,
                            "max_score": 1.0,
                            "passed": True,
                            "weight": 1.0,
                            "status": "passed",
                            "criterion_description": "Includes citations.",
                            "feedback": "The report cited source material.",
                        }
                    ],
                },
            }
        ],
        resource_rows=[
            {
                "id": str(uuid4()),
                "task_execution_id": execution_id,
                "name": "report.md",
                "file_path": "/tmp/ergon-blob/abc",
                "metadata_json": {"sandbox_origin": "/workspace/final_output/report.md"},
            }
        ],
    )
```

If `_write_minimal_rollout` generates execution ids internally, return them from the helper or pass explicit ids. Keep the test focused: final-output detection must use `metadata_json.sandbox_origin`, not durable `file_path`.

Run:

```bash
uv run pytest tests/unit/runtime/test_real_llm_rollout_artifact_health.py tests/real_llm/test_artifact_health.py -q
```

Expected: all tests pass.

---

## Task 4: Preserve Evaluator-Normalized Scores

**Files:**
- Modify: `ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py`
- Modify: `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py`
- Test: `tests/unit/runtime/test_evaluation_summary_contracts.py`
- Test: `tests/unit/state/test_research_rubrics_benchmark.py`

### Rationale

New standard: all evaluators return normalized scalar scores in `TaskEvaluationResult.score`. Persistence must record, not reinterpret, that score.

Current bug:

```python
total_score = result.score
normalized = total_score / max_score_total if max_score_total > 0 else 0.0
```

For ResearchRubrics, `result.score` is already normalized, so this divides twice.

### Patch: Persistence

In `build_evaluation_summary`, replace:

```python
total_score = result.score
normalized = total_score / max_score_total if max_score_total > 0 else 0.0
```

with:

```python
normalized = result.score
```

Keep `max_score_total` as rubric display metadata:

```python
return EvaluationSummary(
    evaluator_name=result.evaluator_name,
    max_score=max_score_total,
    normalized_score=normalized,
    stages_evaluated=len(stage_names),
    stages_passed=stages_passed,
    criterion_results=entries,
)
```

### Patch: ResearchRubrics Metadata

In `ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py`, keep the formula and add explicit score metadata:

```python
return TaskEvaluationResult(
    task_slug=task.task_slug,
    score=normalized_score,
    passed=total_score > 0,
    evaluator_name=self.name,
    criterion_results=results,
    metadata={
        "score_scale": "normalized_0_1",
        "raw_score": total_score,
        "max_possible": max_possible,
        "min_possible": min_possible,
    },
)
```

### Tests

In `tests/unit/runtime/test_evaluation_summary_contracts.py`, add:

```python
def test_build_evaluation_summary_preserves_evaluator_normalized_score() -> None:
    summary = build_evaluation_summary(
        _service_result(
            feedback="criterion ran",
            criterion_score=0.5,
            criterion_weight=2.0,
            passed=True,
        ),
        evaluation_input=None,
    )

    assert summary.normalized_score == 0.5
    assert summary.max_score == 1.0
```

To make this test prove the no-double-normalization contract, change the helper's `CriterionSpec` for this test case from `max_score=1.0` to `max_score=2.0`. With the old implementation, `summary.normalized_score` would be `0.25`; with the new contract, it remains `0.5`.

In `tests/unit/state/test_research_rubrics_benchmark.py`, update expected metadata:

```python
assert result.metadata == {
    "score_scale": "normalized_0_1",
    "raw_score": 2.0,
    "max_possible": 2.0,
    "min_possible": -1.0,
}
```

Run:

```bash
uv run pytest tests/unit/runtime/test_evaluation_summary_contracts.py tests/unit/state/test_research_rubrics_benchmark.py -q
```

Expected: all tests pass.

---

## Task 5: Verify With One Real Rollout

**Files:**
- No new code files.

### Commands

Run focused checks:

```bash
uv run pytest \
  tests/unit/state/test_criterion_runtime_di.py \
  tests/unit/state/test_research_rubrics_benchmark.py \
  tests/unit/runtime/test_evaluation_summary_contracts.py \
  tests/unit/runtime/test_real_llm_rollout_artifact_health.py \
  tests/real_llm/test_artifact_health.py \
  -q
```

Expected: all tests pass.

Run lint/compile for touched files:

```bash
uv run ruff check \
  ergon_core/ergon_core/api/criterion_runtime.py \
  ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py \
  ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py \
  ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py \
  ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py \
  tests/real_llm/artifact_health.py \
  tests/unit/state/test_criterion_runtime_di.py \
  tests/unit/state/test_research_rubrics_benchmark.py \
  tests/unit/runtime/test_evaluation_summary_contracts.py \
  tests/unit/runtime/test_real_llm_rollout_artifact_health.py
```

Expected: `All checks passed!`

Run compile:

```bash
uv run python -m compileall -q \
  ergon_core/ergon_core/api/criterion_runtime.py \
  ergon_core/ergon_core/core/runtime/evaluation/criterion_runtime.py \
  ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py \
  ergon_builtins/ergon_builtins/benchmarks/researchrubrics/judge_criterion.py \
  ergon_builtins/ergon_builtins/benchmarks/researchrubrics/rubric.py \
  tests/real_llm/artifact_health.py
```

Expected: exit code `0`.

After rebuild, rerun one real sample:

```bash
ERGON_REAL_LLM=1 \
ERGON_REAL_LLM_MODEL=openrouter:anthropic/claude-opus-4.7 \
ERGON_REAL_LLM_WORKER=researchrubrics-workflow-cli-react \
ERGON_REAL_LLM_LIMIT=1 \
ERGON_REAL_LLM_BUDGET_USD=25 \
TEST_HARNESS_SECRET=real-llm-secret \
uv run pytest tests/real_llm/benchmarks/test_researchrubrics.py --assume-stack-up -vv -s
```

Expected rollout properties:

- terminal status is `completed`;
- artifact health reports `missing_final_report: False`;
- `normalized scores` matches `RunTaskEvaluation.score`;
- criterion `evaluated_resource_ids` contains the report resource id;
- judge feedback references details from the full final report, not just the final assistant summary.

---

## Non-Goals

- Do not put final-vs-scratch classification in `ergon_core`.
- Do not include full agent conversation in ResearchRubrics judge prompts by default.
- Do not introduce a new persisted table for evidence bundles.
- Do not preserve compatibility with double-normalized summary scores; new runs should use the normalized score invariant.

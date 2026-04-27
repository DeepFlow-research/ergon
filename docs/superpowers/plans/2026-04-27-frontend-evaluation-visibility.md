# Frontend Evaluation Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the evaluation feature set from the design brief to the dashboard: cohort rubric status pips, graph node rubric cues, skipped/error states, rubric metadata, richer evaluation drawer details, container roll-ups, and an evaluation lens.

**Implementation note:** The first implementation keeps the original API strategy: additive backend fields, frontend-derived run/container roll-ups, backend-owned cohort summaries, and stable `data-testid` coverage for cohort pips, graph rubric glyphs, the evaluation lens toggle, and criterion status details.

**Architecture:** Keep the backend read model additive and make the frontend own presentation-specific selectors in a new `features/evaluations` domain. Enrich existing `GET /runs/{run_id}` and `GET /cohorts/{cohort_id}` payloads rather than introducing a new fetch path for the first implementation. Keep E2E assertions anchored to stable `data-testid` attributes and the backend harness DTO.

**Tech Stack:** FastAPI, Pydantic DTOs, SQLModel persistence, Next.js App Router, React, TypeScript, Zod, React Flow, Playwright, pytest.

---

## RFC

### Problem

The backend now produces enough evaluation data to validate task-level correctness, but the dashboard still treats evaluation as a narrow workspace tab. The design brief expects evaluation to be visible across the debugging loop:

- Cohort rows show per-run rubric status pips and failure/skipped state at a glance.
- Graph nodes show which tasks have attached rubrics without requiring a click.
- Container nodes summarize evaluation status for their descendant tasks.
- The evaluation tab explains score composition, weights, skipped criteria, evaluator errors, input, feedback, and timing.
- Operators can switch the DAG into an evaluation lens that highlights evaluation-bearing tasks and dims unrelated work.

### Non-Goals

- Do not change evaluation execution semantics.
- Do not add interactive re-evaluation controls.
- Do not introduce a new standalone evaluation API service.
- Do not persist new relational tables unless the additive summary JSON fields prove insufficient.

### Source Of Truth

Use persisted `RunTaskEvaluation` rows and their typed `summary_json` as the source of truth. The frontend should not infer evaluation status from task status alone. It may derive roll-ups from evaluation rows and task parent/child relationships.

### Nullability And Defaults Policy

Avoid silent defaults at contract boundaries. If a field is owned by the backend and is required for rendering, make it required in the DTO and populate it explicitly in the builder. Use `None`/`null` only for genuinely absent data such as optional model reasoning, optional feedback, optional evaluation input, or optional error detail. In frontend derived state, represent "there is no evaluation evidence" as `null`, not as an all-zero roll-up object with a `"none"` sentinel.

### API Strategy

Use existing endpoints with additive fields:

- `GET /runs/{run_id}` returns the enriched `RunSnapshotDto`.
- `GET /cohorts/{cohort_id}` returns enriched `CohortRunRowDto` rows with lightweight rubric status summaries.
- `GET /api/test/read/run/{run_id}/state` returns the expanded smoke harness fields used by Playwright.

No existing response field should be removed or renamed.

### Evaluation Status Semantics

Use one canonical status vocabulary everywhere:

```python
EvalCriterionStatus = Literal["passed", "failed", "errored", "skipped"]
RubricStatusSummaryStatus = Literal["passing", "failing", "errored", "skipped", "mixed", "none"]
```

Criterion status rules:

- `errored`: `error` is non-null.
- `skipped`: criterion was part of the evaluator spec but did not execute because a prior gate failed or the attached task never reached the required lifecycle point.
- `passed`: criterion executed and `passed` is true.
- `failed`: criterion executed and `passed` is false.

Roll-up status rules:

- `none`: no evaluation rows or criteria.
- `errored`: at least one errored criterion.
- `failing`: at least one failed criterion and no errors.
- `mixed`: passed plus skipped criteria with no failed or errored criteria.
- `skipped`: all known criteria skipped.
- `passing`: all known criteria passed.

### Backend Contract Additions

Do not add parallel DTOs for data the run snapshot already exposes. The codebase already has:

- `RunEvaluationCriterionDto`
- `RunTaskEvaluationDto`
- `RunSnapshotDto.evaluations_by_task`
- `CohortRunRowDto`

The implementation should extend those existing DTOs in place. Graph glyphs, task roll-ups, container roll-ups, and run-level detail roll-ups should be derived in frontend selectors from `RunSnapshotDto.evaluations_by_task`.

The only new backend DTO shape needed for the first implementation is a lightweight cohort-row rubric status summary, because the cohort page should show pips without fetching every run snapshot. The backend should own this summary, including counts and aggregate status. Keep the implementation direct: one compact builder over persisted `EvaluationSummary` rows, not a chain of helper functions or a second generic roll-up subsystem.

Extend `ergon_core/ergon_core/core/api/schemas.py`:

```python
from typing import Literal

EvalCriterionStatus = Literal["passed", "failed", "errored", "skipped"]
```

Add fields to the existing `RunEvaluationCriterionDto` class:

```python
class RunEvaluationCriterionDto(CamelModel):
    # existing fields stay unchanged
    criterion_name: str
    status: EvalCriterionStatus
    passed: bool
    weight: float
    contribution: float
    model_reasoning: str | None = None
    skipped_reason: str | None = None
```

Add fields to the existing `RunTaskEvaluationDto` class:

```python
class RunTaskEvaluationDto(CamelModel):
    # existing fields stay unchanged
    evaluator_name: str
    aggregation_rule: str
```

Add one lightweight DTO in `ergon_core/ergon_core/core/runtime/services/cohort_schemas.py`:

```python
class CohortRubricStatusSummaryDto(BaseModel):
    status: RubricStatusSummaryStatus
    total_criteria: int
    passed: int
    failed: int
    errored: int
    skipped: int
    criterion_statuses: list[str]
    evaluator_names: list[str]


class CohortRunRowDto(BaseModel):
    # existing fields stay unchanged
    rubric_status_summary: CohortRubricStatusSummaryDto
```

### Frontend Contract Additions

The generated REST contracts feed `ergon-dashboard/src/lib/contracts/rest.ts`. After regenerating contracts, normalize only fields that are genuinely optional on the backend contract. Do not use frontend defaults to hide missing required fields such as criterion `status`, criterion `weight`, evaluator name, aggregation rule, or cohort `rubric_status_summary`.

Add frontend-only derived roll-up types in `ergon-dashboard/src/features/evaluations/contracts.ts`; do not mirror them as run-snapshot backend DTOs:

```ts
export type EvalCriterionStatus = "passed" | "failed" | "errored" | "skipped";
export type EvalRollupStatus = "passing" | "failing" | "errored" | "skipped" | "mixed";
export type RubricStatusSummaryStatus = EvalRollupStatus | "none";

export interface EvaluationRollup {
  status: EvalRollupStatus;
  totalCriteria: number;
  passed: number;
  failed: number;
  errored: number;
  skipped: number;
  normalizedScore: number;
  maxScore: number;
  evaluatorNames: string[];
  attachedTaskIds: string[];
  criterionStatuses: EvalCriterionStatus[];
}
```

Extend existing normalized REST types in `ergon-dashboard/src/lib/contracts/rest.ts`:

```ts
export interface RunEvaluationCriterion {
  id: string;
  stageNum: number;
  stageName: string;
  criterionNum: number;
  criterionType: string;
  criterionDescription: string;
  criterionName: string;
  status: EvalCriterionStatus;
  passed: boolean;
  weight: number;
  contribution: number;
  evaluationInput: string | null;
  score: number;
  maxScore: number;
  feedback: string | null;
  modelReasoning: string | null;
  skippedReason: string | null;
  evaluatedActionIds: string[];
  evaluatedResourceIds: string[];
  error: Record<string, unknown> | null;
}
```

### Frontend Domain Boundary

Create a focused evaluation domain:

```text
ergon-dashboard/src/features/evaluations/
  contracts.ts
  status.ts
  selectors.ts
  selectors.test.ts
  components/
    CriterionStatusPip.tsx
    RubricStatusStrip.tsx
    EvaluationNodeGlyph.tsx
    EvaluationRollupBadge.tsx
    EvaluationLensToggle.tsx
    EvaluationCriterionCard.tsx
    EvaluationMetadataSummary.tsx
```

Responsibilities:

- `contracts.ts`: frontend-only types if the generated REST types are too broad for component props.
- `status.ts`: colors, labels, icons, and ordering for evaluation statuses.
- `selectors.ts`: pure roll-up helpers for run, task, container descendants, and cohort rows.
- `components/*`: small visual components with stable `data-testid` attributes.

### UX Contract

Use these stable test IDs:

- `cohort-eval-strip-{run_id}`
- `cohort-eval-pip-{run_id}-{index}`
- `graph-eval-glyph-{task_id}`
- `graph-eval-rollup-{task_id}`
- `graph-eval-lens-toggle`
- `workspace-evaluation-metadata`
- `workspace-evaluation-criterion-{criterion_id}`
- `workspace-evaluation-criterion-status-{criterion_id}`
- `workspace-evaluation-input-{criterion_id}`
- `workspace-evaluation-reasoning-{criterion_id}`

### Acceptance Criteria

- Cohort run rows render a rubric status strip for runs with evaluations and an empty state for runs without evaluations.
- Graph task nodes with attached evaluations render a subtle diamond glyph using text or CSS, with an accessible label.
- Expanded graph containers render a roll-up badge computed from descendant task evaluations.
- Evaluation lens dims non-evaluated tasks and highlights tasks with direct or descendant evaluation evidence.
- Evaluation panel shows aggregation rule, weights, score contribution, status, input, feedback, model reasoning, skipped reasons, and error details.
- Existing smoke specs assert happy-path passing pips, sad-path failed/skipped/errored visibility, graph glyphs, and the evaluation drawer.

---

## File Structure

### Backend Files

- Modify `ergon_core/ergon_core/core/api/schemas.py`: extend existing evaluation DTO fields only.
- Modify `ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py`: persist criterion `status`, optional `model_reasoning`, and optional `skipped_reason` in `summary_json`.
- Modify `ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py`: build criterion status, contribution, and model reasoning from `CriterionResult.metadata`.
- Modify `ergon_core/ergon_core/core/api/runs.py`: pass enriched criterion fields through existing `evaluations_by_task`.
- Modify `ergon_core/ergon_core/core/runtime/services/run_read_service.py`: keep using existing `evaluations_by_task`; no new run-snapshot roll-up fields.
- Modify `ergon_core/ergon_core/core/runtime/services/cohort_schemas.py`: add `rubric_status_summary` to cohort run rows.
- Modify `ergon_core/ergon_core/core/runtime/services/cohort_service.py`: query run evaluations and attach a backend-owned rubric status summary.
- Modify `ergon_core/ergon_core/core/api/test_harness.py`: expose criterion statuses and a lightweight run rubric status summary to Playwright smoke tests.
- Test `tests/unit/runtime/test_evaluation_summary_contracts.py`: assert enriched summary fields.
- Test `tests/unit/runtime/test_cohort_rubric_status_summary.py`: assert cohort row rubric status summary.

### Frontend Files

- Regenerate `ergon-dashboard/src/generated/rest/contracts.ts` after backend schema updates.
- Modify `ergon-dashboard/src/lib/contracts/rest.ts`: normalize additive evaluation fields.
- Modify `ergon-dashboard/src/lib/types.ts`: export enriched evaluation aliases only.
- Modify `ergon-dashboard/src/lib/runState.ts`: deserialize enriched existing evaluations only.
- Create `ergon-dashboard/src/features/evaluations/status.ts`: central status display mapping.
- Create `ergon-dashboard/src/features/evaluations/selectors.ts`: pure derived state helpers.
- Test `ergon-dashboard/src/features/evaluations/selectors.test.ts`: assert direct and container roll-ups.
- Create `ergon-dashboard/src/features/evaluations/components/CriterionStatusPip.tsx`.
- Create `ergon-dashboard/src/features/evaluations/components/RubricStatusStrip.tsx`.
- Create `ergon-dashboard/src/features/evaluations/components/EvaluationNodeGlyph.tsx`.
- Create `ergon-dashboard/src/features/evaluations/components/EvaluationRollupBadge.tsx`.
- Create `ergon-dashboard/src/features/evaluations/components/EvaluationLensToggle.tsx`.
- Create `ergon-dashboard/src/features/evaluations/components/EvaluationCriterionCard.tsx`.
- Create `ergon-dashboard/src/features/evaluations/components/EvaluationMetadataSummary.tsx`.
- Modify `ergon-dashboard/src/components/cohorts/CohortDetailView.tsx`: render cohort run rubric status strips.
- Modify `ergon-dashboard/src/components/dag/TaskNode.tsx`: pass evaluation roll-up props.
- Modify `ergon-dashboard/src/features/graph/components/LeafNode.tsx`: render glyph and roll-up badge.
- Modify `ergon-dashboard/src/features/graph/components/ContainerNode.tsx`: render container roll-up badge.
- Modify `ergon-dashboard/src/components/dag/DAGCanvas.tsx`: add evaluation lens toggle and graph dimming behavior.
- Modify `ergon-dashboard/src/components/panels/EvaluationPanel.tsx`: render richer metadata and criterion cards.
- Modify `ergon-dashboard/tests/helpers/backendHarnessClient.ts`: expand backend harness DTO.
- Modify `ergon-dashboard/tests/e2e/_shared/smoke.ts`: assert the visible evaluation features.

---

## Implementation Tasks

### Task 1: Backend Evaluation Read Contract

**Files:**
- Modify: `ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py`
- Modify: `ergon_core/ergon_core/core/api/schemas.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py`
- Test: `tests/unit/runtime/test_evaluation_summary_contracts.py`

- [ ] **Step 1: Write failing summary contract tests**

Add tests that prove the persistence DTO carries status, weights, contribution, and optional reasoning:

```python
def test_build_evaluation_summary_includes_status_weight_and_contribution() -> None:
    result = _service_result(
        criterion_score=0.5,
        criterion_weight=2.0,
        passed=False,
        metadata={"model_reasoning": "missing supporting artifact"},
    )

    summary = build_evaluation_summary(result, evaluation_input="task evidence")

    entry = summary.criterion_results[0]
    assert entry.status == "failed"
    assert entry.weight == 2.0
    assert entry.contribution == 0.5
    assert entry.model_reasoning == "missing supporting artifact"
    assert entry.skipped_reason is None


def test_dashboard_evaluation_dto_includes_criterion_status_fields() -> None:
    summary = EvaluationSummary(
        evaluator_name="post-root",
        max_score=1.0,
        normalized_score=1.0,
        stages_evaluated=1,
        stages_passed=1,
        criterion_results=[
            CriterionResultEntry(
                criterion_name="timing",
                criterion_type="smoke-post-root-timing-criterion",
                criterion_description="post root timing",
                status="passed",
                score=1.0,
                max_score=1.0,
                passed=True,
                weight=1.0,
                contribution=1.0,
            )
        ],
    )

    dto = build_dashboard_evaluation_dto(
        evaluation_id=UUID("00000000-0000-0000-0000-000000000001"),
        run_id=UUID("00000000-0000-0000-0000-000000000002"),
        task_id=UUID("00000000-0000-0000-0000-000000000003"),
        total_score=1.0,
        created_at=datetime(2026, 4, 27, tzinfo=UTC),
        summary=summary,
    )

    criterion = dto.criterion_results[0]
    assert criterion.status == "passed"
    assert criterion.passed is True
    assert criterion.weight == 1.0
    assert criterion.contribution == 1.0
    assert dto.evaluator_name == "post-root"
    assert dto.aggregation_rule == "weighted_sum"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `pytest tests/unit/runtime/test_evaluation_summary_contracts.py -q`

Expected: failure mentioning missing fields such as `status`, `contribution`, or `evaluator_name`.

- [ ] **Step 3: Add typed persistence fields**

In `evaluation_summary.py`, extend `CriterionResultEntry`:

```python
class CriterionResultEntry(BaseModel):
    """One criterion result as stored in the evaluation summary."""

    criterion_name: str
    criterion_type: str
    stage_num: int
    stage_name: str
    criterion_num: int
    status: Literal["passed", "failed", "errored", "skipped"]
    score: float
    max_score: float
    passed: bool
    weight: float
    contribution: float
    criterion_description: str
    feedback: str | None = None
    model_reasoning: str | None = None
    skipped_reason: str | None = None
    evaluation_input: str | None = None
    evaluated_action_ids: list[str] = Field(default_factory=list)
    evaluated_resource_ids: list[str] = Field(default_factory=list)
    error: dict | None = None
```

- [ ] **Step 4: Add DTO fields**

In `schemas.py`, update `RunEvaluationCriterionDto` and `RunTaskEvaluationDto` with the RFC contract fields.

- [ ] **Step 5: Build status and metadata in persistence**

In `evaluation_persistence_service.py`, add a helper:

```python
def _criterion_status(*, passed: bool, error: dict | None) -> str:
    if error is not None:
        return "errored"
    return "passed" if passed else "failed"
```

Then populate the entry:

```python
metadata = cr.metadata
model_reasoning = metadata.get("model_reasoning")
entries.append(
    CriterionResultEntry(
        criterion_name=cr.name,
        criterion_type=spec.criterion.type_slug,
        criterion_description=spec.criterion.name,
        stage_num=spec.stage_idx,
        stage_name=spec.stage_name,
        criterion_num=spec.criterion_idx,
        status=_criterion_status(passed=cr.passed, error=None),
        score=cr.score,
        max_score=spec.max_score,
        passed=cr.passed,
        weight=cr.weight,
        contribution=cr.score,
        feedback=cr.feedback,
        model_reasoning=model_reasoning if isinstance(model_reasoning, str) else None,
        evaluation_input=evaluation_input,
    )
)
```

- [ ] **Step 6: Run tests and verify pass**

Run: `pytest tests/unit/runtime/test_evaluation_summary_contracts.py -q`

Expected: all tests pass.

- [ ] **Step 7: Commit**

```bash
git add ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py ergon_core/ergon_core/core/api/schemas.py ergon_core/ergon_core/core/runtime/services/evaluation_persistence_service.py tests/unit/runtime/test_evaluation_summary_contracts.py
git commit -m "feat: enrich evaluation read contract"
```

### Task 2: Backend Cohort Rubric Status Summary

**Files:**
- Modify: `ergon_core/ergon_core/core/api/runs.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/run_read_service.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/cohort_schemas.py`
- Modify: `ergon_core/ergon_core/core/runtime/services/cohort_service.py`
- Modify: `ergon_core/ergon_core/core/api/test_harness.py`
- Test: `tests/unit/runtime/test_cohort_rubric_status_summary.py`

- [ ] **Step 1: Write failing cohort rubric summary tests**

Create `tests/unit/runtime/test_cohort_rubric_status_summary.py`:

```python
def test_cohort_run_row_includes_rubric_status_summary(session: Session) -> None:
    cohort, run, node = _persist_run_with_one_failed_evaluation(session)

    detail = experiment_cohort_service.get_detail(cohort.id)

    assert detail is not None
    row = detail.runs[0]
    assert row.rubric_status_summary.status == "failing"
    assert row.rubric_status_summary.total_criteria == 1
    assert row.rubric_status_summary.failed == 1
    assert row.rubric_status_summary.criterion_statuses == ["failed"]
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
pytest tests/unit/runtime/test_cohort_rubric_status_summary.py -q
```

Expected: missing `rubric_status_summary` field or summary builder.

- [ ] **Step 3: Implement one compact rubric summary builder**

Add one private helper in `cohort_service.py`. Use `Counter` so the code says what it is doing without a separate status helper:

```python
from collections import Counter


def _rubric_status_summary(
    summaries: list[EvaluationSummary],
) -> CohortRubricStatusSummaryDto:
    statuses = [
        criterion.status
        for summary in summaries
        for criterion in summary.criterion_results
    ]
    counts = Counter(statuses)

    if not statuses:
        status = "none"
    elif counts["errored"]:
        status = "errored"
    elif counts["failed"]:
        status = "failing"
    elif counts["passed"] and counts["skipped"]:
        status = "mixed"
    elif counts["skipped"] == len(statuses):
        status = "skipped"
    else:
        status = "passing"

    return CohortRubricStatusSummaryDto(
        status=status,
        total_criteria=len(statuses),
        passed=counts["passed"],
        failed=counts["failed"],
        errored=counts["errored"],
        skipped=counts["skipped"],
        criterion_statuses=statuses,
        evaluator_names=sorted({summary.evaluator_name for summary in summaries}),
    )
```

- [ ] **Step 4: Attach cohort row rubric summary**

In `cohort_service.py`, query `RunTaskEvaluation` for cohort runs, group by `run_id`, convert `summary_json` to `EvaluationSummary`, and pass `rubric_status_summary` into `_build_run_row`.

- [ ] **Step 5: Expand test harness state**

In `test_harness.py`, add these fields to the run state JSON:

```json
{
  "rubric_status_summary": {
    "status": "passing",
    "total_criteria": 2,
    "passed": 2,
    "failed": 0,
    "errored": 0,
    "skipped": 0
  },
  "evaluations": [
    {
      "task_id": "node-uuid",
      "task_slug": "d_root",
      "score": 1.0,
      "reason": "root timing marker criterion ran",
      "criterion_statuses": ["passed"],
      "evaluator_name": "post-root"
    }
  ]
}
```

- [ ] **Step 6: Run backend tests**

Run:

```bash
pytest tests/unit/runtime/test_evaluation_summary_contracts.py tests/unit/runtime/test_cohort_rubric_status_summary.py -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Commit**

```bash
git add ergon_core/ergon_core/core/api/runs.py ergon_core/ergon_core/core/runtime/services/run_read_service.py ergon_core/ergon_core/core/runtime/services/cohort_schemas.py ergon_core/ergon_core/core/runtime/services/cohort_service.py ergon_core/ergon_core/core/api/test_harness.py tests/unit/runtime/test_cohort_rubric_status_summary.py
git commit -m "feat: expose cohort rubric status summary"
```

### Task 3: Frontend Contracts And Evaluation Selectors

**Files:**
- Modify: `ergon-dashboard/src/generated/rest/contracts.ts`
- Modify: `ergon-dashboard/src/lib/contracts/rest.ts`
- Modify: `ergon-dashboard/src/lib/types.ts`
- Modify: `ergon-dashboard/src/lib/runState.ts`
- Create: `ergon-dashboard/src/features/evaluations/contracts.ts`
- Create: `ergon-dashboard/src/features/evaluations/status.ts`
- Create: `ergon-dashboard/src/features/evaluations/selectors.ts`
- Test: `ergon-dashboard/src/features/evaluations/selectors.test.ts`

- [ ] **Step 1: Regenerate REST contracts**

Run the repository's existing OpenAPI generation command. If the command is not documented, inspect `package.json` scripts and use the local script rather than hand-editing generated files.

Expected: `src/generated/rest/contracts.ts` includes the new evaluation fields.

- [ ] **Step 2: Write selector tests**

Create `selectors.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { buildContainerEvaluationRollup, isEvaluationBearingTask } from "./selectors";
import type { EvaluationRollup } from "./contracts";
import type { TaskState, WorkflowRunState } from "@/lib/types";

function evaluation(status: "passed" | "failed" | "errored" | "skipped") {
  return {
    id: `evaluation-${status}`,
    evaluatorName: "default",
    totalScore: status === "passed" ? 1 : 0,
    maxScore: 1,
    normalizedScore: status === "passed" ? 1 : 0,
    criterionResults: [{ id: `criterion-${status}`, status, score: status === "passed" ? 1 : 0, maxScore: 1 }],
  };
}

it("detects tasks with direct evaluation evidence", () => {
  const task = { id: "a", childIds: [] } as TaskState;
  const state = {
    evaluationsByTask: new Map([["a", evaluation("passed")]]),
  } as unknown as WorkflowRunState;

  expect(isEvaluationBearingTask(state, task)).toBe(true);
});

it("rolls descendant evaluation failures up to a container", () => {
  const state = {
    tasks: new Map([
      ["root", { id: "root", childIds: ["a", "b"] }],
      ["a", { id: "a", childIds: [] }],
      ["b", { id: "b", childIds: [] }],
    ]),
    evaluationsByTask: new Map([
      ["a", evaluation("passed")],
      ["b", evaluation("failed")],
    ]),
  } as unknown as WorkflowRunState;

  expect(buildContainerEvaluationRollup(state, "root").status).toBe("failing");
});
```

- [ ] **Step 3: Run selector tests and verify failure**

Run: `cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts`

Expected: failure because files/types are missing.

- [ ] **Step 4: Add frontend evaluation contracts and status mapping**

Create `contracts.ts`:

```ts
export type EvalCriterionStatus = "passed" | "failed" | "errored" | "skipped";
export type EvalRollupStatus = "passing" | "failing" | "errored" | "skipped" | "mixed";
export type RubricStatusSummaryStatus = EvalRollupStatus | "none";

export interface EvaluationRollup {
  status: EvalRollupStatus;
  totalCriteria: number;
  passed: number;
  failed: number;
  errored: number;
  skipped: number;
  normalizedScore: number | null;
  maxScore: number | null;
  evaluatorNames: string[];
  attachedTaskIds: string[];
  criterionStatuses: EvalCriterionStatus[];
}
```

Create `status.ts`:

```ts
import type { EvalCriterionStatus, EvalRollupStatus } from "./contracts";

export const EVALUATION_STATUS_LABEL: Record<EvalRollupStatus, string> = {
  passing: "Passing",
  failing: "Failing",
  errored: "Errored",
  skipped: "Skipped",
  mixed: "Mixed",
};

export const CRITERION_STATUS_LABEL: Record<EvalCriterionStatus, string> = {
  passed: "Passed",
  failed: "Failed",
  errored: "Errored",
  skipped: "Skipped",
};

export function evaluationStatusTone(status: EvalRollupStatus): string {
  switch (status) {
    case "passing":
      return "oklch(0.70 0.13 155)";
    case "failing":
      return "oklch(0.68 0.18 22)";
    case "errored":
      return "oklch(0.62 0.18 35)";
    case "skipped":
      return "oklch(0.65 0.03 250)";
    case "mixed":
      return "oklch(0.72 0.12 85)";
  }
}
```

- [ ] **Step 5: Add frontend selectors**

Create `selectors.ts`:

```ts
import type { TaskEvaluationState, TaskState, WorkflowRunState } from "@/lib/types";
import type { EvalRollupStatus, EvaluationRollup } from "./contracts";

export function isEvaluationBearingTask(state: WorkflowRunState, task: TaskState): boolean {
  return buildContainerEvaluationRollup(state, task.id) !== null;
}

function combineStatus(statuses: EvalRollupStatus[]): EvalRollupStatus {
  if (statuses.includes("errored")) return "errored";
  if (statuses.includes("failing")) return "failing";
  if (statuses.includes("mixed")) return "mixed";
  if (statuses.includes("skipped") && statuses.includes("passing")) return "mixed";
  if (statuses.every((status) => status === "skipped")) return "skipped";
  if (statuses.every((status) => status === "passing")) return "passing";
  return "mixed";
}

function evaluationToRollup(evaluation: TaskEvaluationState | undefined): EvaluationRollup | null {
  if (!evaluation) return null;
  const statuses = evaluation.criterionResults.map((criterion) => criterion.status);
  if (statuses.length === 0) return null;
  const passed = statuses.filter((status) => status === "passed").length;
  const failed = statuses.filter((status) => status === "failed").length;
  const errored = statuses.filter((status) => status === "errored").length;
  const skipped = statuses.filter((status) => status === "skipped").length;
  return {
    status: combineStatus(
      statuses.map((status) =>
        status === "passed" ? "passing" : status === "failed" ? "failing" : status === "errored" ? "errored" : "skipped",
      ),
    ),
    totalCriteria: statuses.length,
    passed,
    failed,
    errored,
    skipped,
    normalizedScore: evaluation.normalizedScore,
    maxScore: evaluation.maxScore,
    evaluatorNames: [evaluation.evaluatorName],
    attachedTaskIds: evaluation.taskId ? [evaluation.taskId] : [],
    criterionStatuses: statuses,
  };
}

export function buildContainerEvaluationRollup(state: WorkflowRunState, taskId: string): EvaluationRollup | null {
  const task = state.tasks.get(taskId);
  if (!task) return null;

  const direct = evaluationToRollup(state.evaluationsByTask.get(taskId));
  const childRollups = task.childIds.map((childId) => buildContainerEvaluationRollup(state, childId));
  const rollups = [direct, ...childRollups].filter(
    (rollup): rollup is EvaluationRollup => rollup !== null,
  );

  if (rollups.length === 0) return null;

  const totalCriteria = rollups.reduce((sum, rollup) => sum + rollup.totalCriteria, 0);
  const maxScore = rollups.reduce((sum, rollup) => sum + rollup.maxScore, 0);
  const weightedScore = rollups.reduce(
    (sum, rollup) => sum + rollup.normalizedScore * rollup.maxScore,
    0,
  );

  return {
    status: combineStatus(rollups.map((rollup) => rollup.status)),
    totalCriteria,
    passed: rollups.reduce((sum, rollup) => sum + rollup.passed, 0),
    failed: rollups.reduce((sum, rollup) => sum + rollup.failed, 0),
    errored: rollups.reduce((sum, rollup) => sum + rollup.errored, 0),
    skipped: rollups.reduce((sum, rollup) => sum + rollup.skipped, 0),
    normalizedScore: weightedScore / maxScore,
    maxScore,
    evaluatorNames: Array.from(new Set(rollups.flatMap((rollup) => rollup.evaluatorNames))).sort(),
    attachedTaskIds: Array.from(new Set(rollups.flatMap((rollup) => rollup.attachedTaskIds))).sort(),
    criterionStatuses: rollups.flatMap((rollup) => rollup.criterionStatuses),
  };
}
```

- [ ] **Step 6: Normalize contracts and run state**

In `rest.ts`, require the enriched existing evaluation fields (`criterionName`, `status`, `passed`, `weight`, `contribution`, `evaluatorName`, `aggregationRule`) to be present after contract generation. Normalize only genuinely nullable fields (`modelReasoning`, `skippedReason`, `feedback`, `evaluationInput`, `error`) to `null`. In `runState.ts`, continue deserializing `evaluationsByTask`; do not add `taskEvaluationRollups` or `runEvaluationRollup` to `WorkflowRunState`.

- [ ] **Step 7: Run frontend tests**

Run: `cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts`

Expected: tests pass.

- [ ] **Step 8: Commit**

```bash
git add ergon-dashboard/src/generated/rest/contracts.ts ergon-dashboard/src/lib/contracts/rest.ts ergon-dashboard/src/lib/types.ts ergon-dashboard/src/lib/runState.ts ergon-dashboard/src/features/evaluations/contracts.ts ergon-dashboard/src/features/evaluations/status.ts ergon-dashboard/src/features/evaluations/selectors.ts ergon-dashboard/src/features/evaluations/selectors.test.ts
git commit -m "feat: add frontend evaluation state domain"
```

### Task 4: Cohort Rubric Status Strips

**Files:**
- Create: `ergon-dashboard/src/features/evaluations/components/CriterionStatusPip.tsx`
- Create: `ergon-dashboard/src/features/evaluations/components/RubricStatusStrip.tsx`
- Modify: `ergon-dashboard/src/components/cohorts/CohortDetailView.tsx`
- Test: `ergon-dashboard/tests/e2e/_shared/smoke.ts`

- [ ] **Step 1: Add Playwright assertion first**

In the cohort index test in `smoke.ts`, assert every run row has a strip:

```ts
for (const { run_id } of cohort) {
  await expect(page.getByTestId(`cohort-eval-strip-${run_id}`)).toBeVisible();
  await expect(page.locator(`[data-testid^="cohort-eval-pip-${run_id}-"]`).first()).toBeVisible();
}
```

- [ ] **Step 2: Run Playwright smoke locally against an existing smoke stack**

Run the narrow Playwright command used by the current E2E workflow for one benchmark.

Expected: failure because the rubric status strip test IDs do not exist.

- [ ] **Step 3: Create `CriterionStatusPip`**

```tsx
import type { EvalCriterionStatus } from "@/features/evaluations/contracts";
import { CRITERION_STATUS_LABEL, evaluationStatusTone } from "@/features/evaluations/status";

const rollupStatusByCriterion: Record<EvalCriterionStatus, Parameters<typeof evaluationStatusTone>[0]> = {
  passed: "passing",
  failed: "failing",
  errored: "errored",
  skipped: "skipped",
};

export function CriterionStatusPip({
  status,
  testId,
}: {
  status: EvalCriterionStatus;
  testId?: string;
}) {
  return (
    <span
      data-testid={testId}
      aria-label={`Criterion ${CRITERION_STATUS_LABEL[status]}`}
      title={CRITERION_STATUS_LABEL[status]}
      className="inline-block h-2.5 w-2.5 rounded-full ring-1 ring-white/80"
      style={{ backgroundColor: evaluationStatusTone(rollupStatusByCriterion[status]) }}
    />
  );
}
```

- [ ] **Step 4: Create `RubricStatusStrip`**

```tsx
import type { CohortRunRow } from "@/lib/types";
import { CriterionStatusPip } from "./CriterionStatusPip";

export function RubricStatusStrip({
  runId,
  summary,
}: {
  runId: string;
  summary: CohortRunRow["rubric_status_summary"];
}) {
  const statuses = summary.criterion_statuses;

  return (
    <div data-testid={`cohort-eval-strip-${runId}`} className="mt-2 flex items-center gap-1.5">
      <span className="text-[10px] font-medium uppercase tracking-[0.08em] text-[var(--faint)]">
        Rubric
      </span>
      {statuses.length === 0 ? (
        <span className="text-xs text-[var(--muted)]">No criteria</span>
      ) : (
        <span className="flex items-center gap-1">
          {statuses.map((status, index) => (
            <CriterionStatusPip
              key={`${status}-${index}`}
              status={status}
              testId={`cohort-eval-pip-${runId}-${index}`}
            />
          ))}
        </span>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Render strip in cohort rows**

In `CohortRunRowCard`, render:

```tsx
<RubricStatusStrip runId={run.run_id} summary={run.rubric_status_summary} />
```

Place it under the cohort/run ID metadata so it is visible without widening the grid.

- [ ] **Step 6: Run frontend and E2E checks**

Run:

```bash
cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts
```

Then run the narrow Playwright smoke command.

Expected: selector tests pass and Playwright sees cohort rubric status strips.

- [ ] **Step 7: Commit**

```bash
git add ergon-dashboard/src/features/evaluations/components/CriterionStatusPip.tsx ergon-dashboard/src/features/evaluations/components/RubricStatusStrip.tsx ergon-dashboard/src/components/cohorts/CohortDetailView.tsx ergon-dashboard/tests/e2e/_shared/smoke.ts
git commit -m "feat: show cohort rubric status"
```

### Task 5: Graph Glyphs, Container Roll-Ups, And Evaluation Lens

**Files:**
- Create: `ergon-dashboard/src/features/evaluations/components/EvaluationNodeGlyph.tsx`
- Create: `ergon-dashboard/src/features/evaluations/components/EvaluationRollupBadge.tsx`
- Create: `ergon-dashboard/src/features/evaluations/components/EvaluationLensToggle.tsx`
- Modify: `ergon-dashboard/src/components/dag/TaskNode.tsx`
- Modify: `ergon-dashboard/src/features/graph/components/LeafNode.tsx`
- Modify: `ergon-dashboard/src/features/graph/components/ContainerNode.tsx`
- Modify: `ergon-dashboard/src/components/dag/DAGCanvas.tsx`
- Test: `ergon-dashboard/tests/e2e/_shared/smoke.ts`

- [ ] **Step 1: Add Playwright graph assertions first**

In `assertRunWorkspace`, after selecting an evaluated task:

```ts
if (evaluatedTaskIds.has(selected.id)) {
  await expect(page.getByTestId(`graph-eval-glyph-${selected.id}`)).toBeVisible();
}
await expect(page.getByTestId("graph-eval-lens-toggle")).toBeVisible();
await page.getByTestId("graph-eval-lens-toggle").click();
await expect(page.getByTestId("graph-canvas")).toHaveAttribute("data-eval-lens", "on");
```

- [ ] **Step 2: Run Playwright and verify failure**

Expected: missing glyph/toggle test IDs.

- [ ] **Step 3: Create graph evaluation components**

`EvaluationNodeGlyph.tsx`:

```tsx
import type { EvaluationRollup } from "@/features/evaluations/contracts";
import { EVALUATION_STATUS_LABEL, evaluationStatusTone } from "@/features/evaluations/status";

export function EvaluationNodeGlyph({
  taskId,
  rollup,
}: {
  taskId: string;
  rollup: EvaluationRollup;
}) {
  return (
    <span
      data-testid={`graph-eval-glyph-${taskId}`}
      aria-label={`Evaluation ${EVALUATION_STATUS_LABEL[rollup.status]}`}
      title={`Evaluation ${EVALUATION_STATUS_LABEL[rollup.status]}`}
      className="inline-flex h-4 w-4 items-center justify-center rounded-full text-[10px] font-semibold"
      style={{ color: evaluationStatusTone(rollup.status), backgroundColor: "rgba(255,255,255,0.8)" }}
    >
      &#9671;
    </span>
  );
}
```

`EvaluationRollupBadge.tsx`:

```tsx
import type { EvaluationRollup } from "@/features/evaluations/contracts";
import { EVALUATION_STATUS_LABEL, evaluationStatusTone } from "@/features/evaluations/status";

export function EvaluationRollupBadge({
  taskId,
  rollup,
}: {
  taskId: string;
  rollup: EvaluationRollup;
}) {
  return (
    <span
      data-testid={`graph-eval-rollup-${taskId}`}
      className="rounded-full px-1.5 py-0.5 text-[10px] font-medium"
      style={{
        color: evaluationStatusTone(rollup.status),
        backgroundColor: "rgba(255,255,255,0.75)",
        border: `1px solid ${evaluationStatusTone(rollup.status)}`,
      }}
    >
      {EVALUATION_STATUS_LABEL[rollup.status]} · {rollup.totalCriteria}
    </span>
  );
}
```

`EvaluationLensToggle.tsx`:

```tsx
export function EvaluationLensToggle({
  enabled,
  onToggle,
}: {
  enabled: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      data-testid="graph-eval-lens-toggle"
      aria-pressed={enabled}
      onClick={onToggle}
      className={`rounded px-2 py-1 text-xs font-medium ring-1 ${
        enabled
          ? "bg-[var(--ink)] text-[var(--card)] ring-[var(--ink)]"
          : "bg-[var(--card)] text-[var(--muted)] ring-[var(--line)]"
      }`}
    >
      Eval lens
    </button>
  );
}
```

- [ ] **Step 4: Pass roll-ups through React Flow node data**

Extend `TaskNodeData`:

```ts
evaluationRollup?: EvaluationRollup;
evalLensEnabled?: boolean;
```

When building React Flow nodes in `DAGCanvas.tsx`, set:

```ts
const evaluationRollup = buildContainerEvaluationRollup(runState, task.id);
const evalBearing = evaluationRollup !== null;
data: {
  task,
  evaluationRollup,
  evalLensEnabled,
  dimmed: evalLensEnabled ? !evalBearing : isSearchDimmed,
}
```

- [ ] **Step 5: Render glyphs and roll-ups in nodes**

In `LeafNode.tsx`, render `EvaluationNodeGlyph` near the title for direct task evaluations and `EvaluationRollupBadge` if there are multiple criteria.

In `ContainerNode.tsx`, render `EvaluationRollupBadge` in the header row next to the child count.

- [ ] **Step 6: Add lens toggle to DAG controls**

In `DAGCanvas.tsx`, keep:

```ts
const [evalLensEnabled, setEvalLensEnabled] = useState(false);
```

Render `EvaluationLensToggle` in the floating control card area and set:

```tsx
<div data-testid="graph-canvas" data-eval-lens={evalLensEnabled ? "on" : "off"}>
```

- [ ] **Step 7: Run focused frontend tests and Playwright**

Run:

```bash
cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts
```

Run the narrow Playwright smoke command.

Expected: graph glyph and lens assertions pass.

- [ ] **Step 8: Commit**

```bash
git add ergon-dashboard/src/features/evaluations/components/EvaluationNodeGlyph.tsx ergon-dashboard/src/features/evaluations/components/EvaluationRollupBadge.tsx ergon-dashboard/src/features/evaluations/components/EvaluationLensToggle.tsx ergon-dashboard/src/components/dag/TaskNode.tsx ergon-dashboard/src/features/graph/components/LeafNode.tsx ergon-dashboard/src/features/graph/components/ContainerNode.tsx ergon-dashboard/src/components/dag/DAGCanvas.tsx ergon-dashboard/tests/e2e/_shared/smoke.ts
git commit -m "feat: add evaluation graph lens"
```

### Task 6: Rich Evaluation Workspace Panel

**Files:**
- Create: `ergon-dashboard/src/features/evaluations/components/EvaluationCriterionCard.tsx`
- Create: `ergon-dashboard/src/features/evaluations/components/EvaluationMetadataSummary.tsx`
- Modify: `ergon-dashboard/src/components/panels/EvaluationPanel.tsx`
- Test: `ergon-dashboard/tests/e2e/_shared/smoke.ts`

- [ ] **Step 1: Add Playwright drawer assertions first**

In `assertRunWorkspace`, inside the evaluation tab branch for evaluated tasks:

```ts
await expect(page.getByTestId("workspace-evaluation-metadata")).toBeVisible();
await expect(page.locator('[data-testid^="workspace-evaluation-criterion-"]').first()).toBeVisible();
await expect(page.locator('[data-testid^="workspace-evaluation-criterion-status-"]').first()).toBeVisible();
await expect(page.locator('[data-testid^="workspace-evaluation-input-"]').first()).toBeVisible();
```

- [ ] **Step 2: Run Playwright and verify failure**

Expected: metadata and criterion card test IDs missing.

- [ ] **Step 3: Create `EvaluationMetadataSummary`**

```tsx
import type { TaskEvaluationState } from "@/lib/types";

export function EvaluationMetadataSummary({ evaluation }: { evaluation: TaskEvaluationState }) {
  return (
    <section data-testid="workspace-evaluation-metadata" className="rounded border border-[var(--line)] bg-[var(--paper)] p-3">
      <div className="grid grid-cols-2 gap-3 text-sm">
        <div>
          <div className="text-xs text-[var(--faint)]">Evaluator</div>
          <div className="font-medium text-[var(--ink)]">{evaluation.evaluatorName}</div>
        </div>
        <div>
          <div className="text-xs text-[var(--faint)]">Aggregation</div>
          <div className="font-medium text-[var(--ink)]">{evaluation.aggregationRule}</div>
        </div>
        <div>
          <div className="text-xs text-[var(--faint)]">Score</div>
          <div className="font-medium text-[var(--ink)]">
            {evaluation.totalScore.toFixed(2)} / {evaluation.maxScore.toFixed(2)}
          </div>
        </div>
        <div>
          <div className="text-xs text-[var(--faint)]">Stages</div>
          <div className="font-medium text-[var(--ink)]">
            {evaluation.stagesPassed} / {evaluation.stagesEvaluated} passed
          </div>
        </div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Create `EvaluationCriterionCard`**

```tsx
import type { EvaluationCriterionState } from "@/lib/types";
import { CRITERION_STATUS_LABEL, evaluationStatusTone } from "@/features/evaluations/status";

export function EvaluationCriterionCard({ criterion }: { criterion: EvaluationCriterionState }) {
  const tone = evaluationStatusTone(
    criterion.status === "passed"
      ? "passing"
      : criterion.status === "failed"
        ? "failing"
        : criterion.status === "errored"
          ? "errored"
          : "skipped",
  );

  return (
    <article
      data-testid={`workspace-evaluation-criterion-${criterion.id}`}
      className="rounded border border-[var(--line)] bg-[var(--card)] p-3"
    >
      <div className="flex items-start justify-between gap-3">
        <div>
          <h4 className="font-medium text-[var(--ink)]">{criterion.criterionDescription}</h4>
          <div className="mt-1 text-xs text-[var(--muted)]">
            {criterion.stageName} · weight {criterion.weight.toFixed(2)} · contribution {criterion.contribution.toFixed(2)}
          </div>
        </div>
        <span
          data-testid={`workspace-evaluation-criterion-status-${criterion.id}`}
          className="rounded-full px-2 py-0.5 text-xs font-medium"
          style={{ color: tone, border: `1px solid ${tone}` }}
        >
          {CRITERION_STATUS_LABEL[criterion.status]}
        </span>
      </div>

      {criterion.evaluationInput && (
        <div data-testid={`workspace-evaluation-input-${criterion.id}`} className="mt-3 rounded bg-[var(--paper)] p-2 text-xs text-[var(--muted)]">
          {criterion.evaluationInput}
        </div>
      )}

      {criterion.feedback && <p className="mt-3 text-sm text-[var(--ink)]">{criterion.feedback}</p>}

      {criterion.modelReasoning && (
        <div data-testid={`workspace-evaluation-reasoning-${criterion.id}`} className="mt-3 text-sm text-[var(--muted)]">
          {criterion.modelReasoning}
        </div>
      )}

      {criterion.skippedReason && <p className="mt-3 text-sm text-[var(--muted)]">{criterion.skippedReason}</p>}

      {criterion.error && (
        <pre className="mt-3 overflow-auto rounded bg-[var(--paper)] p-2 text-xs text-[var(--ink)]">
          {JSON.stringify(criterion.error, null, 2)}
        </pre>
      )}
    </article>
  );
}
```

- [ ] **Step 5: Replace the current criterion map in `EvaluationPanel`**

Keep existing empty state behavior, but render:

```tsx
<EvaluationMetadataSummary evaluation={evaluation} />
<div className="mt-3 space-y-3">
  {evaluation.criterionResults.map((criterion) => (
    <EvaluationCriterionCard key={criterion.id} criterion={criterion} />
  ))}
</div>
```

- [ ] **Step 6: Run frontend and E2E checks**

Run:

```bash
cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts
```

Run the narrow Playwright smoke command.

Expected: evaluation workspace assertions pass.

- [ ] **Step 7: Commit**

```bash
git add ergon-dashboard/src/features/evaluations/components/EvaluationCriterionCard.tsx ergon-dashboard/src/features/evaluations/components/EvaluationMetadataSummary.tsx ergon-dashboard/src/components/panels/EvaluationPanel.tsx ergon-dashboard/tests/e2e/_shared/smoke.ts
git commit -m "feat: enrich evaluation workspace panel"
```

### Task 7: End-To-End Hardening

**Files:**
- Modify: `ergon-dashboard/tests/helpers/backendHarnessClient.ts`
- Modify: `ergon-dashboard/tests/e2e/_shared/smoke.ts`
- Modify: `tests/e2e/_asserts.py`
- Modify: `docs/architecture/07_testing.md`

- [ ] **Step 1: Expand backend harness TypeScript DTO**

In `backendHarnessClient.ts`, add:

```ts
export interface BackendEvaluationRollup {
  status: "passing" | "failing" | "errored" | "skipped" | "mixed" | "none" | string;
  total_criteria: number;
  passed: number;
  failed: number;
  errored: number;
  skipped: number;
}
```

Extend `BackendRunState`:

```ts
rubric_status_summary: BackendEvaluationRollup;
evaluations: {
  task_id: string;
  task_slug: string | null;
  score: number;
  reason: string;
  evaluator_name: string | null;
  criterion_statuses: string[];
}[];
```

- [ ] **Step 2: Add backend E2E assertions**

In `tests/e2e/_asserts.py`, assert happy runs expose:

```python
assert len(root_evaluations) == 2
assert {ev.parsed_summary().evaluator_name for ev in root_evaluations} >= {"default", "post-root"}
assert all(
    cr.status == "passed"
    for ev in root_evaluations
    for cr in ev.parsed_summary().criterion_results
)
```

For sad runs, assert failed or skipped criterion state is exposed when a criterion does not pass.

- [ ] **Step 3: Add UI assertions for each feature**

In `smoke.ts`, assert:

```ts
expect(state.rubric_status_summary.total_criteria).toBeGreaterThan(0);
await expect(page.getByTestId("graph-eval-lens-toggle")).toBeVisible();
await expect(page.locator('[data-testid^="workspace-evaluation-criterion-"]').first()).toBeVisible();
```

For happy runs:

```ts
expect(state.rubric_status_summary.status).toBe("passing");
```

For sad runs:

```ts
expect(["failing", "errored", "mixed", "skipped"]).toContain(state.rubric_status_summary.status);
```

- [ ] **Step 4: Update testing docs**

In `docs/architecture/07_testing.md`, add the frontend evaluation visibility surface to the E2E assertion table:

```text
Evaluation visibility | Cohort pips, graph glyphs, container roll-ups, eval lens, workspace criterion cards | Playwright + backend harness DTO
```

- [ ] **Step 5: Run focused checks**

Run:

```bash
pytest tests/unit/runtime/test_evaluation_summary_contracts.py tests/unit/runtime/test_cohort_rubric_status_summary.py -q
cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts
```

Run the benchmark E2E smoke workflow locally for one benchmark if the stack is already available.

Expected: unit and frontend tests pass; Playwright passes for the exercised benchmark.

- [ ] **Step 6: Commit**

```bash
git add ergon-dashboard/tests/helpers/backendHarnessClient.ts ergon-dashboard/tests/e2e/_shared/smoke.ts tests/e2e/_asserts.py docs/architecture/07_testing.md
git commit -m "test: cover evaluation visibility e2e"
```

---

## Rollout Notes

1. Backend changes are additive and can ship before frontend rendering.
2. Generated REST contracts must be refreshed after backend DTO changes and before frontend contract normalization.
3. Cohort roll-ups intentionally stay lightweight to avoid loading full run snapshots for every row.
4. The evaluation lens is local UI state; it should not change the URL in the first implementation.
5. If skipped criteria require semantics not available in `summary_json`, extend `CriterionExecutor` to emit explicit skipped results in a later follow-up rather than inferring skipped state from missing rows.

## Verification Matrix

- Backend unit: `pytest tests/unit/runtime/test_evaluation_summary_contracts.py -q`
- Backend unit: `pytest tests/unit/runtime/test_cohort_rubric_status_summary.py -q`
- Frontend unit: `cd ergon-dashboard && npm test -- features/evaluations/selectors.test.ts`
- E2E: run the existing canonical smoke command for at least one happy/sad cohort.
- Lints: use `ReadLints` for edited files after each frontend and backend slice.

## Self-Review

- Spec coverage: cohort pips are covered in Task 4; graph glyphs, container roll-ups, and eval lens are covered in Task 5; richer drawer metadata and criterion detail are covered in Task 6; backend schemas/endpoints are covered in Tasks 1 and 2; E2E coverage is covered in Task 7.
- Placeholder scan: the plan contains concrete fields, commands, file paths, test IDs, and code shapes. Follow-up notes are explicitly scoped to future semantics rather than missing implementation steps.
- Type consistency: `EvalCriterionStatus`, `EvalRollupStatus`, `CohortRubricStatusSummaryDto`, and frontend-only `EvaluationRollup` names are used consistently across backend, frontend contracts, selectors, and components.

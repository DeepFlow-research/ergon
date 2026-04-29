import type { TaskEvaluationState, WorkflowRunState } from "@/lib/types";
import type { EvalCriterionStatus, EvalRollupStatus, EvaluationRollup } from "./contracts";

function criterionStatusToRollupStatus(status: EvalCriterionStatus): EvalRollupStatus {
  if (status === "passed") return "passing";
  if (status === "failed") return "failing";
  return status;
}

export function combineEvaluationStatuses(statuses: EvalRollupStatus[]): EvalRollupStatus {
  if (statuses.includes("errored")) return "errored";
  if (statuses.includes("failing")) return "failing";
  if (statuses.includes("mixed")) return "mixed";
  if (statuses.includes("skipped") && statuses.includes("passing")) return "mixed";
  if (statuses.every((status) => status === "skipped")) return "skipped";
  return "passing";
}

export function evaluationToRollup(evaluation: TaskEvaluationState | undefined): EvaluationRollup | null {
  if (!evaluation || evaluation.criterionResults.length === 0) return null;

  const criterionStatuses = evaluation.criterionResults.map(
    (criterion) => criterion.status as EvalCriterionStatus,
  );
  const passed = criterionStatuses.filter((status) => status === "passed").length;
  const failed = criterionStatuses.filter((status) => status === "failed").length;
  const errored = criterionStatuses.filter((status) => status === "errored").length;
  const skipped = criterionStatuses.filter((status) => status === "skipped").length;

  return {
    status: combineEvaluationStatuses(criterionStatuses.map(criterionStatusToRollupStatus)),
    totalCriteria: criterionStatuses.length,
    passed,
    failed,
    errored,
    skipped,
    normalizedScore: evaluation.normalizedScore,
    maxScore: evaluation.maxScore,
    evaluatorNames: [evaluation.evaluatorName],
    attachedTaskIds: evaluation.taskId ? [evaluation.taskId] : [],
    criterionStatuses,
  };
}

export function buildContainerEvaluationRollup(
  state: WorkflowRunState,
  taskId: string,
): EvaluationRollup | null {
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
    status: combineEvaluationStatuses(rollups.map((rollup) => rollup.status)),
    totalCriteria,
    passed: rollups.reduce((sum, rollup) => sum + rollup.passed, 0),
    failed: rollups.reduce((sum, rollup) => sum + rollup.failed, 0),
    errored: rollups.reduce((sum, rollup) => sum + rollup.errored, 0),
    skipped: rollups.reduce((sum, rollup) => sum + rollup.skipped, 0),
    normalizedScore: maxScore > 0 ? weightedScore / maxScore : 0,
    maxScore,
    evaluatorNames: Array.from(new Set(rollups.flatMap((rollup) => rollup.evaluatorNames))).sort(),
    attachedTaskIds: Array.from(new Set(rollups.flatMap((rollup) => rollup.attachedTaskIds))).sort(),
    criterionStatuses: rollups.flatMap((rollup) => rollup.criterionStatuses),
  };
}

export function isEvaluationBearingTask(state: WorkflowRunState, taskId: string): boolean {
  return buildContainerEvaluationRollup(state, taskId) !== null;
}

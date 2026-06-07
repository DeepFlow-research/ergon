import type { TaskEvaluationState, SampleWorkspaceState } from "@/lib/types";
import { formatScore } from "@/lib/sample-state/formatters";
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

function criterionStateLabel(status: EvalCriterionStatus): string {
  switch (status) {
    case "passed":
      return "Pass";
    case "failed":
      return "Fail";
    case "skipped":
      return "Skipped";
    case "errored":
      return "Error";
  }
}

export interface EvaluationCriterionViewModel {
  id: string;
  status: EvalCriterionStatus;
  stateLabel: string;
  stageLabel: string;
  title: string;
  typeLabel: string;
  scoreLabel: string;
  contributionLabel: string;
  weightLabel: string;
  feedback: string | null;
  modelReasoning: string | null;
  skippedReason: string | null;
  evaluationInput: string | null;
  error: Record<string, unknown> | null;
  evaluatedActionIds: string[];
  evaluatedResourceIds: string[];
}

export interface EvaluationViewModel {
  summary: {
    evaluatorName: string;
    status: EvalRollupStatus;
    scoreLabel: string;
    criteriaLabel: string;
    failedGateLabel: string;
  };
  composition: {
    aggregationRule: string;
    totalScoreLabel: string;
    stagesLabel: string;
  };
  counts: Pick<EvaluationRollup, "passed" | "failed" | "skipped" | "errored" | "totalCriteria">;
  criteria: EvaluationCriterionViewModel[];
}

export function evaluationToViewModel(
  evaluation: TaskEvaluationState | null | undefined,
): EvaluationViewModel | null {
  if (!evaluation) return null;

  const rollup =
    evaluationToRollup(evaluation) ??
    ({
      status: "skipped",
      totalCriteria: 0,
      passed: 0,
      failed: 0,
      skipped: 0,
      errored: 0,
      normalizedScore: evaluation.normalizedScore,
      maxScore: evaluation.maxScore,
      evaluatorNames: [evaluation.evaluatorName],
      attachedTaskIds: evaluation.taskId ? [evaluation.taskId] : [],
      criterionStatuses: [],
    } satisfies EvaluationRollup);

  const criteriaLabel = `${rollup.passed} passed, ${rollup.failed} failed, ${rollup.skipped} skipped, ${rollup.errored} errored`;

  return {
    summary: {
      evaluatorName: evaluation.evaluatorName,
      status: rollup.status,
      scoreLabel: formatScore(evaluation.normalizedScore).value,
      criteriaLabel,
      failedGateLabel: evaluation.failedGate ?? "None",
    },
    composition: {
      aggregationRule: evaluation.aggregationRule,
      totalScoreLabel: `${evaluation.totalScore} / ${evaluation.maxScore}`,
      stagesLabel: `${evaluation.stagesPassed} / ${evaluation.stagesEvaluated}`,
    },
    counts: {
      totalCriteria: rollup.totalCriteria,
      passed: rollup.passed,
      failed: rollup.failed,
      skipped: rollup.skipped,
      errored: rollup.errored,
    },
    criteria: evaluation.criterionResults.map((criterion) => {
      const status = criterion.status as EvalCriterionStatus;
      return {
        id: criterion.id,
        status,
        stateLabel: criterionStateLabel(status),
        stageLabel: `${criterion.stageName} · #${criterion.criterionNum + 1}`,
        title: criterion.criterionDescription || criterion.criterionName,
        typeLabel: criterion.criterionType,
        scoreLabel: `${criterion.score} / ${criterion.maxScore}`,
        contributionLabel: String(criterion.contribution),
        weightLabel: String(criterion.weight),
        feedback: criterion.feedback ?? null,
        modelReasoning: criterion.modelReasoning ?? null,
        skippedReason: criterion.skippedReason ?? null,
        evaluationInput: criterion.evaluationInput ?? null,
        error: criterion.error ?? null,
        evaluatedActionIds: criterion.evaluatedActionIds ?? [],
        evaluatedResourceIds: criterion.evaluatedResourceIds ?? [],
      };
    }),
  };
}

export function buildContainerEvaluationRollup(
  state: SampleWorkspaceState,
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

export function isEvaluationBearingTask(state: SampleWorkspaceState, taskId: string): boolean {
  return buildContainerEvaluationRollup(state, taskId) !== null;
}

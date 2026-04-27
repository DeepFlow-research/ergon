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

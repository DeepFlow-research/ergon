"use client";

import { TaskEvaluationState } from "@/lib/types";

function formatPercent(score: number): string {
  return `${(score * 100).toFixed(1)}%`;
}

function EvaluationCriteriaEmpty({ detail }: { detail: string }) {
  return (
    <div
      className="rounded-xl border border-dashed border-gray-300 bg-gray-50 px-4 py-6 text-center text-gray-500 dark:border-gray-700 dark:bg-gray-800/40 dark:text-gray-400"
      data-testid="evaluation-criteria-empty"
    >
      <p className="font-medium text-gray-700 dark:text-gray-200">
        No evaluation criteria recorded yet
      </p>
      <p className="mt-1 text-sm">{detail}</p>
    </div>
  );
}

export function EvaluationPanel({
  evaluation,
}: {
  evaluation: TaskEvaluationState | null;
}) {
  if (!evaluation) {
    return (
      <EvaluationCriteriaEmpty detail="Evaluation details will appear when a persisted evaluation payload is available." />
    );
  }

  return (
    <div className="space-y-4">
      <div className="grid gap-3 sm:grid-cols-4">
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Normalized</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {formatPercent(evaluation.normalizedScore)}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Total score</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.totalScore} / {evaluation.maxScore}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Stages passed</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.stagesPassed} / {evaluation.stagesEvaluated}
          </div>
        </div>
        <div className="rounded-xl bg-gray-50 px-3 py-2 dark:bg-gray-800/50">
          <div className="text-xs text-gray-500 dark:text-gray-400">Failed gate</div>
          <div className="text-sm font-semibold text-gray-900 dark:text-white">
            {evaluation.failedGate ?? "none"}
          </div>
        </div>
      </div>

      {evaluation.criterionResults.length === 0 ? (
        <EvaluationCriteriaEmpty detail="This task has no criterionResults in the persisted evaluation payload." />
      ) : (
        <div className="space-y-3">
          {evaluation.criterionResults.map((criterion) => (
            <div
              key={criterion.id}
              className="rounded-xl border border-gray-200 bg-white px-3 py-3 dark:border-gray-700 dark:bg-gray-900/40"
              data-testid={`evaluation-criterion-${criterion.id}`}
            >
              <div className="flex items-start justify-between gap-4">
                <div>
                  <div className="font-medium text-gray-900 dark:text-white">
                    {criterion.stageName}: {criterion.criterionDescription}
                  </div>
                  <div className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {criterion.criterionType}
                  </div>
                </div>
                <div className="text-sm font-semibold text-gray-900 dark:text-white">
                  {criterion.score} / {criterion.maxScore}
                </div>
              </div>
              {criterion.feedback ? (
                <p className="mt-2 whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-200">
                  {criterion.feedback}
                </p>
              ) : null}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
